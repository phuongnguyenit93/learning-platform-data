# SQLSTATE, mã lỗi MySQL và condition có tên

Khi một câu lệnh SQL thất bại, MySQL cung cấp nhiều thông tin để xác định nguyên nhân: SQLSTATE, mã lỗi số của MySQL và thông điệp mô tả. Ba thông tin này có quan hệ với nhau nhưng không thay thế cho nhau. SQLSTATE mô tả nhóm lỗi theo quy ước SQL; mã lỗi số nhận diện lỗi cụ thể trong MySQL; thông điệp giải thích tình huống bằng ngôn ngữ dễ đọc hơn.

Trong stored program, có thể dùng các giá trị đó trực tiếp trong handler hoặc khai báo condition có tên để mã nguồn dễ hiểu. Condition có tên giúp thay các mã số khó nhớ hoặc SQLSTATE lặp lại bằng một tên nghiệp vụ rõ ràng. Khi cần phát sinh lỗi do nghiệp vụ tự định nghĩa, dùng SIGNAL với một SQLSTATE phù hợp; khi cần đọc lỗi vừa xảy ra, dùng GET DIAGNOSTICS.

Bài này tập trung vào cấu trúc SQLSTATE, cách phân biệt SQLSTATE với MySQL error code, các mã thường gặp, khai báo và phạm vi condition có tên, cách kết hợp condition với handler, SIGNAL/RESIGNAL và đọc thông tin lỗi trong diagnostics area.

## 1. Ba thành phần nhận diện lỗi

Khi MySQL phát sinh một condition, các thông tin quan trọng gồm:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| SQLSTATE | Mã trạng thái gồm 5 ký tự, biểu diễn nhóm/tình trạng SQL | 23000, 42000, 45000 |
| MySQL error code | Số nguyên riêng của MySQL để nhận diện lỗi cụ thể | 1062, 1064, 1213 |
| MESSAGE_TEXT | Thông điệp mô tả lỗi | Duplicate entry, syntax error |

Ví dụ, khi INSERT một giá trị trùng unique key, MySQL thường trả:

- SQLSTATE: 23000
- MySQL error code: 1062
- Message: Duplicate entry ...

SQLSTATE 23000 biểu thị vi phạm ràng buộc toàn vẹn. Mã 1062 cụ thể hơn: duplicate key. Vì vậy, một ứng dụng có thể xử lý theo SQLSTATE khi chỉ cần biết đây là lỗi integrity constraint, hoặc theo mã 1062 khi cần phân biệt duplicate key với các lỗi integrity khác.

Không nên phân tích chuỗi MESSAGE_TEXT để quyết định logic nghiệp vụ. Nội dung thông điệp có thể thay đổi theo phiên bản, ngôn ngữ, tên bảng/cột và dữ liệu đầu vào. Hãy dùng SQLSTATE hoặc MySQL error code để định tuyến xử lý; dùng MESSAGE_TEXT chủ yếu cho log và chẩn đoán.

## 2. SQLSTATE có cấu trúc như thế nào?

SQLSTATE là chuỗi gồm đúng 5 ký tự. Hai ký tự đầu xác định class, ba ký tự cuối xác định subclass trong class đó.

```text
SQLSTATE = CC SSS
            |  |
            |  +-- Subclass: chi tiết trạng thái trong class
            +----- Class: nhóm trạng thái
```

Ví dụ:

- 23000: class 23, integrity constraint violation.
- 42000: class 42, syntax error or access rule violation.
- 40001: class 40, transaction rollback.
- 02000: class 02, no data.
- 45000: class 45, user-defined exception trong MySQL.

SQLSTATE là mã ký tự, không phải số nguyên. Khi so sánh hoặc khai báo, đặt trong dấu nháy đơn:

```sql
DECLARE duplicate_state CONDITION
    FOR SQLSTATE '23000';
```

Không bỏ số 0 ở đầu. Ví dụ 02000 phải được giữ nguyên đủ 5 ký tự.

### 2.1. Các class thường gặp

| Class | Tên nhóm | Tình huống thường gặp |
|---|---|---|
| 00 | Successful completion | Câu lệnh hoàn tất thành công |
| 01 | Warning | Câu lệnh hoàn tất nhưng có cảnh báo |
| 02 | No data | Không có hàng hoặc không tìm thấy dữ liệu; thường gặp khi FETCH cursor đã hết hàng |
| 08 | Connection exception | Lỗi kết nối |
| 21 | Cardinality violation | Vi phạm số lượng hàng/giá trị theo ngữ cảnh |
| 22 | Data exception | Lỗi dữ liệu hoặc chuyển đổi dữ liệu |
| 23 | Integrity constraint violation | Vi phạm primary key, unique key, foreign key hoặc constraint |
| 24 | Invalid cursor state | Trạng thái cursor không hợp lệ |
| 25 | Invalid transaction state | Trạng thái transaction không hợp lệ |
| 28 | Invalid authorization specification | Thông tin xác thực hoặc quyền không hợp lệ |
| 40 | Transaction rollback | Transaction bị rollback, ví dụ deadlock |
| 42 | Syntax error or access rule violation | Lỗi cú pháp hoặc quy tắc truy cập |
| HY | General error | Nhóm lỗi chung do implementation cung cấp |

Đây là các class tiêu biểu để định hướng chẩn đoán, không phải danh sách đầy đủ mọi SQLSTATE. Khi cần biết chính xác trạng thái của một lỗi cụ thể, hãy lấy giá trị thực tế từ diagnostics area hoặc tài liệu MySQL.

### 2.2. Ba class đặc biệt trong khai báo handler

MySQL cung cấp ba shorthand condition class thường dùng trong DECLARE HANDLER:

| Shorthand | Phạm vi |
|---|---|
| SQLWARNING | Các condition thuộc class 01 |
| NOT FOUND | Các condition thuộc class 02 |
| SQLEXCEPTION | Các class khác ngoài 00, 01 và 02 |

Ví dụ:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

Trong xử lý cursor, NOT FOUND thường được dùng để nhận biết FETCH không còn hàng. Handler này là cách viết gọn cho nhóm condition class 02; nó không có nghĩa mọi trường hợp dữ liệu rỗng trong mọi câu SELECT đều tạo ra cùng một hành vi.

### 2.3. SQLSTATE 00000 và SQLSTATE 45000

00000 biểu thị successful completion, không phải lỗi. Không dùng SQLSTATE class 00 để phát sinh lỗi bằng SIGNAL.

45000 là SQLSTATE tổng quát dành cho user-defined exception trong MySQL. Đây là lựa chọn thường dùng khi routine cần báo một vi phạm nghiệp vụ mà không tương ứng trực tiếp với một lỗi server cụ thể:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'So tien phai lon hon 0';
```

Ứng dụng có thể nhận SQLSTATE 45000 và thông điệp do routine cung cấp để xử lý theo hợp đồng đã thống nhất.

## 3. MySQL error code là gì?

MySQL error code là số nguyên nhận diện một lỗi cụ thể do server phát sinh. Các mã này được công bố trong Server Error Reference và thường có tên symbolic như ER_DUP_ENTRY hoặc ER_PARSE_ERROR trong mã nguồn/tài liệu MySQL.

Ví dụ một số mã phổ biến:

| MySQL error code | Tên lỗi thường dùng | SQLSTATE thường đi kèm | Ý nghĩa |
|---:|---|---|---|
| 1062 | ER_DUP_ENTRY | 23000 | Giá trị duplicate trong unique index |
| 1048 | ER_BAD_NULL_ERROR | 23000 | Gán NULL cho cột NOT NULL |
| 1452 | ER_NO_REFERENCED_ROW_2 | 23000 | Không tìm thấy hàng parent cho foreign key |
| 1064 | ER_PARSE_ERROR | 42000 | Cú pháp SQL không hợp lệ |
| 1054 | ER_BAD_FIELD_ERROR | 42S22 | Không có cột được tham chiếu |
| 1146 | ER_NO_SUCH_TABLE | 42S02 | Bảng không tồn tại |
| 1213 | ER_LOCK_DEADLOCK | 40001 | Transaction bị chọn làm nạn nhân deadlock |

Các cặp trên là ví dụ điển hình của MySQL. Khi cần chẩn đoán một lỗi thực tế, hãy lấy cả SQLSTATE và MYSQL_ERRNO từ chính phiên bản server đang chạy, không suy luận chỉ từ câu thông báo.

### 3.1. Vì sao cần cả SQLSTATE và error code?

SQLSTATE có tính khái quát và thuận tiện khi muốn xử lý theo nhóm lỗi. MySQL error code có độ cụ thể cao hơn nhưng gắn với implementation MySQL.

Ví dụ:

- Bắt SQLSTATE 23000 có thể bao quát nhiều lỗi integrity constraint.
- Bắt error code 1062 chỉ nhắm đến duplicate key.
- Bắt SQLSTATE 40001 giúp nhận diện transaction rollback theo nhóm serialization/deadlock.
- Bắt error code 1213 nhắm tới deadlock do MySQL báo.

Chọn mức cụ thể theo nhu cầu. Nếu logic cần phản ứng khác nhau với duplicate key và foreign key violation, dùng error code cụ thể hoặc tách condition cụ thể. Nếu mọi lỗi integrity đều có cùng cách xử lý, có thể cân nhắc SQLSTATE phù hợp.

### 3.2. Không coi SQLSTATE là mã số MySQL

SQLSTATE và MySQL error code có kiểu và miền giá trị khác nhau:

```sql
-- Khai bao theo SQLSTATE: chuoi 5 ky tu
DECLARE integrity_error CONDITION
    FOR SQLSTATE '23000';

-- Khai bao theo MySQL error code: so nguyen
DECLARE duplicate_key CONDITION
    FOR 1062;
```

Không viết SQLSTATE 1062 và cũng không viết FOR '1062' để biểu diễn mã lỗi MySQL. Dùng đúng dạng chuỗi SQLSTATE hoặc số nguyên error code.

## 4. Condition có tên là gì?

Condition có tên là một tên do người viết routine khai báo để đại diện cho một SQLSTATE hoặc một MySQL error code. Cú pháp:

```sql
DECLARE condition_name CONDITION
    FOR condition_value;
```

Trong đó condition_value có một trong hai dạng:

```sql
SQLSTATE [VALUE] 'sqlstate_value'
```

hoặc:

```sql
mysql_error_code
```

Ví dụ:

```sql
DECLARE no_data CONDITION
    FOR SQLSTATE '02000';

DECLARE duplicate_key CONDITION
    FOR 1062;
```

Sau khi khai báo, có thể dùng tên condition trong phần khai báo handler:

```sql
DECLARE CONTINUE HANDLER FOR no_data
    SET v_done = TRUE;

DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

Condition có tên giúp routine dễ đọc hơn. Người bảo trì có thể hiểu duplicate_key là lỗi duplicate key mà không cần ghi nhớ mã 1062 ở mọi nơi.

## 5. Khai báo condition theo SQLSTATE

Khi muốn xử lý theo nhóm trạng thái SQL hoặc phát sinh lỗi nghiệp vụ, khai báo condition theo SQLSTATE:

```sql
DECLARE invalid_amount CONDITION
    FOR SQLSTATE '45000';
```

Condition này có thể được dùng trong handler:

```sql
DECLARE EXIT HANDLER FOR invalid_amount
BEGIN
    SET p_result = 'INVALID_AMOUNT';
END;
```

Nó cũng có thể được dùng với SIGNAL để phát sinh condition tương ứng:

```sql
SIGNAL invalid_amount
    SET MESSAGE_TEXT = 'Amount must be greater than zero';
```

Đối với SIGNAL và RESIGNAL, condition name phải được khai báo và gắn với một SQLSTATE. Condition name được khai báo theo MySQL error code chỉ dùng để nhận diện condition khi khai báo handler; không dùng nó như condition SQLSTATE để phát sinh bằng SIGNAL.

### 5.1. SQLSTATE VALUE là tùy chọn

Hai cách sau tương đương:

```sql
DECLARE invalid_amount CONDITION
    FOR SQLSTATE '45000';

DECLARE invalid_amount CONDITION
    FOR SQLSTATE VALUE '45000';
```

Từ khóa VALUE là tùy chọn. Dùng dạng có VALUE hoặc không có VALUE nhất quán trong cùng codebase.

## 6. Khai báo condition theo MySQL error code

Khi cần xử lý một lỗi MySQL cụ thể, khai báo condition theo số nguyên:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
```

Sau đó dùng tên condition trong handler:

```sql
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

Điều này tương đương khai báo handler trực tiếp theo mã lỗi:

```sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate = TRUE;
```

Condition có tên làm rõ ý nghĩa và tránh lặp mã số. Cách dùng số trực tiếp vẫn hợp lệ, nhưng routine lớn thường dễ bảo trì hơn khi condition được đặt tên.

### 6.1. Một error code không phải một class SQLSTATE

Ví dụ 1062 tương ứng SQLSTATE 23000, nhưng không có nghĩa SQLSTATE 23000 chỉ đại diện cho lỗi 1062. Nhiều lỗi integrity có thể dùng cùng SQLSTATE class/value theo quy tắc server.

Nếu khai báo:

```sql
DECLARE integrity_violation CONDITION
    FOR SQLSTATE '23000';
```

handler cho integrity_violation xử lý condition có SQLSTATE chính xác 23000. Nếu cần xử lý mọi trạng thái trong class 23, MySQL không cho khai báo wildcard kiểu 23xxx bằng DECLARE CONDITION; hãy chọn các SQLSTATE cụ thể hoặc thiết kế handler theo yêu cầu thực tế.

## 7. Vị trí DECLARE và phạm vi condition

Condition được khai báo trong phần declaration của một compound block BEGIN ... END. Tất cả khai báo phải đặt trước câu lệnh thực thi của block.

Thứ tự khai báo trong một block:

1. Biến cục bộ và condition.
2. Cursor.
3. Handler.

Ví dụ:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE no_data CONDITION
        FOR SQLSTATE '02000';
    DECLARE duplicate_key CONDITION
        FOR 1062;

    DECLARE cur_orders CURSOR FOR
        SELECT id FROM orders;

    DECLARE CONTINUE HANDLER FOR no_data
        SET v_done = TRUE;

    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    -- Cac cau lenh thuc thi bat dau tu day
END
```

Không đặt DECLARE CONDITION sau một câu SET, SELECT hoặc INSERT. Không đặt khai báo handler trước khai báo cursor.

### 7.1. Phạm vi tên condition

Condition có phạm vi trong block nơi nó được khai báo và các block lồng bên trong. Một block khác bên ngoài không tự động nhìn thấy tên được khai báo chỉ trong block con.

Ví dụ:

```sql
main: BEGIN
    DECLARE duplicate_key CONDITION FOR 1062;

    BEGIN
        DECLARE CONTINUE HANDLER FOR duplicate_key
            SET v_duplicate = TRUE;

        -- Block con co the tham chieu condition cua block cha
    END;
END main
```

Condition khai báo ở block cha có thể được tham chiếu trong block con nằm trong phạm vi. Nên đặt tên condition khác nhau giữa các block lồng nhau để việc đọc và xử lý handler không gây nhầm lẫn.

## 8. Kết hợp condition có tên với handler

Condition có tên chỉ định danh condition. Bản thân câu DECLARE CONDITION không xử lý lỗi. Muốn xử lý condition, phải khai báo handler.

Ví dụ bắt duplicate key:

```sql
DELIMITER //

CREATE PROCEDURE add_customer(
    IN p_email VARCHAR(255),
    OUT p_result VARCHAR(30)
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_key CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    INSERT INTO customers(email)
    VALUES (p_email);

    IF v_duplicate THEN
        SET p_result = 'DUPLICATE';
    ELSE
        SET p_result = 'CREATED';
    END IF;
END//

DELIMITER ;
```

Khi INSERT phát sinh error 1062, CONTINUE handler đặt v_duplicate thành TRUE rồi tiếp tục sau câu INSERT. IF sau đó gán kết quả phù hợp.

Lưu ý: handler theo 1062 bắt mọi duplicate-key violation phát sinh trong phạm vi handler, không riêng email nếu bảng có nhiều unique key. Nếu cần giới hạn phạm vi, đặt INSERT trong một block con và khai báo handler ở block con đó. Nếu routine cần trả lỗi thay vì chuyển thành trạng thái, dùng EXIT handler hoặc RESIGNAL theo hợp đồng đã thiết kế.

### 8.1. Phân biệt CONTINUE và EXIT

| Loại handler | Sau khi handler chạy |
|---|---|
| CONTINUE | Tiếp tục thực thi ở vị trí sau câu lệnh gây condition |
| EXIT | Thoát khỏi block BEGIN ... END chứa handler |

Condition có tên không quyết định CONTINUE hay EXIT. Hành vi này được quyết định bởi loại handler được khai báo.

## 9. Condition có tên cho lỗi nghiệp vụ

Có thể định nghĩa condition với SQLSTATE 45000 để routine báo lỗi đầu vào:

```sql
DELIMITER //

CREATE PROCEDURE create_payment(
    IN p_amount DECIMAL(12,2)
)
BEGIN
    DECLARE invalid_amount CONDITION
        FOR SQLSTATE '45000';

    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL invalid_amount
            SET MESSAGE_TEXT = 'Payment amount must be positive';
    END IF;

    INSERT INTO payments(amount)
    VALUES (p_amount);
END//

DELIMITER ;
```

Khi đầu vào không hợp lệ, SIGNAL phát sinh lỗi SQLSTATE 45000 cùng MESSAGE_TEXT. Câu INSERT không được thực hiện sau SIGNAL trong luồng xử lý bình thường.

Không nên dùng SQLSTATE 00000 để báo lỗi. Cũng không nên chọn SQLSTATE hệ thống cụ thể của một lỗi khác chỉ để tận dụng mã có sẵn nếu routine đang báo một vi phạm nghiệp vụ riêng.

## 10. SIGNAL và RESIGNAL

SIGNAL chủ động phát sinh một condition. Có thể chỉ định SQLSTATE trực tiếp hoặc condition name đã khai báo theo SQLSTATE:

```sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Business rule rejected the operation';
```

Hoặc:

```sql
DECLARE invalid_state CONDITION
    FOR SQLSTATE '45000';

SIGNAL invalid_state
    SET MESSAGE_TEXT = 'Business rule rejected the operation';
```

RESIGNAL được dùng bên trong handler để phát sinh lại condition đã kích hoạt handler hoặc phát sinh lại với một số thông tin được thay đổi:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    -- Ghi nhan thong tin hoac thuc hien cleanup
    RESIGNAL;
END;
```

Nếu không thay đổi condition, RESIGNAL giúp caller tiếp tục nhận lỗi gốc. Nếu sửa MESSAGE_TEXT hoặc một số signal information item, caller nhận condition đã được điều chỉnh theo nội dung RESIGNAL.

### 10.1. Không nhầm SIGNAL với DECLARE CONDITION

| Câu lệnh | Chức năng |
|---|---|
| DECLARE ... CONDITION | Đặt tên cho SQLSTATE hoặc MySQL error code |
| DECLARE ... HANDLER | Đăng ký hành vi khi condition xảy ra |
| SIGNAL | Chủ động phát sinh condition |
| RESIGNAL | Phát sinh lại condition trong handler |

Khai báo condition không tự phát sinh lỗi và cũng không tự bắt lỗi. Cần chọn đúng câu lệnh cho từng mục đích.

## 11. Đọc thông tin lỗi bằng GET DIAGNOSTICS

Sau khi một câu lệnh tạo condition, MySQL lưu thông tin trong diagnostics area. GET DIAGNOSTICS dùng để đọc các trường trong khu vực này.

Ba trường quan trọng khi điều tra lỗi:

| Diagnostics item | Thông tin |
|---|---|
| RETURNED_SQLSTATE | SQLSTATE của condition |
| MYSQL_ERRNO | MySQL error code |
| MESSAGE_TEXT | Thông điệp lỗi |

Trong handler, GET STACKED DIAGNOSTICS đọc diagnostics area được lưu khi handler được kích hoạt:

```sql
GET STACKED DIAGNOSTICS CONDITION 1
    v_sqlstate = RETURNED_SQLSTATE,
    v_mysql_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;
```

GET STACKED DIAGNOSTICS chỉ được dùng khi đang ở trong handler. GET CURRENT DIAGNOSTICS đọc diagnostics area hiện tại; các câu lệnh tiếp theo trong handler có thể tạo thêm condition, vì vậy STACKED thường phù hợp khi cần lấy lại condition đã kích hoạt handler.

### 11.1. Ví dụ thu thập lỗi rồi RESIGNAL

```sql
DELIMITER //

CREATE PROCEDURE insert_payment(
    IN p_amount DECIMAL(12,2),
    OUT p_sqlstate CHAR(5),
    OUT p_mysql_errno INT,
    OUT p_message VARCHAR(128)
)
BEGIN
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_mysql_errno INT;
    DECLARE v_message VARCHAR(128);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET STACKED DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_mysql_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        SET p_sqlstate = v_sqlstate;
        SET p_mysql_errno = v_mysql_errno;
        SET p_message = v_message;

        RESIGNAL;
    END;

    INSERT INTO payments(amount)
    VALUES (p_amount);
END//

DELIMITER ;
```

Handler đọc condition gây lỗi trước khi chạy các câu lệnh khác, gán ba thông tin vào OUT parameters rồi RESIGNAL để caller vẫn nhận lỗi. Tùy client/driver và cách CALL kết thúc bằng lỗi, việc đọc OUT parameters sau một CALL thất bại có thể khác nhau; nếu ứng dụng cần hợp đồng kết quả ổn định, hãy kiểm tra hành vi của driver và cân nhắc trả thông tin qua logging/observability ở tầng phù hợp.

### 11.2. Diagnostics area có nhiều condition

Một câu lệnh có thể tạo nhiều warning hoặc condition. Statement information item NUMBER cho biết số condition trong diagnostics area; ROW_COUNT cho biết số hàng bị ảnh hưởng theo ngữ cảnh câu lệnh.

Ví dụ đọc số condition:

```sql
GET DIAGNOSTICS
    v_condition_count = NUMBER,
    v_row_count = ROW_COUNT;
```

Để đọc condition cụ thể, dùng:

```sql
GET DIAGNOSTICS CONDITION 1
    v_sqlstate = RETURNED_SQLSTATE,
    v_mysql_errno = MYSQL_ERRNO,
    v_message = MESSAGE_TEXT;
```

Condition number là chỉ số trong diagnostics area. Khi câu lệnh có nhiều warning/error, không giả định condition 1 luôn là mọi thông tin bạn cần; đọc NUMBER và chọn condition phù hợp với mục đích chẩn đoán.

## 12. Chọn mức bắt lỗi: error code, SQLSTATE hay shorthand?

| Cách khai báo | Khi nên dùng |
|---|---|
| MySQL error code, ví dụ 1062 | Chỉ xử lý một lỗi MySQL cụ thể |
| SQLSTATE cụ thể, ví dụ 23000 | Xử lý một trạng thái SQL cụ thể |
| SQLWARNING | Xử lý nhóm warning class 01 |
| NOT FOUND | Xử lý nhóm no-data class 02, thường dùng với cursor |
| SQLEXCEPTION | Xử lý nhóm lỗi còn lại, khi không cần phân biệt chi tiết |
| Condition có tên | Khi muốn mã nguồn diễn đạt ý nghĩa và tái sử dụng condition |

Ví dụ:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate = TRUE;
```

So với:

```sql
DECLARE CONTINUE HANDLER FOR 1062
    SET v_duplicate = TRUE;
```

Hai cách xử lý cùng error code. Dạng condition có tên dễ đọc hơn khi routine có nhiều handler hoặc condition được dùng ở nhiều vị trí.

## 13. Các tình huống thực tế

### 13.1. Duplicate key

Tình huống: ứng dụng tạo tài khoản với email đã tồn tại.

- MySQL error code thường gặp: 1062.
- SQLSTATE thường gặp: 23000.
- Cách xử lý: trả trạng thái duplicate hoặc chuyển thành lỗi nghiệp vụ riêng.

Không nên bắt toàn bộ SQLEXCEPTION rồi trả DUPLICATE vì có thể che giấu lỗi kết nối, cú pháp, deadlock hoặc lỗi dữ liệu khác.

### 13.2. Foreign key violation

Tình huống: thêm order với customer_id không tồn tại.

- MySQL error code thường gặp: 1452.
- SQLSTATE thường gặp: 23000.
- Cách xử lý: trả lỗi tham chiếu không hợp lệ hoặc kiểm tra lại dữ liệu đầu vào.

SQLSTATE 23000 giống ví dụ duplicate key, nhưng error code khác. Nếu nghiệp vụ cần phân biệt hai trường hợp, dùng mã lỗi cụ thể.

### 13.3. Bảng hoặc cột không tồn tại

Ví dụ:

- 1146 / 42S02: table không tồn tại.
- 1054 / 42S22: unknown column.

Những lỗi này thường cho thấy schema, migration hoặc câu SQL không đồng bộ. Không nên chuyển chúng thành thông báo “không tìm thấy dữ liệu” vì đây là lỗi cấu trúc hoặc triển khai.

### 13.4. Deadlock

MySQL error code 1213 thường đi kèm SQLSTATE 40001. Transaction bị chọn làm nạn nhân cần được retry theo chính sách có giới hạn, với toàn bộ transaction được thực hiện lại từ đầu.

Không retry chỉ riêng câu UPDATE gây lỗi nếu transaction trước đó đã bị rollback. Cần thiết kế retry có backoff, giới hạn số lần và bảo đảm thao tác có tính idempotent phù hợp.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| SQLSTATE và error code là một | SQLSTATE là chuỗi 5 ký tự; MySQL error code là số nguyên |
| Một SQLSTATE chỉ có một MySQL error code | Nhiều lỗi cụ thể có thể chia sẻ cùng SQLSTATE |
| 23000 chỉ là duplicate key | Đây là trạng thái integrity constraint; có thể gặp foreign key violation và lỗi khác |
| MESSAGE_TEXT ổn định để ứng dụng parse | Message phụ thuộc phiên bản, dữ liệu và ngôn ngữ; không dùng làm khóa logic |
| DECLARE CONDITION tự bắt lỗi | Nó chỉ đặt tên; cần DECLARE HANDLER để xử lý |
| Condition gắn với error code có thể SIGNAL trực tiếp | Condition name dùng với SIGNAL/RESIGNAL phải gắn với SQLSTATE |
| SQLSTATE 00000 dùng để phát sinh lỗi thành công | 00000 là successful completion, không dùng để báo lỗi bằng SIGNAL |
| SQLSTATE 23xxx là wildcard hợp lệ | DECLARE CONDITION yêu cầu SQLSTATE cụ thể; không có wildcard theo class |
| NOT FOUND chỉ có nghĩa bảng rỗng | Đây là condition class 02; thường gặp khi FETCH cursor không còn hàng |
| GET DIAGNOSTICS và GET STACKED DIAGNOSTICS giống nhau | STACKED đọc diagnostics area đã kích hoạt handler; chỉ dùng trong handler |
| Bắt SQLEXCEPTION luôn là cách an toàn nhất | Handler quá rộng có thể che giấu lỗi cần được caller xử lý riêng |

## 15. Checklist thiết kế condition và handler

- Đã xác định cần xử lý theo SQLSTATE hay MySQL error code cụ thể chưa?
- Có cần phân biệt các lỗi cùng SQLSTATE nhưng khác error code không?
- Tên condition có diễn đạt đúng ý nghĩa lỗi không?
- Condition có được khai báo trong đúng block và trước handler không?
- Các khai báo biến/condition, cursor và handler có đúng thứ tự không?
- Condition name dùng với SIGNAL có được gắn với SQLSTATE không?
- SQLSTATE có đúng 5 ký tự và không phải class 00 khi phát sinh lỗi không?
- Handler là CONTINUE hay EXIT có đúng hành vi mong muốn không?
- Có đang bắt SQLEXCEPTION quá rộng và vô tình che lỗi không?
- Có dùng MESSAGE_TEXT để log thay vì parse logic không?
- Trong handler, đã lấy diagnostics bằng GET STACKED DIAGNOSTICS trước khi chạy câu lệnh khác chưa?
- Có ghi lại RETURNED_SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT khi cần chẩn đoán không?
- Nếu xử lý deadlock, retry có thực hiện lại toàn bộ transaction không?
- Đã kiểm thử duplicate key, foreign key violation, NULL, no data và lỗi không dự kiến chưa?

## 16. Bài tập thực hành

### Bài 1 — Đọc SQLSTATE và MySQL error code

Cho các trường hợp: duplicate key, foreign key violation, syntax error, unknown table và deadlock. Tra cứu SQLSTATE, MySQL error code và mô tả tương ứng trong MySQL Server Error Reference. Ghi rõ trường hợp nào chia sẻ SQLSTATE.

### Bài 2 — Đặt tên condition

Viết procedure thêm một khách hàng. Khai báo condition duplicate_key cho error code 1062 và handler phù hợp. Trả trạng thái DUPLICATE khi email bị trùng; trả CREATED khi INSERT thành công.

### Bài 3 — Phát sinh lỗi nghiệp vụ

Viết procedure nhận số tiền. Khai báo invalid_amount cho SQLSTATE 45000. Dùng SIGNAL invalid_amount khi giá trị NULL hoặc không dương; đặt MESSAGE_TEXT dễ hiểu.

### Bài 4 — Lấy diagnostics

Viết EXIT handler cho SQLEXCEPTION. Dùng GET STACKED DIAGNOSTICS để đọc RETURNED_SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT, sau đó RESIGNAL lỗi gốc.

### Bài 5 — Chọn phạm vi handler

Một routine có thể gặp duplicate key, foreign key violation và deadlock. Đề xuất condition có tên và handler phù hợp cho từng lỗi; giải thích trường hợp nào nên trả lỗi cho caller và trường hợp nào có thể chuyển thành trạng thái nghiệp vụ.

## 17. Tài liệu tham khảo chính thức

- [MySQL 9.7 — Condition Handling](https://dev.mysql.com/doc/refman/9.7/en/condition-handling.html)
- [MySQL 9.7 — DECLARE ... CONDITION](https://dev.mysql.com/doc/refman/9.7/en/declare-condition.html)
- [MySQL 9.7 — DECLARE ... HANDLER](https://dev.mysql.com/doc/refman/9.7/en/declare-handler.html)
- [MySQL 9.7 — SIGNAL Statement](https://dev.mysql.com/doc/refman/9.7/en/signal.html)
- [MySQL 9.7 — RESIGNAL Statement](https://dev.mysql.com/doc/refman/9.7/en/resignal.html)
- [MySQL 9.7 — GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/9.7/en/get-diagnostics.html)
- [MySQL 9.7 — Server Error Reference](https://dev.mysql.com/doc/mysql-errors/9.7/en/server-error-reference.html)
- [MySQL 9.7 — Error Message Elements](https://dev.mysql.com/doc/mysql-errors/9.7/en/error-message-elements.html)
- [MySQL 8.0 — Condition Handling](https://dev.mysql.com/doc/refman/8.0/en/condition-handling.html)

## Kết luận

SQLSTATE, MySQL error code và MESSAGE_TEXT cung cấp ba mức thông tin khác nhau về condition. SQLSTATE gồm 5 ký tự và phân loại theo class/subclass; error code là số nguyên riêng của MySQL để nhận diện lỗi cụ thể; MESSAGE_TEXT dùng để đọc và ghi log. DECLARE CONDITION đặt tên cho SQLSTATE hoặc error code để handler dễ đọc hơn, nhưng bản thân nó không bắt lỗi. Dùng SIGNAL để phát sinh lỗi nghiệp vụ với SQLSTATE phù hợp, RESIGNAL để chuyển tiếp lỗi trong handler và GET STACKED DIAGNOSTICS để lấy condition đã kích hoạt handler. Chọn phạm vi bắt lỗi đủ cụ thể, tránh parse thông điệp và luôn giữ lại thông tin SQLSTATE/error code để chẩn đoán và xử lý đúng.
