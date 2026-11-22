# DELIMITER trong công cụ dòng lệnh và dấu kết thúc stored program

Khi chạy một câu SQL thông thường trong MySQL client, dấu chấm phẩy (`;`) thường báo cho client biết câu lệnh đã kết thúc. Nhưng một stored program như procedure, function hoặc trigger có thể chứa nhiều câu SQL, mỗi câu lại kết thúc bằng `;`. Nếu client dừng ở dấu chấm phẩy đầu tiên, nó sẽ gửi một phần định nghĩa chưa hoàn chỉnh lên máy chủ và nhận lỗi cú pháp.

Lệnh `DELIMITER` giải quyết vấn đề này ở phía công cụ khách. Nó đổi chuỗi mà MySQL command-line client dùng để nhận biết điểm kết thúc của toàn bộ câu lệnh đang nhập. Nhờ đó, dấu `;` vẫn được giữ bên trong thân stored program, còn một chuỗi khác như `$$` hoặc `//` đánh dấu kết thúc câu `CREATE PROCEDURE`, `CREATE FUNCTION` hay `CREATE TRIGGER`.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction, kiểm soát đồng thời và vận hành cơ sở dữ liệu quan hệ. Hiểu đúng `DELIMITER` giúp bạn tạo, chạy và bảo trì stored program trong môi trường dòng lệnh, đồng thời tránh nhầm lẫn giữa cú pháp SQL của máy chủ và lệnh điều khiển của client.

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa dấu kết thúc câu lệnh mà client nhận diện và dấu phân tách câu SQL bên trong stored program.
- Đổi delimiter trong MySQL command-line client và khôi phục về `;`.
- Tạo procedure, function và trigger có nhiều câu lệnh trong thân.
- Chạy tệp SQL chứa stored program bằng MySQL client.
- Nhận biết lỗi do delimiter sai và xử lý khi client còn giữ một câu lệnh chưa hoàn chỉnh.

## 1. Hai lớp xử lý cần phân biệt

Khi bạn gõ SQL vào MySQL client cổ điển (`mysql`), có hai bước riêng:

1. **Client đọc đầu vào:** client tích lũy nội dung bạn nhập. Khi gặp delimiter hiện tại, nó coi phần vừa nhập là một câu lệnh hoàn chỉnh và gửi nội dung SQL đó tới máy chủ.
2. **Máy chủ phân tích SQL:** MySQL nhận câu lệnh qua giao thức kết nối và phân tích cú pháp SQL. Máy chủ hiểu cấu trúc `CREATE PROCEDURE`, `BEGIN ... END`, `IF ... END IF` và các câu lệnh bên trong.

Ở chế độ mặc định, delimiter của MySQL client là `;`. Ví dụ:

```sql
SELECT VERSION();
SHOW DATABASES;
```

Mỗi dấu `;` kết thúc một câu lệnh riêng để client gửi đi. Dấu `;` không phải là một câu lệnh SQL độc lập; nó là ký hiệu kết thúc câu lệnh trong cách nhập SQL thông thường.

`DELIMITER` là lệnh do MySQL client xử lý. Nó **không phải câu lệnh SQL gửi tới máy chủ** và không thay đổi cú pháp SQL của MySQL. Khi client dùng `$$` làm delimiter, chuỗi `$$` được client dùng để nhận biết kết thúc toàn bộ câu `CREATE`; các dấu `;` nằm bên trong thân routine vẫn được giữ nguyên trong nội dung gửi lên máy chủ.

## 2. Cú pháp và cách đổi delimiter

Trong MySQL command-line client, cú pháp tổng quát là:

```text
DELIMITER chuoi_moi
```

Ví dụ:

```sql
DELIMITER $$
```

Từ thời điểm này, client đợi chuỗi `$$` để gửi câu lệnh hiện tại. Dấu `;` không còn kết thúc câu lệnh ở phía client cho đến khi delimiter được đổi lại.

Sau khi tạo stored program, khôi phục mặc định:

```sql
DELIMITER ;
```

Bạn cũng có thể chọn `//`, `%%` hoặc một chuỗi khác. Hãy chọn chuỗi dễ nhận biết và không xuất hiện trong phần thân routine. `$$` và `//` là hai lựa chọn phổ biến trong ví dụ và tài liệu MySQL.

Lệnh `DELIMITER` được nhập trên dòng riêng trong MySQL client. Không thêm dấu `;` ở cuối chỉ thị này như thể nó là SQL. Tên lệnh không phân biệt chữ hoa/chữ thường trong MySQL client.

## 3. Tạo procedure có nhiều câu lệnh

Giả sử bạn muốn tạo procedure `greet_user`. Procedure này khai báo biến cục bộ, chuẩn hóa tham số đầu vào rồi trả về một thông điệp. Các câu lệnh bên trong đều kết thúc bằng `;`.

```sql
DROP PROCEDURE IF EXISTS greet_user;

DELIMITER $$

CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
BEGIN
    DECLARE v_name VARCHAR(80);

    SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'ban');

    SELECT CONCAT('Xin chao, ', v_name, '!') AS message;
END$$

DELIMITER ;

CALL greet_user('MySQL');
CALL greet_user(NULL);
```

Hãy đọc ví dụ theo thứ tự:

- `DROP PROCEDURE ...;` chạy khi delimiter vẫn là `;`, vì đây là câu lệnh SQL đơn giản.
- `DELIMITER $$` yêu cầu client chờ `$$` mới gửi câu lệnh hiện tại.
- `CREATE PROCEDURE ... BEGIN ... END` là một câu lệnh tạo procedure. Các dấu `;` bên trong kết thúc `DECLARE`, `SET` và `SELECT` theo cú pháp compound statement.
- `END$$` kết thúc phần định nghĩa đối với client. Client gửi toàn bộ câu `CREATE PROCEDURE` cho máy chủ.
- `DELIMITER ;` khôi phục cách nhập SQL thông thường.
- `CALL` chạy procedure đã tạo.

`DELIMITER $$` và `DELIMITER ;` không được lưu trong định nghĩa procedure. Chúng chỉ điều khiển cách client chia đầu vào thành câu lệnh. Máy chủ lưu phần định nghĩa SQL của procedure, bao gồm các dấu phân tách nội bộ cần thiết.

## 4. Vì sao stored program cần delimiter riêng?

Procedure, function và trigger có thể dùng compound statement với `BEGIN ... END`. Bên trong khối này, nhiều câu lệnh SQL được ngăn cách bằng dấu `;`. Một khối điều khiển cũng có thể chứa nhiều phần kết thúc như `END IF;`, `END LOOP;` hoặc một khối `BEGIN ... END` lồng nhau.

Ví dụ thân procedure có điều kiện:

```sql
DELIMITER //

CREATE PROCEDURE classify_amount(IN p_amount DECIMAL(10, 2))
BEGIN
    IF p_amount IS NULL THEN
        SELECT 'Chua co gia tri' AS result;
    ELSEIF p_amount < 0 THEN
        SELECT 'Gia tri am' AS result;
    ELSEIF p_amount = 0 THEN
        SELECT 'Bang khong' AS result;
    ELSE
        SELECT 'Gia tri duong' AS result;
    END IF;
END//

DELIMITER ;

CALL classify_amount(NULL);
CALL classify_amount(-10);
CALL classify_amount(25.50);
```

Trong ví dụ, `END IF;` đóng cấu trúc `IF`, còn `END//` đóng định nghĩa procedure ở phía client. Không thay dấu `;` của `END IF;` bằng `//`; hai ký hiệu này có vai trò khác nhau.

Nếu bạn dùng vòng lặp hoặc khối lồng nhau, quy tắc vẫn như vậy: giữ cú pháp nội bộ của stored program và dùng delimiter riêng để client nhận biết điểm kết thúc của toàn bộ câu `CREATE`.

## 5. Tạo function và trigger

### 5.1. Stored function

Function trả về một giá trị và có thể được dùng trong biểu thức SQL khi đáp ứng các quy tắc của MySQL. Ví dụ dưới đây tính mức giá sau giảm 10%:

```sql
DROP FUNCTION IF EXISTS discounted_amount;

DELIMITER $$

CREATE FUNCTION discounted_amount(p_amount DECIMAL(10, 2))
RETURNS DECIMAL(10, 2)
DETERMINISTIC
NO SQL
BEGIN
    IF p_amount IS NULL OR p_amount < 0 THEN
        RETURN 0;
    END IF;

    RETURN p_amount * 0.90;
END$$

DELIMITER ;

SELECT discounted_amount(100.00) AS amount_after_discount;
```

Trong function, `RETURN` trả kết quả cho biểu thức gọi function. Các câu lệnh và cấu trúc điều khiển trong thân vẫn dùng dấu `;`. Phần `END$$` chỉ là ranh giới kết thúc câu `CREATE FUNCTION` ở client.

### 5.2. Trigger

Trigger thường chứa một hoặc nhiều câu lệnh cần thực hiện khi có thao tác `INSERT`, `UPDATE` hoặc `DELETE` trên bảng. Ví dụ sau ghi nhận một dòng log sau mỗi lần thêm dữ liệu:

```sql
CREATE TABLE IF NOT EXISTS audit_demo (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS audit_demo_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    audit_demo_id BIGINT NOT NULL,
    action_name VARCHAR(10) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

DROP TRIGGER IF EXISTS trg_audit_demo_after_insert;

DELIMITER $$

CREATE TRIGGER trg_audit_demo_after_insert
AFTER INSERT ON audit_demo
FOR EACH ROW
BEGIN
    INSERT INTO audit_demo_log (audit_demo_id, action_name)
    VALUES (NEW.id, 'INSERT');
END$$

DELIMITER ;

INSERT INTO audit_demo (note) VALUES ('Ban ghi thu nghiem');
SELECT * FROM audit_demo_log;
```

Hai câu `CREATE TABLE` và `DROP TRIGGER` ở đầu vẫn dùng delimiter mặc định. Khi bắt đầu định nghĩa trigger, client chuyển sang `$$`; câu `INSERT` trong thân trigger kết thúc bằng `;`, còn `END$$` kết thúc toàn bộ định nghĩa trigger.

## 6. Chạy tệp SQL có stored program

Bạn có thể lưu các câu lệnh tạo routine vào tệp, ví dụ `routines.sql`. Tệp cần chứa cả chỉ thị `DELIMITER` và phần khôi phục delimiter:

```sql
DROP PROCEDURE IF EXISTS greet_user;

DELIMITER $$

CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
BEGIN
    DECLARE v_name VARCHAR(80);
    SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'ban');
    SELECT CONCAT('Xin chao, ', v_name, '!') AS message;
END$$

DELIMITER ;
```

Có hai cách chạy bằng MySQL command-line client cổ điển.

**Cách 1: chuyển hướng tệp vào client từ shell.** Ví dụ:

```bash
mysql --user=labuser --password --database=labdb < routines.sql
```

Client yêu cầu nhập mật khẩu. Khi chạy ở chế độ batch, `mysql` vẫn đọc và xử lý chỉ thị `DELIMITER` trong tệp đầu vào.

**Cách 2: dùng lệnh `source` trong phiên client.** Sau khi kết nối vào đúng database, chạy:

```text
source ./routines.sql
```

Lệnh `source` là lệnh của MySQL client, dùng để đọc và thực thi tệp. Đường dẫn được tính từ thư mục làm việc của tiến trình client.

Sau khi chạy, kiểm tra định nghĩa:

```sql
SHOW CREATE PROCEDURE greet_user\G
```

Lệnh `SHOW CREATE PROCEDURE` cho biết định nghĩa mà máy chủ đang lưu. Phần kết quả không cần chứa các chỉ thị `DELIMITER`, vì chúng không thuộc SQL definition được lưu trên máy chủ.

## 7. Khi dùng GUI, migration tool hoặc driver ứng dụng

`DELIMITER` là chỉ thị riêng của MySQL command-line client cổ điển. Vì vậy, không gửi nguyên dòng `DELIMITER $$` tới máy chủ như một câu SQL. Nếu gửi trực tiếp, máy chủ sẽ báo lỗi cú pháp vì nó không hiểu chỉ thị điều khiển của client.

Khi tạo stored program từ ứng dụng Java, Python hoặc một ứng dụng khác, thông thường bạn gửi toàn bộ câu `CREATE PROCEDURE` hoặc `CREATE TRIGGER` như một đơn vị thực thi qua driver. Chuỗi SQL gửi đi có thể chứa các dấu `;` bên trong thân routine, nhưng không chứa dòng `DELIMITER` và không cần hậu tố `$$`.

Ví dụ minh họa trong Java JDBC:

```java
String sql = """
    CREATE PROCEDURE greet_user(IN p_name VARCHAR(80))
    BEGIN
        DECLARE v_name VARCHAR(80);
        SET v_name = COALESCE(NULLIF(TRIM(p_name), ''), 'ban');
        SELECT CONCAT('Xin chao, ', v_name, '!') AS message;
    END
    """;

try (Statement statement = connection.createStatement()) {
    statement.execute(sql);
}
```

Đây là một lời gọi `execute` với toàn bộ câu `CREATE PROCEDURE`. Driver gửi câu lệnh theo giao thức kết nối; `DELIMITER` không cần thiết. Khi gọi procedure, bạn có thể dùng `CallableStatement` hoặc câu SQL `CALL` tùy nhu cầu ứng dụng.

Một số GUI editor, migration framework hoặc script runner có bộ phân tích tệp riêng. Có công cụ nhận cú pháp `DELIMITER`, có công cụ yêu cầu cấu hình delimiter hoặc gửi từng câu lệnh bằng API. Hãy kiểm tra quy tắc của công cụ đang dùng. Nếu công cụ tự tách tệp ở mọi dấu `;`, nó có thể cắt đôi phần `CREATE` dù server và procedure hoàn toàn hợp lệ.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lỗi cú pháp ngay tại `DECLARE`, `SET` hoặc `IF` khi tạo procedure | Client vẫn dùng `;` và đã gửi phần đầu của thân routine trước khi gặp `END` | Đổi delimiter trước câu `CREATE`, sau đó chạy lại toàn bộ định nghĩa từ đầu |
| Các dòng sau `BEGIN` bị chạy như câu lệnh riêng | Dấu `;` nội bộ đã kết thúc đầu vào ở client | Chọn delimiter khác như `$$` hoặc `//` cho toàn bộ câu `CREATE` |
| `DELIMITER` bị báo lỗi cú pháp từ server | Chỉ thị client đã được gửi tới máy chủ qua driver hoặc công cụ không hỗ trợ cú pháp này | Bỏ dòng `DELIMITER`; cấu hình script runner hoặc gửi toàn bộ câu `CREATE` qua một lần thực thi |
| Các câu SQL tiếp theo không chạy như mong đợi | Client vẫn giữ delimiter tùy chỉnh | Chạy `DELIMITER ;` để khôi phục delimiter mặc định |
| Client đang chờ thêm đầu vào sau khi nhập sai | Câu lệnh hiện tại chưa gặp delimiter kết thúc | Dùng `\c` trong MySQL client để hủy phần đầu vào đang chờ, sau đó đặt lại delimiter |
| Script chạy được trên máy này nhưng lỗi ở công cụ khác | Mỗi công cụ có bộ phân tích script và quy tắc delimiter riêng | Kiểm tra tài liệu công cụ; tách riêng chỉ thị client khỏi SQL gửi qua driver nếu cần |

Một lỗi rất phổ biến là quên khôi phục delimiter. Ví dụ, sau khi chạy `DELIMITER $$`, bạn gõ `SELECT VERSION();` rồi chờ mãi vì client đang đợi `$$`. Chỉ cần nhập:

```sql
DELIMITER ;
```

Nếu client đang giữ một câu lệnh chưa hoàn chỉnh, hãy hủy đầu vào hiện tại bằng `\c` trước rồi mới đổi delimiter.

## 9. Quy trình làm việc khuyến nghị

Khi viết script tạo stored program, hãy áp dụng trình tự sau:

1. Chạy các câu lệnh chuẩn bị như `DROP ... IF EXISTS` hoặc tạo bảng phụ thuộc khi delimiter còn là `;`.
2. Chuyển sang delimiter ít có khả năng xuất hiện trong phần thân, ví dụ `$$`.
3. Viết đầy đủ câu `CREATE` với `BEGIN ... END`; giữ dấu `;` cho từng câu lệnh và cấu trúc điều khiển bên trong.
4. Kết thúc định nghĩa bằng `END$$` (hoặc `END//` nếu đã chọn `//`).
5. Đổi delimiter về `;` ngay sau phần định nghĩa.
6. Gọi procedure, kiểm tra function hoặc thực hiện thao tác kích hoạt trigger.
7. Dùng `SHOW CREATE PROCEDURE`, `SHOW CREATE FUNCTION` hoặc `SHOW CREATE TRIGGER` để xác minh định nghĩa đã được lưu.

Đặt phần tạo stored program thành một khối rõ ràng trong tệp SQL giúp người đọc dễ thấy lúc nào delimiter thay đổi. Nếu tệp tạo nhiều routine liên tiếp, có thể giữ delimiter tùy chỉnh cho cả nhóm, nhưng vẫn cần khôi phục về `;` sau nhóm đó.

## 10. Bài tập thực hành

1. Mở MySQL command-line client, chạy hai câu lệnh đơn giản với delimiter mặc định `;`.
2. Tạo procedure `greet_user` ở phần 3. Gọi procedure với chuỗi bình thường, chuỗi rỗng và `NULL`.
3. Tạo procedure `classify_amount`. Giải thích vai trò riêng của `END IF;` và `END//`.
4. Tạo function `discounted_amount`, gọi function trong một câu `SELECT`, sau đó kiểm tra bằng `SHOW CREATE FUNCTION`.
5. Tạo hai bảng `audit_demo` và `audit_demo_log`, cài trigger rồi chèn một bản ghi. Xác nhận trigger tạo dòng log.
6. Lưu một routine vào `routines.sql` và chạy bằng `source`. Sau đó chạy lại tệp từ shell bằng `mysql` ở chế độ batch.
7. Cố ý bỏ qua bước đổi delimiter, quan sát lỗi hoặc cách client tách câu lệnh; sau đó sửa script và chạy lại.
8. Tạo một lời gọi `Statement.execute()` trong JDBC với toàn bộ câu `CREATE PROCEDURE`. Giải thích vì sao không đưa `DELIMITER` vào chuỗi SQL gửi qua driver.

## 11. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích rằng `DELIMITER` điều khiển cách MySQL client chia đầu vào, còn máy chủ phân tích cú pháp stored program; tạo được procedure, function và trigger có nhiều câu lệnh; chạy được tệp SQL trong chế độ tương tác hoặc batch; khôi phục delimiter về `;`; và biết cách xử lý khi công cụ chạy script không hỗ trợ chỉ thị `DELIMITER`.
