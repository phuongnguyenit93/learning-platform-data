# IF, CASE, LOOP, WHILE, REPEAT và LEAVE/ITERATE

Stored program cho phép đóng gói nhiều câu lệnh SQL thành một đơn vị được lưu trên MySQL Server. Ngoài việc thực hiện truy vấn và cập nhật dữ liệu, stored program còn cần quyết định nhánh xử lý, lặp qua một dãy bước và thoát sớm khi đạt điều kiện. MySQL cung cấp các cấu trúc điều khiển IF, CASE, LOOP, WHILE, REPEAT, LEAVE và ITERATE cho mục đích này.

Chọn đúng cấu trúc điều khiển giúp routine dễ đọc, tránh vòng lặp vô hạn và xử lý rõ các trường hợp NULL. Bài này tập trung vào cú pháp, ngữ nghĩa, cách kết hợp và các lỗi thường gặp khi dùng những cấu trúc đó trong stored procedure, stored function, trigger và event.

## 1. Flow control trong stored program

MySQL hỗ trợ các cấu trúc điều khiển sau trong stored program:

| Cấu trúc | Vai trò |
|---|---|
| IF | Chọn nhánh theo một hoặc nhiều điều kiện |
| CASE | Chọn nhánh theo giá trị hoặc điều kiện |
| LOOP | Lặp không có điều kiện kiểm tra ở đầu/cuối; thường kết thúc bằng LEAVE |
| WHILE | Lặp khi điều kiện ở đầu vòng lặp còn đúng |
| REPEAT | Chạy thân vòng lặp rồi mới kiểm tra điều kiện kết thúc |
| LEAVE | Thoát khỏi block hoặc vòng lặp được gắn nhãn |
| ITERATE | Bỏ phần còn lại của lượt hiện tại và bắt đầu lượt tiếp theo |

Các cấu trúc có thể lồng nhau. Ví dụ, một IF có thể nằm trong WHILE, còn CASE có thể nằm trong LOOP. MySQL không hỗ trợ vòng lặp FOR; nếu cần lặp theo bộ đếm, thường dùng WHILE, REPEAT hoặc LOOP.

Các cấu trúc này nằm trong thân stored program, thường là một compound statement BEGIN ... END. Chúng không phải cú pháp điều khiển của một câu SELECT thông thường, dù SQL cũng có biểu thức CASE và hàm IF() có thể dùng trực tiếp trong câu truy vấn.

## 2. Khung BEGIN ... END, biến cục bộ và DELIMITER

Ví dụ một procedure đơn giản:

```sql
DELIMITER //

CREATE PROCEDURE show_message(IN p_name VARCHAR(100))
BEGIN
    DECLARE v_message VARCHAR(150) DEFAULT '';

    SET v_message = CONCAT('Xin chao, ', p_name);
    SELECT v_message AS message;
END//

DELIMITER ;
```

BEGIN ... END gom nhiều câu lệnh thành một compound statement. Mỗi câu lệnh bên trong vẫn kết thúc bằng dấu chấm phẩy (;).

### 2.1. Vì sao cần DELIMITER?

Trong MySQL command-line client, dấu chấm phẩy mặc định kết thúc một lệnh gửi đến server. Nếu dùng dấu chấm phẩy bên trong procedure, client có thể gửi phần thân routine quá sớm. Lệnh DELIMITER // tạm đổi ký hiệu kết thúc lệnh ở phía client; sau khi định nghĩa routine xong, DELIMITER ; khôi phục mặc định.

DELIMITER là lệnh của client, không phải câu SQL được thực thi bởi server. Khi dùng driver hoặc API gửi câu CREATE PROCEDURE, thường gửi toàn bộ câu lệnh định nghĩa như một statement theo cách driver hỗ trợ; không gửi dòng DELIMITER như SQL.

### 2.2. Khai báo và phạm vi biến

Biến cục bộ được khai báo bằng DECLARE ở đầu block BEGIN ... END, trước các câu lệnh thực thi:

```sql
BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_total DECIMAL(12,2) DEFAULT 0.00;

    SET v_count = 10;
    SET v_total = 125.50;
END
```

- Nếu không khai báo DEFAULT, giá trị ban đầu của biến cục bộ là NULL.
- Phạm vi của biến là block nơi biến được khai báo và các block lồng bên trong, trừ khi block con khai báo biến trùng tên.
- Mỗi block lồng có thể khai báo biến riêng ở đầu block đó.
- Dùng SET để gán giá trị cho biến cục bộ.

Nên đặt tên biến có tiền tố như v_ và tên tham số có tiền tố p_ để tránh nhầm với tên cột trong SQL.

## 3. Điều kiện Boolean và giá trị NULL

Điều kiện của IF, CASE, WHILE và REPEAT là một search condition. Trong logic SQL có ba trạng thái:

| Kết quả điều kiện | Ý nghĩa |
|---|---|
| TRUE | Điều kiện đúng |
| FALSE | Điều kiện sai |
| UNKNOWN (NULL) | Không xác định vì có giá trị NULL tham gia |

Điểm quan trọng: chỉ điều kiện đánh giá thành TRUE mới chọn nhánh THEN hoặc làm điều kiện lặp được xem là đúng. FALSE và UNKNOWN không được xem là TRUE.

Ví dụ:

```sql
IF p_amount > 100 THEN
    SET v_level = 'HIGH';
ELSE
    SET v_level = 'NORMAL';
END IF;
```

Nếu p_amount là NULL, biểu thức p_amount > 100 không phải TRUE, nên nhánh ELSE chạy. Nếu nghiệp vụ muốn phân biệt giá trị thiếu với giá trị thấp, phải kiểm tra NULL trước:

```sql
IF p_amount IS NULL THEN
    SET v_level = 'UNKNOWN';
ELSEIF p_amount > 100 THEN
    SET v_level = 'HIGH';
ELSE
    SET v_level = 'NORMAL';
END IF;
```

Các phép so sánh với NULL bằng = hoặc <> không phải cách kiểm tra NULL. Dùng IS NULL hoặc IS NOT NULL.

## 4. IF statement

IF chọn một nhánh theo điều kiện. Cú pháp:

```sql
IF search_condition THEN
    statement_list
[ELSEIF search_condition THEN
    statement_list] ...
[ELSE
    statement_list]
END IF;
```

ELSEIF là một từ khóa viết liền, không phải ELSE IF. Mỗi nhánh phải có ít nhất một câu lệnh; không để một statement_list rỗng.

### 4.1. IF ... THEN ... ELSE

```sql
DELIMITER //

CREATE PROCEDURE classify_payment(
    IN p_amount DECIMAL(12,2),
    OUT p_result VARCHAR(20)
)
BEGIN
    IF p_amount IS NULL THEN
        SET p_result = 'UNKNOWN';
    ELSEIF p_amount <= 0 THEN
        SET p_result = 'INVALID';
    ELSE
        SET p_result = 'VALID';
    END IF;
END//

DELIMITER ;
```

Gọi procedure:

```sql
CALL classify_payment(250.00, @result);
SELECT @result;
```

Procedure trả VALID. Nếu truyền NULL, kết quả là UNKNOWN; nếu truyền số 0 hoặc số âm, kết quả là INVALID.

### 4.2. Nhiều nhánh ELSEIF

Khi phân loại theo khoảng giá trị, đặt các điều kiện theo thứ tự rõ ràng:

```sql
IF p_score IS NULL THEN
    SET p_grade = 'NOT_GRADED';
ELSEIF p_score < 0 OR p_score > 100 THEN
    SET p_grade = 'OUT_OF_RANGE';
ELSEIF p_score >= 90 THEN
    SET p_grade = 'A';
ELSEIF p_score >= 80 THEN
    SET p_grade = 'B';
ELSEIF p_score >= 65 THEN
    SET p_grade = 'C';
ELSE
    SET p_grade = 'D';
END IF;
```

MySQL kiểm tra từ trên xuống và thực thi nhánh đầu tiên có điều kiện TRUE. Vì vậy, điều kiện biên và thứ tự nhánh có ý nghĩa. Nếu đưa p_score >= 65 lên trước p_score >= 90, điểm 95 sẽ bị xếp loại C.

### 4.3. IF lồng nhau

Có thể đặt một IF bên trong nhánh của IF khác:

```sql
IF p_status = 'ACTIVE' THEN
    IF p_balance > 0 THEN
        SET p_message = 'ACTIVE_WITH_BALANCE';
    ELSE
        SET p_message = 'ACTIVE_NO_BALANCE';
    END IF;
ELSE
    SET p_message = 'INACTIVE';
END IF;
```

Mỗi IF phải có END IF riêng. Với nhiều nhánh điều kiện độc lập, ELSEIF thường dễ đọc hơn nhiều tầng IF lồng nhau.

### 4.4. Khi nào dùng IF?

Dùng IF khi cần:

- Kiểm tra điều kiện đầu vào hoặc trường hợp NULL.
- Phân loại theo nhiều điều kiện có thể khác nhau.
- Kết hợp các điều kiện AND, OR, NOT.
- Thực hiện một nhánh rồi tiếp tục các câu lệnh sau END IF.

## 5. CASE statement

CASE statement là cấu trúc rẽ nhánh nhiều lựa chọn trong stored program. Có hai dạng: simple CASE so sánh một biểu thức với các giá trị và searched CASE đánh giá từng điều kiện.

### 5.1. Simple CASE

Cú pháp:

```sql
CASE case_value
    WHEN when_value THEN
        statement_list
    [WHEN when_value THEN
        statement_list] ...
    [ELSE
        statement_list]
END CASE;
```

Ví dụ phân loại trạng thái:

```sql
DELIMITER //

CREATE PROCEDURE describe_order_status(
    IN p_status VARCHAR(20),
    OUT p_description VARCHAR(100)
)
BEGIN
    CASE p_status
        WHEN 'NEW' THEN
            SET p_description = 'Cho xu ly';
        WHEN 'PAID' THEN
            SET p_description = 'Da thanh toan';
        WHEN 'SHIPPED' THEN
            SET p_description = 'Dang giao hang';
        WHEN 'CANCELLED' THEN
            SET p_description = 'Da huy';
        ELSE
            SET p_description = 'Trang thai khong xac dinh';
    END CASE;
END//

DELIMITER ;
```

Simple CASE so sánh case_value với từng when_value. Nhánh khớp đầu tiên được thực thi; nếu không nhánh nào khớp, ELSE được thực thi nếu có.

### 5.2. Searched CASE

Searched CASE không so sánh một giá trị chung; mỗi WHEN có thể là một điều kiện độc lập:

```sql
CASE
    WHEN p_total IS NULL THEN
        SET p_tier = 'UNKNOWN';
    WHEN p_total < 0 THEN
        SET p_tier = 'INVALID';
    WHEN p_total >= 10000000 THEN
        SET p_tier = 'PLATINUM';
    WHEN p_total >= 5000000 THEN
        SET p_tier = 'GOLD';
    WHEN p_total >= 1000000 THEN
        SET p_tier = 'SILVER';
    ELSE
        SET p_tier = 'STANDARD';
END CASE;
```

Các điều kiện được đánh giá theo thứ tự; nhánh đầu tiên TRUE sẽ chạy. Giống IF, hãy đặt điều kiện đặc biệt như IS NULL và điều kiện biên trước các nhánh tổng quát hơn.

### 5.3. CASE không có ELSE

Khác với IF, nếu không có WHEN nào khớp và CASE statement không có ELSE, MySQL phát sinh lỗi Case not found for CASE statement. Vì vậy, khi đầu vào có thể chứa giá trị ngoài dự kiến, nên viết ELSE rõ ràng:

```sql
CASE p_status
    WHEN 'NEW' THEN
        SET p_message = 'New order';
    WHEN 'PAID' THEN
        SET p_message = 'Paid order';
    ELSE
        SET p_message = 'Other status';
END CASE;
```

Nếu thực sự không cần làm gì khi không có nhánh khớp, có thể dùng ELSE chứa một compound block rỗng:

```sql
CASE p_status
    WHEN 'NEW' THEN
        SET p_message = 'New order';
    ELSE
        BEGIN
        END;
END CASE;
```

CASE statement không hỗ trợ ELSE NULL như CASE expression. Cách rõ ràng hơn trong hầu hết nghiệp vụ là gán một trạng thái mặc định.

### 5.4. Không dùng simple CASE để kiểm tra NULL

Không viết:

```sql
CASE p_status
    WHEN NULL THEN
        SET p_message = 'Missing';
    ELSE
        SET p_message = 'Present';
END CASE;
```

So sánh NULL = NULL không cho kết quả TRUE, nên nhánh WHEN NULL không bắt được giá trị NULL. Dùng searched CASE:

```sql
CASE
    WHEN p_status IS NULL THEN
        SET p_message = 'Missing';
    WHEN p_status = 'NEW' THEN
        SET p_message = 'New';
    ELSE
        SET p_message = 'Other';
END CASE;
```

### 5.5. CASE statement khác CASE expression

Hai cú pháp có mục đích khác nhau:

| CASE statement | CASE expression |
|---|---|
| Dùng để điều khiển câu lệnh trong stored program | Trả về một giá trị trong biểu thức SQL |
| Có statement_list sau THEN | Có biểu thức kết quả sau THEN |
| Kết thúc bằng END CASE | Kết thúc bằng END |
| Không có ELSE và không nhánh nào khớp thì phát sinh lỗi | Không có ELSE và không nhánh nào khớp thì trả về NULL |

Ví dụ CASE expression trong truy vấn:

```sql
SELECT
    order_id,
    CASE
        WHEN total_amount >= 1000000 THEN 'HIGH'
        WHEN total_amount > 0 THEN 'NORMAL'
        ELSE 'ZERO_OR_INVALID'
    END AS amount_group
FROM orders;
```

Tương tự, IF ... END IF là IF statement trong stored program, còn IF(condition, value_if_true, value_if_false) là hàm IF() trả về một giá trị trong biểu thức SQL.

## 6. LOOP statement

LOOP lặp lại danh sách câu lệnh mà không có điều kiện kiểm tra sẵn ở đầu hoặc cuối. Thân vòng lặp thường tự kiểm tra điều kiện và dùng LEAVE để kết thúc.

Cú pháp:

```sql
[begin_label:] LOOP
    statement_list
END LOOP [end_label];
```

Nếu không có đường đi nào thực hiện LEAVE hoặc cách kết thúc hợp lệ khác, LOOP có thể chạy vô hạn.

### 6.1. Ví dụ tính tổng từ 1 đến N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_loop(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_n IS NULL OR p_n < 1 THEN
        SET p_sum = 0;
    ELSE
        sum_loop: LOOP
            IF v_i > p_n THEN
                LEAVE sum_loop;
            END IF;

            SET v_total = v_total + v_i;
            SET v_i = v_i + 1;
        END LOOP sum_loop;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Gọi thử:

```sql
CALL sum_to_loop(5, @total);
SELECT @total AS total; -- 15
```

Luồng thực thi:

1. Khởi tạo v_i = 1, v_total = 0.
2. Kiểm tra v_i > p_n.
3. Nếu đúng, LEAVE sum_loop thoát khỏi vòng lặp.
4. Nếu sai, cộng v_i vào tổng rồi tăng bộ đếm.
5. Quay lại đầu LOOP.

Kiểm tra điều kiện kết thúc trước khi xử lý giúp tránh cộng thêm một giá trị vượt giới hạn.

### 6.2. Khi nào dùng LOOP?

Dùng LOOP khi điều kiện thoát nằm ở giữa thân vòng lặp hoặc có nhiều điểm có thể kết thúc. Nếu điều kiện tiếp tục đơn giản và luôn kiểm tra ở đầu, WHILE thường dễ đọc hơn.

## 7. WHILE statement

WHILE kiểm tra điều kiện trước mỗi lượt. Thân vòng lặp chỉ chạy khi điều kiện TRUE.

Cú pháp:

```sql
[begin_label:] WHILE search_condition DO
    statement_list
END WHILE [end_label];
```

Nếu điều kiện FALSE hoặc UNKNOWN ngay từ đầu, thân vòng lặp không chạy lần nào.

### 7.1. Ví dụ tính tổng từ 1 đến N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_while(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    WHILE v_i <= p_n DO
        SET v_total = v_total + v_i;
        SET v_i = v_i + 1;
    END WHILE;

    SET p_sum = v_total;
END//

DELIMITER ;
```

Ví dụ:

```sql
CALL sum_to_while(5, @total);
SELECT @total AS total; -- 15
```

Với p_n bằng 0 hoặc số âm, điều kiện 1 <= p_n sai và kết quả bằng 0. Với p_n là NULL, điều kiện không TRUE nên thân vòng lặp cũng không chạy; tuy vậy, nếu nghiệp vụ cần phân biệt NULL với 0, hãy kiểm tra NULL tường minh thay vì để hai trường hợp cùng trả kết quả.

### 7.2. Tránh vòng lặp không tiến triển

Mỗi lượt phải làm thay đổi trạng thái để điều kiện cuối cùng có thể trở thành FALSE:

```sql
WHILE v_i <= p_n DO
    -- Xu ly cong viec
    SET v_i = v_i + 1;
END WHILE;
```

Nếu quên tăng v_i, điều kiện vẫn đúng và procedure có thể chạy mãi. Với vòng lặp phụ thuộc nhiều biến, kiểm tra tất cả biến tham gia điều kiện.

## 8. REPEAT statement

REPEAT thực hiện thân vòng lặp trước, sau đó mới kiểm tra điều kiện UNTIL. Vì vậy, thân vòng lặp luôn chạy ít nhất một lần.

Cú pháp:

```sql
[begin_label:] REPEAT
    statement_list
UNTIL search_condition
END REPEAT [end_label];
```

Vòng lặp kết thúc khi search_condition TRUE. Nếu điều kiện FALSE hoặc UNKNOWN, vòng tiếp theo bắt đầu.

### 8.1. Ví dụ tính tổng từ 1 đến N

```sql
DELIMITER //

CREATE PROCEDURE sum_to_repeat(
    IN p_n INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 1;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_n IS NULL OR p_n < 1 THEN
        SET p_sum = 0;
    ELSE
        REPEAT
            SET v_total = v_total + v_i;
            SET v_i = v_i + 1;
        UNTIL v_i > p_n
        END REPEAT;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Gọi thử:

```sql
CALL sum_to_repeat(5, @total);
SELECT @total AS total; -- 15
```

Với p_n = 1, thân vòng lặp chạy một lần, cộng 1, tăng v_i thành 2 rồi điều kiện 2 > 1 kết thúc vòng.

### 8.2. Vì sao cần kiểm tra đầu vào trước REPEAT?

Nếu bỏ IF p_n IS NULL OR p_n < 1, thân REPEAT vẫn chạy ít nhất một lần. Khi p_n = 0, ví dụ có thể cộng 1 dù kết quả mong đợi là 0. Với đầu vào NULL, điều kiện UNTIL có thể không bao giờ TRUE nếu biến điều khiển không được cập nhật phù hợp.

Hãy kiểm tra điều kiện tiền đề trước khi vào REPEAT nếu không được phép thực hiện ngay cả một lượt.

## 9. So sánh LOOP, WHILE và REPEAT

| Tiêu chí | LOOP | WHILE | REPEAT |
|---|---|---|---|
| Kiểm tra điều kiện | Do người viết đặt trong thân | Trước thân | Sau thân |
| Số lượt tối thiểu | 1 lượt vào thân trước khi LEAVE; nếu không có LEAVE có thể vô hạn | 0 | 1 |
| Cách kết thúc thường dùng | LEAVE label | Điều kiện WHILE thành FALSE/UNKNOWN hoặc LEAVE | Điều kiện UNTIL thành TRUE hoặc LEAVE |
| Phù hợp | Nhiều điểm thoát hoặc điều kiện thoát ở giữa thân | Lặp khi một điều kiện còn đúng | Phải chạy ít nhất một lần rồi mới kiểm tra |
| Rủi ro thường gặp | Quên LEAVE | Không cập nhật biến điều kiện | Không bao giờ đạt UNTIL hoặc quên kiểm tra tiền đề |

Có thể viết cùng một thuật toán bằng cả ba dạng. Chọn dạng thể hiện rõ nhất thời điểm kiểm tra điều kiện, không chọn chỉ vì cú pháp ngắn hơn.

## 10. LEAVE statement

LEAVE label thoát khỏi cấu trúc điều khiển được gắn nhãn:

```sql
LEAVE loop_label;
```

LEAVE có thể dùng trong:

- LOOP
- WHILE
- REPEAT
- Block BEGIN ... END có nhãn

Nếu nhãn thuộc block ngoài cùng của stored program, LEAVE thoát khỏi block chương trình đó.

Ví dụ thoát sớm khỏi block:

```sql
DELIMITER //

CREATE PROCEDURE validate_code(
    IN p_code VARCHAR(20),
    OUT p_message VARCHAR(50)
)
main: BEGIN
    IF p_code IS NULL OR p_code = '' THEN
        SET p_message = 'MISSING_CODE';
        LEAVE main;
    END IF;

    SET p_message = 'VALID_CODE';
END main//

DELIMITER ;
```

Khi đầu vào không hợp lệ, LEAVE main rời block có nhãn main, bỏ qua câu lệnh gán VALID_CODE.

LEAVE không phải là lệnh thoát khỏi mọi vòng lặp một cách tự động. Nó cần nhãn hợp lệ để xác định chính xác cấu trúc cần thoát.

## 11. ITERATE statement

ITERATE label bỏ qua phần còn lại của lượt hiện tại và bắt đầu lượt tiếp theo của vòng lặp được gắn nhãn:

```sql
ITERATE loop_label;
```

ITERATE chỉ được dùng trong LOOP, WHILE và REPEAT. Không dùng ITERATE để nhảy tới đầu một block BEGIN ... END.

### 11.1. Ví dụ cộng các số lẻ từ 1 đến N

```sql
DELIMITER //

CREATE PROCEDURE sum_odd_numbers(
    IN p_limit INT,
    OUT p_sum BIGINT
)
BEGIN
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_total BIGINT DEFAULT 0;

    IF p_limit IS NULL OR p_limit < 1 THEN
        SET p_sum = 0;
    ELSE
        odd_loop: LOOP
            SET v_i = v_i + 1;

            IF v_i > p_limit THEN
                LEAVE odd_loop;
            END IF;

            IF MOD(v_i, 2) = 0 THEN
                ITERATE odd_loop;
            END IF;

            SET v_total = v_total + v_i;
        END LOOP odd_loop;

        SET p_sum = v_total;
    END IF;
END//

DELIMITER ;
```

Gọi thử:

```sql
CALL sum_odd_numbers(7, @odd_total);
SELECT @odd_total AS odd_total; -- 16 (1 + 3 + 5 + 7)
```

Khi v_i là số chẵn, ITERATE odd_loop quay về đầu vòng và bỏ qua câu lệnh cộng tổng. Bộ đếm được tăng trước ITERATE, do đó vòng lặp vẫn tiến triển.

### 11.2. Thứ tự cập nhật trạng thái

Đây là lỗi dễ gặp:

```sql
IF MOD(v_i, 2) = 0 THEN
    ITERATE odd_loop;
END IF;

SET v_i = v_i + 1;
```

Nếu v_i là số chẵn, ITERATE bỏ qua lệnh tăng phía dưới. Vòng tiếp theo lại gặp đúng giá trị chẵn đó và lặp mãi. Hãy cập nhật bộ đếm trước ITERATE, hoặc đặt lệnh tăng ở vị trí luôn được thực thi.

## 12. Nhãn và vòng lặp lồng nhau

Nhãn có thể gắn cho BEGIN ... END, LOOP, WHILE và REPEAT. Cú pháp:

```sql
label_name: LOOP
    statement_list
END LOOP label_name;
```

Quy tắc nhãn:

- Nhãn mở đầu phải có dấu hai chấm (:).
- Nhãn kết thúc là tùy chọn, nhưng nếu có thì phải giống nhãn mở đầu.
- Không thể có nhãn kết thúc nếu không có nhãn mở đầu.
- Các nhãn ở cùng mức lồng nhau phải khác nhau.
- Tên nhãn dài tối đa 16 ký tự.

Ví dụ vòng lặp lồng nhau:

```sql
DELIMITER //

CREATE PROCEDURE count_pairs(
    IN p_outer_limit INT,
    IN p_inner_limit INT,
    OUT p_count BIGINT
)
BEGIN
    DECLARE v_outer INT DEFAULT 1;
    DECLARE v_inner INT DEFAULT 1;
    DECLARE v_count BIGINT DEFAULT 0;

    WHILE v_outer <= p_outer_limit DO
        SET v_inner = 1;

        inner_loop: WHILE v_inner <= p_inner_limit DO
            SET v_count = v_count + 1;
            SET v_inner = v_inner + 1;
        END WHILE inner_loop;

        SET v_outer = v_outer + 1;
    END WHILE;

    SET p_count = v_count;
END//

DELIMITER ;
```

Với p_outer_limit = 3 và p_inner_limit = 2, procedure đếm 6 cặp.

Trong vòng lặp lồng nhau:

- LEAVE inner_loop chỉ thoát vòng lặp trong.
- LEAVE outer_loop thoát vòng lặp ngoài nếu nhãn đó nằm trong phạm vi hợp lệ.
- ITERATE inner_loop chỉ bắt đầu lượt tiếp theo của vòng lặp trong.
- ITERATE outer_loop bắt đầu lượt tiếp theo của vòng lặp ngoài; các câu lệnh còn lại của lượt ngoài hiện tại, bao gồm phần xử lý sau vòng trong, sẽ bị bỏ qua.

Đặt tên nhãn ngắn, mô tả đúng vai trò và tránh dùng cùng tên ở cùng mức lồng nhau.

## 13. Kết hợp IF, CASE và vòng lặp

Trong thực tế, một routine có thể dùng nhiều cấu trúc cùng lúc. Ví dụ dưới đây duyệt một dãy số, bỏ qua số chia hết cho 3 và phân loại các số còn lại:

```sql
DELIMITER //

CREATE PROCEDURE summarize_numbers(
    IN p_limit INT,
    OUT p_small_count INT,
    OUT p_large_count INT
)
BEGIN
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_small INT DEFAULT 0;
    DECLARE v_large INT DEFAULT 0;

    IF p_limit IS NULL OR p_limit < 1 THEN
        SET p_small_count = 0;
        SET p_large_count = 0;
    ELSE
        number_loop: WHILE v_i < p_limit DO
            SET v_i = v_i + 1;

            IF MOD(v_i, 3) = 0 THEN
                ITERATE number_loop;
            END IF;

            CASE
                WHEN v_i < 10 THEN
                    SET v_small = v_small + 1;
                ELSE
                    SET v_large = v_large + 1;
            END CASE;
        END WHILE number_loop;

        SET p_small_count = v_small;
        SET p_large_count = v_large;
    END IF;
END//

DELIMITER ;
```

Với giới hạn 12, các số được xét là 1, 2, 4, 5, 7, 8, 10, 11. Kết quả: 6 số nhỏ hơn 10 và 2 số từ 10 trở lên.

Ví dụ cho thấy:

1. IF xử lý đầu vào không hợp lệ.
2. WHILE điều khiển số lượt.
3. ITERATE bỏ qua các số chia hết cho 3.
4. CASE phân loại số còn lại.

Khi kết hợp nhiều cấu trúc, thụt lề và tên nhãn nhất quán giúp tránh nhầm lẫn về phạm vi của END IF, END CASE, END WHILE và END LOOP.

## 14. Chọn cấu trúc điều khiển phù hợp

| Nhu cầu | Cấu trúc nên cân nhắc | Lý do |
|---|---|---|
| Một điều kiện hoặc vài nhánh khác nhau | IF | Diễn đạt điều kiện tổng quát |
| Nhiều lựa chọn theo cùng một giá trị | Simple CASE | Không lặp lại biểu thức so sánh |
| Nhiều điều kiện độc lập | Searched CASE | Mỗi nhánh có search condition riêng |
| Lặp khi điều kiện còn đúng ngay từ đầu | WHILE | Có thể chạy 0 lần |
| Phải thực hiện ít nhất một lượt | REPEAT | Kiểm tra điều kiện sau thân |
| Nhiều điểm thoát hoặc kiểm tra giữa thân | LOOP + LEAVE | Chủ động kiểm soát điểm kết thúc |
| Bỏ qua phần còn lại của một lượt | ITERATE | Chuyển ngay sang lượt tiếp theo |
| Dừng một block có nhãn | LEAVE block_label | Thoát block, không cần lồng thêm IF |

Đừng dùng vòng lặp để thay thế một câu SQL tập hợp đơn giản. Ví dụ, nếu cần tăng giá trị cho mọi hàng thỏa điều kiện, thường nên dùng một câu UPDATE ... WHERE thay vì lặp từng ID rồi cập nhật từng hàng. Vòng lặp phù hợp hơn khi mỗi bước phụ thuộc kết quả bước trước hoặc cần điều phối một chuỗi thao tác có giới hạn rõ.

## 15. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| IF không vào nhánh mong đợi | Điều kiện trả về FALSE hoặc UNKNOWN do NULL | Kiểm tra NULL bằng IS NULL trước |
| ELSEIF bị lỗi cú pháp | Viết thành ELSE IF hoặc thiếu THEN | Dùng đúng từ khóa ELSEIF ... THEN |
| Thiếu END IF | Nhánh IF chưa được đóng | Mỗi IF có đúng một END IF |
| CASE phát sinh Case not found | Không nhánh nào khớp và không có ELSE | Thêm nhánh ELSE phù hợp |
| WHEN NULL không khớp | So sánh NULL bằng phép bằng không trả TRUE | Dùng searched CASE với IS NULL |
| CASE statement lỗi tại END | Dùng nhầm kết thúc của CASE expression | Dùng END CASE cho statement |
| LOOP chạy mãi | Không có LEAVE hoặc biến điều khiển không thay đổi | Xác định điều kiện thoát và cập nhật biến |
| WHILE không chạy lần nào | Điều kiện đầu tiên FALSE hoặc UNKNOWN | Kiểm tra giá trị đầu vào và điều kiện khởi tạo |
| REPEAT chạy thêm một lượt | REPEAT luôn chạy thân trước khi kiểm tra UNTIL | Kiểm tra tiền đề trước khi vào vòng |
| REPEAT không kết thúc | Điều kiện UNTIL không bao giờ TRUE | Kiểm tra biến điều khiển và điều kiện dừng |
| ITERATE gây vòng lặp vô hạn | Lệnh cập nhật biến bị bỏ qua sau ITERATE | Cập nhật trạng thái trước ITERATE |
| LEAVE/ITERATE không tìm thấy nhãn | Nhãn sai tên hoặc không nằm trong phạm vi | Kiểm tra nhãn mở đầu/kết thúc và phạm vi |
| Dùng ITERATE với block BEGIN | ITERATE chỉ dùng cho LOOP/WHILE/REPEAT | Dùng LEAVE cho block hoặc đặt vòng lặp có nhãn |
| Client báo lỗi ngay giữa CREATE PROCEDURE | Client dùng ; để tách routine body | Đổi delimiter ở client hoặc gửi routine như một statement hoàn chỉnh qua driver |
| Lỗi do khai báo biến | DECLARE nằm sau câu lệnh thực thi | Chuyển DECLARE lên đầu block tương ứng |

## 16. Nguyên tắc an toàn và hiệu năng khi dùng vòng lặp

### 16.1. Luôn xác định điều kiện kết thúc

Trước khi viết loop, ghi rõ:

- Biến nào điều khiển vòng lặp?
- Giá trị khởi tạo là gì?
- Câu lệnh nào làm biến thay đổi?
- Điều kiện nào kết thúc vòng?
- Điều gì xảy ra khi đầu vào là NULL, 0 hoặc số âm?

Với LOOP, luôn xác định một đường đi có thể tới LEAVE. Với WHILE, kiểm tra điều kiện đầu vào. Với REPEAT, nhớ thân vòng lặp luôn chạy ít nhất một lần.

### 16.2. Giới hạn số lần lặp

Nếu đầu vào điều khiển số lượt, xác thực miền giá trị trước khi bắt đầu. Tránh để một tham số bất thường tạo hàng triệu hoặc hàng tỷ vòng lặp ngoài dự kiến.

### 16.3. Ưu tiên xử lý theo tập hợp

Các thao tác như cập nhật nhiều hàng, tính tổng hoặc phân loại hàng thường có thể làm bằng một câu SQL tập hợp:

```sql
UPDATE orders
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND created_at < CURRENT_DATE - INTERVAL 30 DAY;
```

Cách này thường hiệu quả hơn lặp qua từng hàng và thực hiện một UPDATE riêng cho mỗi hàng. Chỉ dùng loop khi thật sự cần điều khiển từng bước, chia batch hoặc phối hợp các thao tác phụ thuộc nhau.

### 16.4. Chú ý phạm vi biến và dữ liệu NULL

Biến cục bộ không có DEFAULT bắt đầu bằng NULL. Một phép cộng như v_total = v_total + v_value sẽ cho kết quả NULL nếu một toán hạng là NULL. Khởi tạo bộ đếm và tổng bằng 0; kiểm tra dữ liệu đầu vào hoặc dùng hàm xử lý NULL phù hợp với nghiệp vụ.

### 16.5. Giữ phần thân dễ kiểm tra

- Mỗi nhánh chỉ làm một nhóm công việc rõ ràng.
- Tránh lồng quá nhiều cấp IF/CASE/LOOP.
- Đặt nhãn theo mục đích, không đặt tên chung chung như l1, l2.
- Đặt câu lệnh tăng bộ đếm ở vị trí không bị bỏ qua ngoài ý muốn.
- Dùng comment để giải thích điều kiện thoát không hiển nhiên.

## 17. Quy trình kiểm thử routine có flow control

Trước khi triển khai routine, kiểm tra tối thiểu:

1. Nhánh đúng thông thường.
2. Nhánh biên bằng đúng ngưỡng.
3. Nhánh dưới và trên ngưỡng.
4. Đầu vào NULL.
5. Đầu vào 0 hoặc số âm nếu tham số là số.
6. CASE nhận giá trị không có trong danh sách WHEN.
7. Vòng lặp chạy 0 lần, 1 lần và nhiều lần.
8. Nhánh ITERATE có cập nhật biến trước khi quay lại đầu vòng.
9. Nhánh LEAVE thoát đúng vòng/block mong muốn.
10. Vòng lặp lồng nhau không vô tình thoát nhầm cấp.

Ví dụ bộ kiểm thử cho sum_to_while:

| Tham số p_n | Kết quả mong đợi | Điều cần xác nhận |
|---:|---:|---|
| NULL | 0 theo ví dụ hiện tại | Điều kiện WHILE UNKNOWN không vào thân |
| -1 | 0 | Điều kiện ban đầu FALSE |
| 0 | 0 | Không có lượt lặp |
| 1 | 1 | Một lượt |
| 5 | 15 | Nhiều lượt |

Với routine nghiệp vụ thực tế, có thể cần trả trạng thái riêng cho NULL thay vì gộp NULL với 0. Bộ kiểm thử phải phản ánh chính sách đó.

## 18. Bài tập thực hành

### Bài 1 — Phân loại điểm bằng IF

Viết procedure nhận p_score và trả p_grade:

- NULL: NOT_GRADED
- Ngoài khoảng 0 đến 100: INVALID
- Từ 90: A
- Từ 80 đến dưới 90: B
- Từ 65 đến dưới 80: C
- Còn lại: D

Kiểm tra lần lượt các giá trị NULL, -1, 0, 64, 65, 79, 80, 89, 90, 100 và 101.

### Bài 2 — Chuyển trạng thái bằng CASE

Viết procedure nhận mã trạng thái đơn hàng và trả mô tả. Dùng simple CASE cho các giá trị NEW, PAID, SHIPPED, CANCELLED, có ELSE cho mã lạ. Sau đó viết lại bằng searched CASE để xử lý riêng giá trị NULL.

### Bài 3 — Tính tổng bằng ba loại vòng lặp

Viết ba procedure tương đương dùng LOOP, WHILE và REPEAT để tính tổng từ 1 đến N. Kiểm tra N bằng 0, 1 và 10. So sánh vị trí kiểm tra điều kiện dừng trong từng cách viết.

### Bài 4 — Cộng số lẻ với ITERATE

Viết procedure cộng các số lẻ từ 1 đến N. Dùng ITERATE để bỏ qua số chẵn và LEAVE để dừng khi vượt N. Kiểm tra bộ đếm vẫn tăng ở mọi lượt.

### Bài 5 — Thoát block có nhãn

Viết procedure kiểm tra mã đầu vào. Nếu mã NULL hoặc rỗng, gán thông báo lỗi nghiệp vụ vào OUT parameter rồi LEAVE block ngoài cùng. Nếu hợp lệ, tiếp tục xử lý và gán thông báo thành công.

## 19. Checklist trước khi hoàn tất stored program

- Dùng đúng IF ... END IF và CASE ... END CASE?
- Đã phân biệt IF statement với hàm IF() chưa?
- Đã phân biệt CASE statement với CASE expression chưa?
- Các điều kiện NULL đã được xử lý theo nghiệp vụ chưa?
- CASE statement có ELSE cho trường hợp không khớp chưa?
- Mọi biến cục bộ đã được DECLARE ở đầu block và khởi tạo hợp lý chưa?
- LOOP có đường đi chắc chắn tới LEAVE không?
- WHILE có điều kiện khởi đầu đúng không?
- REPEAT có xử lý việc thân luôn chạy ít nhất một lần không?
- ITERATE có bỏ qua lệnh cập nhật biến cần thiết không?
- LEAVE/ITERATE tham chiếu đúng nhãn và đúng cấp lồng nhau không?
- Tên nhãn có tối đa 16 ký tự và không trùng ở cùng mức không?
- Mọi block đã đóng bằng đúng từ khóa END tương ứng chưa?
- DELIMITER có được dùng đúng ở client không?
- Có thể thay một loop bằng câu SQL tập hợp đơn giản hơn không?
- Đã kiểm tra các trường hợp biên và NULL chưa?

## 20. Tài liệu tham khảo chính thức

- [MySQL 9.7 — Flow Control Statements](https://dev.mysql.com/doc/refman/9.7/en/flow-control-statements.html)
- [MySQL 9.7 — IF Statement](https://dev.mysql.com/doc/refman/9.7/en/if.html)
- [MySQL 9.7 — CASE Statement](https://dev.mysql.com/doc/refman/9.7/en/case.html)
- [MySQL 9.7 — LOOP Statement](https://dev.mysql.com/doc/refman/9.7/en/loop.html)
- [MySQL 9.7 — WHILE Statement](https://dev.mysql.com/doc/refman/9.7/en/while.html)
- [MySQL 9.7 — REPEAT Statement](https://dev.mysql.com/doc/refman/9.7/en/repeat.html)
- [MySQL 9.7 — LEAVE Statement](https://dev.mysql.com/doc/refman/9.7/en/leave.html)
- [MySQL 9.7 — ITERATE Statement](https://dev.mysql.com/doc/refman/9.7/en/iterate.html)
- [MySQL 9.7 — Statement Labels](https://dev.mysql.com/doc/refman/9.7/en/statement-labels.html)
- [MySQL 9.7 — Local Variable DECLARE Statement](https://dev.mysql.com/doc/refman/9.7/en/declare-local-variable.html)
- [MySQL 9.7 — BEGIN ... END Compound Statement](https://dev.mysql.com/doc/refman/9.7/en/begin-end.html)
- [MySQL 8.0 — Flow Control Statements](https://dev.mysql.com/doc/refman/8.0/en/flow-control-statements.html)

## Kết luận

IF và CASE điều khiển nhánh; LOOP, WHILE và REPEAT điều khiển việc lặp; LEAVE thoát khỏi block hoặc vòng lặp có nhãn, còn ITERATE bắt đầu lượt tiếp theo của một vòng lặp. Điểm khác biệt quan trọng giữa các vòng lặp là thời điểm kiểm tra điều kiện: WHILE kiểm tra trước thân, REPEAT kiểm tra sau thân và luôn chạy ít nhất một lần, còn LOOP cần một đường thoát được thiết kế rõ. Khi viết stored program, phải xử lý NULL tường minh, khai báo biến đúng vị trí, dùng nhãn hợp lệ và bảo đảm biến điều khiển tiến triển để tránh vòng lặp vô hạn. Với thao tác dữ liệu hàng loạt, ưu tiên câu SQL theo tập hợp nếu có thể thay thế loop một cách rõ ràng và an toàn.
