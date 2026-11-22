# DECLARE: thứ tự khai báo biến, condition, cursor và handler

Trong stored program của MySQL, `DECLARE` dùng để khai báo các thành phần cục bộ của một block `BEGIN ... END`: biến, condition có tên, cursor và handler. Các khai báo này phải xuất hiện ở đầu block, trước những câu lệnh thực thi. Ngoài vị trí khai báo, **thứ tự giữa các nhóm cũng có quy tắc**: khai báo biến và condition trước, cursor sau đó, handler cuối cùng.

Thứ tự này giúp MySQL biết kiểu dữ liệu và điều kiện mà routine sử dụng trước khi biên dịch phần xử lý cursor/handler. Một lỗi đặt `DECLARE` sau `SET`, `SELECT`, `IF` hoặc `OPEN` sẽ làm routine không tạo được. Khi cần khai báo thành phần ở giữa luồng xử lý, hãy tạo một block `BEGIN ... END` lồng nhau và đặt các `DECLARE` ở đầu block con.

Bài học tập trung vào cú pháp, thứ tự, phạm vi và cách phối hợp bốn loại khai báo. Ví dụ cursor chỉ nhằm minh họa vị trí `DECLARE CURSOR` và handler `NOT FOUND`; hãy ưu tiên SQL set-based khi có thể xử lý toàn bộ tập dữ liệu bằng một câu lệnh.

## 1. DECLARE thuộc về một block BEGIN ... END

Stored procedure, function, trigger và event có thể có compound statement:

```sql
BEGIN
    -- Khai báo cục bộ nằm ở đây.

    -- Sau nhóm DECLARE mới đến câu lệnh thực thi.
    SET @example_value = 1;
END
```

Mỗi block `BEGIN ... END` có phạm vi khai báo riêng. Phần thân routine là một block; một block lồng nhau có thể khai báo biến, condition, cursor và handler riêng.

Không đặt `DECLARE` sau câu lệnh thực thi trong cùng block:

```sql
BEGIN
    SET @started = 1;

    -- Sai: DECLARE không được đặt sau câu lệnh thực thi trong block này.
    -- DECLARE v_count INT DEFAULT 0;
END
```

Nếu cần một biến chỉ dùng cho phần xử lý sau, tạo block lồng nhau ở đúng vị trí thay vì chèn khai báo muộn vào block hiện tại.

## 2. Thứ tự bắt buộc của bốn nhóm khai báo

Trong mỗi block, thứ tự tổng quát là:

1. **Biến cục bộ và condition có tên**: khai báo các biến bằng `DECLARE variable`; khai báo condition bằng `DECLARE condition_name CONDITION`.
2. **Cursor**: khai báo bằng `DECLARE cursor_name CURSOR FOR SELECT ...`.
3. **Handler**: khai báo bằng `DECLARE handler_action HANDLER FOR condition ...`.
4. **Câu lệnh thực thi**: `SET`, `SELECT`, `OPEN`, `FETCH`, `IF`, `LOOP`, `INSERT`, `UPDATE`, `CALL`, v.v.

Ví dụ hợp lệ:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE no_more_rows CONDITION FOR SQLSTATE '02000';

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR no_more_rows
        SET v_done = TRUE;

    OPEN cur_orders;
    -- Các câu lệnh thực thi tiếp theo.
    CLOSE cur_orders;
END
```

Trong nhóm đầu, biến và condition đều phải đứng trước cursor/handler; có thể tổ chức chúng theo thứ tự dễ đọc. Cursor phải đứng trước mọi handler trong cùng block. Không thể khai báo cursor sau handler hoặc khai báo biến sau cursor.

## 3. Khai báo biến cục bộ

Cú pháp:

```sql
DECLARE variable_name data_type [DEFAULT value];
```

Ví dụ:

```sql
DECLARE v_customer_id BIGINT UNSIGNED;
DECLARE v_total DECIMAL(13, 2) DEFAULT 0.00;
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE v_message VARCHAR(200) DEFAULT 'pending';
```

Biến cục bộ không có `DEFAULT` bắt đầu với giá trị `NULL`. Dùng kiểu dữ liệu phù hợp với cột/biểu thức mà biến nhận; tránh dùng `VARCHAR` cho số tiền hoặc số lượng nếu cần tính toán chính xác.

Có thể khai báo nhiều biến cùng kiểu trong một câu lệnh:

```sql
DECLARE v_min_id, v_max_id BIGINT UNSIGNED DEFAULT 0;
```

`DEFAULT` dùng để xác định giá trị khởi tạo. Với biến routine, dùng giá trị mặc định đơn giản, rõ ràng; nếu cần tính giá trị bằng biểu thức hoặc hàm, gán sau khai báo bằng `SET` hoặc `SELECT ... INTO`.

### 3.1. Gán giá trị cho biến

Dùng `SET`:

```sql
SET v_total = 1250.50;
SET v_done = FALSE;
```

Hoặc dùng `SELECT ... INTO` khi lấy dữ liệu từ bảng:

```sql
SELECT total_amount
INTO v_total
FROM orders
WHERE order_id = 1001;
```

`SELECT ... INTO` cần trả đúng một hàng. Không có hàng sẽ phát sinh điều kiện `NOT FOUND`; nhiều hơn một hàng sẽ phát sinh lỗi cardinality (thường là lỗi 1172). Nếu truy vấn có thể trả nhiều hàng, dùng cursor hoặc viết truy vấn aggregate/set-based phù hợp.

### 3.2. Biến cục bộ khác user-defined variable

Biến cục bộ được khai báo bằng `DECLARE` và chỉ tồn tại trong block/routine. User-defined variable có tiền tố `@`, thuộc session/connection và không cần `DECLARE`:

```sql
DECLARE v_count BIGINT DEFAULT 0;
SET v_count = 10;

SET @session_count = 10;
```

Không dùng `@variable` thay cho biến cục bộ trong stored program nếu không có lý do. User variable tồn tại qua nhiều câu lệnh trong cùng session và có thể giữ giá trị khi connection được tái sử dụng, gây rò trạng thái giữa các request trong connection pool.

## 4. Khai báo condition có tên

Condition giúp đặt tên cho một mã lỗi MySQL hoặc một SQLSTATE để handler dễ đọc hơn.

Cú pháp:

```sql
DECLARE condition_name CONDITION FOR condition_value;
```

Trong đó `condition_value` có thể là mã lỗi MySQL hoặc `SQLSTATE [VALUE] 'sqlstate_value'`.

Ví dụ:

```sql
DECLARE duplicate_key CONDITION FOR 1062;
DECLARE no_data CONDITION FOR SQLSTATE '02000';
DECLARE invalid_order CONDITION FOR SQLSTATE '45000';
```

Sau đó có thể dùng tên condition trong handler:

```sql
DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate_found = TRUE;
```

Condition chỉ là tên cho một điều kiện; bản thân câu `DECLARE ... CONDITION` không xử lý lỗi. Việc xử lý được thực hiện bởi handler khai báo riêng.

### 4.1. Mã lỗi MySQL và SQLSTATE

- **Mã lỗi MySQL** là số vendor-specific, ví dụ `1062` cho duplicate key.
- **SQLSTATE** là mã 5 ký tự theo quy ước SQL, ví dụ `02000` cho `NOT FOUND`, `23000` cho integrity constraint violation và `45000` cho exception do ứng dụng phát ra.
- **Condition name** là tên cục bộ ánh xạ tới một mã lỗi hoặc SQLSTATE.

Ví dụ:

```sql
DECLARE duplicate_email CONDITION FOR 1062;
DECLARE business_rule_failed CONDITION FOR SQLSTATE '45000';
```

Khi cần phân biệt lỗi cụ thể theo phiên bản/driver, ứng dụng Java vẫn nên đọc SQLSTATE và vendor error code từ `SQLException`; không chỉ phân tích chuỗi message.

## 5. Khai báo cursor

Cursor cho phép đọc lần lượt từng hàng từ một truy vấn trong stored program.

Cú pháp:

```sql
DECLARE cursor_name CURSOR FOR select_statement;
```

Ví dụ:

```sql
DECLARE cur_pending_orders CURSOR FOR
    SELECT order_id, customer_id
    FROM orders
    WHERE status = 'pending'
    ORDER BY order_id;
```

Cursor phải được khai báo sau biến/condition và trước handler trong cùng block. Câu `SELECT` của cursor không có `INTO`; các cột được lấy ra sau bằng `FETCH ... INTO`.

Cursor trong MySQL là **asensitive**, **read-only** và **nonscrollable**:

- Asensitive: server có thể hoặc không tạo bản sao dữ liệu; không dựa vào giả định cursor là snapshot độc lập.
- Read-only: cursor dùng để đọc, không cập nhật trực tiếp hàng qua cursor như một số hệ quản trị khác.
- Nonscrollable: chỉ fetch theo hướng tiến; không nhảy lùi hoặc đến vị trí tùy ý.

Cursor thường cần các bước `OPEN`, `FETCH` và `CLOSE`. Phần xử lý đầy đủ sẽ dùng handler `NOT FOUND` để nhận biết hết hàng.

## 6. Khai báo handler

Handler quy định hành động khi một condition xảy ra trong phạm vi block.

Cú pháp khái quát:

```sql
DECLARE handler_action HANDLER
FOR condition_value [, condition_value] ...
statement;
```

Hai hành động chính:

- `CONTINUE`: chạy handler rồi tiếp tục thực thi sau câu lệnh phát sinh condition.
- `EXIT`: chạy handler rồi thoát khỏi block `BEGIN ... END` nơi handler được khai báo.

MySQL có cú pháp `UNDO` trong grammar lịch sử nhưng không hỗ trợ hành động handler `UNDO`; không dùng nó.

Ví dụ handler tiếp tục sau duplicate key:

```sql
DECLARE v_duplicate_found BOOLEAN DEFAULT FALSE;
DECLARE duplicate_key CONDITION FOR 1062;

DECLARE CONTINUE HANDLER FOR duplicate_key
    SET v_duplicate_found = TRUE;
```

Ví dụ handler thoát block khi có exception:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    SET v_error_seen = TRUE;
    RESIGNAL;
END;
```

Handler có thể chạy một câu lệnh đơn hoặc một block `BEGIN ... END`. Nếu handler body là block riêng, các khai báo cục bộ của handler body phải ở đầu block đó và tuân theo cùng quy tắc thứ tự `DECLARE`.

## 7. Các nhóm condition dùng với handler

MySQL cho phép khai báo handler theo các nhóm condition tổng quát:

| Condition | Ý nghĩa |
| --- | --- |
| Mã lỗi MySQL | Một lỗi cụ thể, ví dụ `1062` |
| `SQLSTATE 'xxxxx'` | Một SQLSTATE cụ thể |
| Condition name | Tên đã khai báo bằng `DECLARE ... CONDITION` |
| `SQLWARNING` | Nhóm SQLSTATE class `01` |
| `NOT FOUND` | Nhóm SQLSTATE class `02`, thường gặp khi cursor hết hàng hoặc `SELECT ... INTO` không tìm thấy hàng |
| `SQLEXCEPTION` | Các SQLSTATE class khác `00`, `01`, `02` |

Ví dụ:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

`NOT FOUND` không chỉ có nghĩa cursor đã hết dữ liệu. Một `SELECT ... INTO` không trả hàng cũng phát sinh condition thuộc nhóm này. Khi đặt handler quá rộng ở block chứa nhiều thao tác đọc, cần phân biệt nguồn condition để không nhầm “không tìm thấy một bản ghi phụ” với “cursor đã kết thúc”.

## 8. Thứ tự ưu tiên khi nhiều handler cùng khớp

Nếu một condition có thể khớp nhiều handler trong cùng phạm vi, MySQL áp dụng thứ tự ưu tiên:

1. Handler cho mã lỗi MySQL cụ thể có ưu tiên cao nhất.
2. Handler cho SQLSTATE cụ thể có ưu tiên tiếp theo.
3. Handler cho nhóm condition như `SQLEXCEPTION`, `SQLWARNING`, `NOT FOUND` có ưu tiên thấp hơn.

Ví dụ, lỗi duplicate key có thể khớp handler cho mã `1062`, handler cho SQLSTATE `23000` và handler tổng quát `SQLEXCEPTION`. Handler mã lỗi cụ thể `1062` được ưu tiên.

Nếu có nhiều handler cùng mức ưu tiên khớp một condition, lựa chọn có thể không xác định. Tránh khai báo nhiều handler cùng mức cho cùng condition với kỳ vọng MySQL sẽ chọn theo thứ tự dòng. Thiết kế condition cụ thể, rõ ràng và chỉ dùng handler tổng quát làm fallback.

## 9. Phạm vi của biến, condition, cursor và handler

Mọi khai báo trong block có phạm vi trong block đó và các block con theo quy tắc scope. Khi block kết thúc, biến cục bộ không còn tồn tại; cursor cần được đóng trước khi rời luồng bình thường; handler không áp dụng ngoài phạm vi đã khai báo.

Ví dụ block lồng nhau:

```sql
BEGIN
    DECLARE v_outer_count INT DEFAULT 0;

    SET v_outer_count = 1;

    BEGIN
        DECLARE v_inner_count INT DEFAULT 0;
        SET v_inner_count = v_outer_count + 1;
    END;

    -- v_outer_count vẫn dùng được ở đây.
    -- v_inner_count không còn trong scope.
END
```

Block con có thể khai báo tên biến trùng với biến ngoài, nhưng điều đó dễ gây nhầm lẫn khi đọc và bảo trì. Ưu tiên tên phân biệt rõ theo mục đích (`v_outer_...`, `v_cursor_...`) thay vì dựa vào shadowing.

### 9.1. DECLARE trong IF, LOOP và handler body

Không thể đặt `DECLARE` trực tiếp sau `THEN`, `DO` hoặc giữa một chuỗi câu lệnh trong cùng block. Nếu cần scope mới, bọc phần đó trong compound statement:

```sql
IF p_use_cursor THEN
    BEGIN
        DECLARE v_local_limit INT DEFAULT 100;
        -- Các câu lệnh dùng v_local_limit.
    END;
END IF;
```

Trong block con này, mọi biến/condition vẫn phải đứng trước cursor, cursor trước handler và tất cả trước câu lệnh thực thi.

## 10. NOT FOUND và cursor exhaustion

Khi `FETCH` không còn hàng, MySQL phát sinh condition `NOT FOUND` (SQLSTATE class `02`). Cách phổ biến là khai báo một biến cờ và handler `CONTINUE`:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        -- Xử lý hàng hiện tại.
    END LOOP;

    CLOSE cur_orders;
END
```

Thứ tự khai báo trong ví dụ là điểm cốt lõi: biến trước, cursor sau, handler cuối cùng, rồi mới `OPEN` và `FETCH`.

Handler là `CONTINUE`, vì vậy sau khi `FETCH` hết hàng, luồng tiếp tục tại câu `IF v_done`. Nếu dùng `EXIT`, handler sẽ thoát khỏi block chứa nó; điều đó có thể làm routine rời block trước khi thực hiện `CLOSE` theo luồng bình thường.

Đây là cùng mẫu trong một procedure hoàn chỉnh, dùng tham số `OUT` để trả số hàng đã fetch:

```sql
DELIMITER //

CREATE PROCEDURE sp_count_orders_with_cursor(
    OUT p_processed_count BIGINT
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    SET p_processed_count = 0;
    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SET p_processed_count = p_processed_count + 1;
    END LOOP;

    CLOSE cur_orders;
END//

DELIMITER ;
```

Gọi procedure:

```sql
CALL sp_count_orders_with_cursor(@processed_count);
SELECT @processed_count;
```

Ví dụ này minh họa thứ tự khai báo. Nếu mục tiêu thực tế chỉ là đếm số đơn hàng, `SELECT COUNT(*) INTO ... FROM orders` sẽ đơn giản và hiệu quả hơn cursor.

## 11. Tránh dùng chung NOT FOUND handler cho nhiều mục đích

Một handler `NOT FOUND` ở block lớn có thể nhận cả cursor exhaustion lẫn `SELECT ... INTO` không có hàng. Ví dụ sau dễ có lỗi logic:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(150);
    DECLARE cur_orders CURSOR FOR
        SELECT customer_id FROM orders;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_customer_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SELECT customer_name
        INTO v_customer_name
        FROM customers
        WHERE customer_id = v_customer_id;

        -- Nếu không tìm thấy customer, cùng handler sẽ đặt v_done = TRUE.
        -- Vòng lặp có thể bị hiểu nhầm là cursor đã hết hàng.
    END LOOP;

    CLOSE cur_orders;
END
```

Trong ví dụ này, `v_customer_id` đã được khai báo ở nhóm biến đầu block để minh họa đúng cú pháp. Vấn đề còn lại là `SELECT ... INTO` không tìm thấy khách hàng có thể đặt cờ `v_done`, làm vòng lặp dừng sai nguyên nhân.

Một cách thiết kế an toàn hơn là cô lập cursor loop trong block riêng, hoặc đặt truy vấn phụ trong block lồng nhau với handler `NOT FOUND` riêng. Mỗi nguồn `NOT FOUND` cần có ý nghĩa xử lý rõ ràng.

Ví dụ tách truy vấn phụ:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(150);

    DECLARE cur_orders CURSOR FOR
        SELECT customer_id FROM orders ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_customer_id;
        IF v_done THEN
            LEAVE read_loop;
        END IF;

        BEGIN
            DECLARE v_customer_missing BOOLEAN DEFAULT FALSE;
            DECLARE CONTINUE HANDLER FOR NOT FOUND
                SET v_customer_missing = TRUE;

            SELECT customer_name
            INTO v_customer_name
            FROM customers
            WHERE customer_id = v_customer_id;

            IF v_customer_missing THEN
                SET v_customer_name = NULL;
            END IF;
        END;

        -- Tiếp tục xử lý hàng hiện tại.
    END LOOP;

    CLOSE cur_orders;
END
```

Handler của block con xử lý `NOT FOUND` từ `SELECT ... INTO`; handler của block ngoài chỉ quản lý cursor exhaustion. Khai báo của block con cũng tuân thủ đúng thứ tự: biến trước, handler sau.

## 12. Condition có tên giúp handler dễ đọc

Thay vì lặp mã lỗi trong handler, đặt tên condition:

```sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_email CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_email
        SET v_duplicate = TRUE;

    INSERT INTO customers (customer_name, email, region_code, status)
    VALUES ('An', 'an@example.test', 'VN', 'active');

    IF v_duplicate THEN
        -- Xử lý trường hợp email đã tồn tại.
    END IF;
END
```

Condition `duplicate_email` chỉ có ý nghĩa trong block nơi nó được khai báo và các phạm vi con. Tên condition không thay đổi mã lỗi gốc; nó chỉ làm code dễ hiểu.

Nếu cần xử lý nhiều lỗi integrity khác nhau, đừng gộp tất cả vào một condition tên chung như `data_error` nếu hành vi cần khác nhau. Dùng tên phản ánh ý nghĩa cụ thể và handler fallback `SQLEXCEPTION` để rollback/RESIGNAL khi cần.

## 13. EXIT và CONTINUE trong handler

Hai hành động này khác nhau ở vị trí luồng thực thi sau handler:

| Action | Sau khi handler chạy | Phạm vi ảnh hưởng |
| --- | --- | --- |
| `CONTINUE` | Tiếp tục tại câu lệnh ngay sau câu gây condition | Block tiếp tục hoạt động |
| `EXIT` | Thoát block `BEGIN ... END` chứa handler | Các câu còn lại trong block đó bị bỏ qua |

Ví dụ `CONTINUE` dùng cờ để xử lý duplicate:

```sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_key CONDITION FOR 1062;
    DECLARE CONTINUE HANDLER FOR duplicate_key
        SET v_duplicate = TRUE;

    INSERT INTO customers (customer_name, email, region_code, status)
    VALUES ('An', 'an@example.test', 'VN', 'active');

    IF v_duplicate THEN
        SELECT 'Email already exists' AS message;
    END IF;
END
```

Ví dụ `EXIT` để rollback và ném lại exception:

```sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- Các câu DML có thể phát sinh lỗi.
END
```

`EXIT` không đồng nghĩa với rollback tự động. Nếu cần rollback, phải viết `ROLLBACK` trong handler và chỉ dùng khi routine thực sự sở hữu transaction. Nếu transaction do caller quản lý, handler trong routine không nên tự ý rollback toàn bộ công việc của caller trừ khi hợp đồng routine quy định rõ.

## 14. Khai báo nhiều cursor và nhiều handler

Một block có thể khai báo nhiều cursor. Tất cả cursor phải được khai báo trước mọi handler trong block:

```sql
BEGIN
    DECLARE v_done_a BOOLEAN DEFAULT FALSE;
    DECLARE v_done_b BOOLEAN DEFAULT FALSE;
    DECLARE v_id_a BIGINT UNSIGNED;
    DECLARE v_id_b BIGINT UNSIGNED;

    DECLARE cur_a CURSOR FOR
        SELECT id FROM source_a ORDER BY id;
    DECLARE cur_b CURSOR FOR
        SELECT id FROM source_b ORDER BY id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
    BEGIN
        -- Một handler chung không tự biết cursor nào vừa hết.
        SET v_done_a = TRUE;
        SET v_done_b = TRUE;
    END;

    -- Cần thiết kế luồng riêng nếu hai cursor có vòng đời khác nhau.
END
```

Handler chung như trên không đủ để phân biệt cursor A hay B vừa hết dữ liệu; nó đặt cả hai cờ và có thể kết thúc vòng lặp sai. Với hai cursor có vòng đời độc lập, dùng các block lồng nhau để mỗi cursor có handler `NOT FOUND` và cờ riêng, hoặc thiết kế một truy vấn JOIN/set-based thay cho hai cursor.

Nếu khai báo nhiều handler cho các condition khác nhau, đặt tất cả sau phần khai báo cursor. Tránh handler trùng mức ưu tiên cho cùng condition vì lựa chọn có thể không xác định.

## 15. Thứ tự DECLARE trong block lồng nhau

Mỗi block có quy tắc riêng. Ví dụ block ngoài khai báo biến và handler, block con khai báo cursor và handler của riêng nó:

```sql
BEGIN
    DECLARE v_total BIGINT DEFAULT 0;

    SET v_total = 10;

    BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_id BIGINT UNSIGNED;

        DECLARE cur_ids CURSOR FOR
            SELECT order_id FROM orders ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        OPEN cur_ids;
        -- FETCH trong block con.
        CLOSE cur_ids;
    END;

    -- Tiếp tục dùng v_total.
END
```

Không cần khai báo cursor của block con ở block ngoài. Giữ khai báo gần nơi sử dụng giúp người đọc nhận ra scope và giảm khả năng handler ngoài bắt condition không mong muốn.

## 16. Lỗi cú pháp DECLARE thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Khai báo biến sau `SET` | DECLARE phải đứng ở đầu block | Chuyển khai báo lên đầu hoặc tạo block con |
| Khai báo cursor trước biến | Biến/condition phải khai báo trước cursor | Đưa nhóm biến/condition lên trước |
| Khai báo handler trước cursor | Cursor phải đứng trước handler | Chuyển toàn bộ cursor lên trước handler |
| Khai báo condition sau handler | Condition thuộc nhóm khai báo đầu | Đưa condition lên trước cursor/handler |
| Đặt DECLARE trực tiếp trong IF/LOOP | Không có block compound mới để tạo scope | Bọc phần cần khai báo bằng `BEGIN ... END` |
| Dùng `DECLARE` trong SQL ngoài routine | Đây là cú pháp stored program | Dùng biến SQL/client phù hợp hoặc tạo routine |
| Dùng handler `UNDO` | MySQL không hỗ trợ action này | Dùng `CONTINUE` hoặc `EXIT` |
| Dùng `NOT FOUND` chỉ như cursor end | `SELECT ... INTO` không có hàng cũng phát condition này | Cô lập scope/handler hoặc dùng cờ riêng |
| Đặt handler quá tổng quát | Có thể bắt nhầm lỗi cần xử lý khác | Dùng condition cụ thể và handler fallback |

## 17. Debug routine và kiểm tra khai báo

Khi routine không tạo được, kiểm tra theo thứ tự:

1. `DECLARE` có nằm ngay đầu block sau `BEGIN` không?
2. Biến và condition đã khai báo trước cursor chưa?
3. Tất cả cursor đã đứng trước handler chưa?
4. Handler có nằm trước câu lệnh thực thi không?
5. Kiểu dữ liệu biến có tương thích với cột `FETCH`/`SELECT ... INTO` không?
6. Cursor `SELECT` có đúng số cột và thứ tự với danh sách biến trong `FETCH` không?
7. Condition name đã khai báo trong scope nhìn thấy handler chưa?
8. Handler có bắt quá rộng `NOT FOUND` hoặc `SQLEXCEPTION` không?
9. Block `BEGIN ... END` có đóng đúng và label/loop có đúng không?
10. Nếu dùng command-line client, đã đổi `DELIMITER` để gửi toàn bộ routine như một statement chưa?

Xem định nghĩa routine:

```sql
SHOW CREATE PROCEDURE app_db.sp_process_orders\G
SHOW CREATE FUNCTION app_db.fn_line_total\G
```

Xem metadata routine:

```sql
SELECT
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    SQL_DATA_ACCESS,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'app_db';
```

Metadata giúp xác nhận routine đã được tạo và các đặc tính khai báo; nó không thay thế việc đọc toàn bộ source hoặc kiểm thử các nhánh handler.

## 18. Khi nào nên dùng cursor và khi nào nên dùng set-based SQL?

Cursor xử lý từng hàng tuần tự. Điều này hữu ích khi mỗi hàng cần một luồng xử lý tuần tự mà khó biểu diễn bằng một câu SQL set-based. Tuy nhiên, cursor có thể tạo nhiều lần thao tác, giữ tài nguyên lâu và khó tối ưu hơn một câu `UPDATE`, `INSERT ... SELECT`, JOIN hoặc aggregate.

Ví dụ, thay vì cursor để tăng giá tất cả sản phẩm trong một nhóm:

```sql
UPDATE products
SET price = ROUND(price * 1.05, 2)
WHERE category_id = 10;
```

thường tốt hơn việc mở cursor, fetch từng sản phẩm và update từng hàng.

Chỉ dùng cursor khi thực sự cần xử lý tuần tự, có tập dữ liệu hữu hạn, có index phù hợp và thời gian mở cursor được kiểm soát. Khi có thể, chuyển logic sang set-based SQL để MySQL tối ưu toàn bộ tập dữ liệu.

## 19. Bài tập thực hành

1. Tạo procedure có hai biến cục bộ; thử đặt một `DECLARE` sau `SET` và quan sát lỗi tạo routine.
2. Sắp xếp lại routine để biến và condition đứng trước cursor, cursor đứng trước handler.
3. Khai báo condition `duplicate_key` cho mã lỗi `1062`; dùng handler `CONTINUE` để đặt cờ.
4. Khai báo condition `no_data` cho SQLSTATE `02000`; dùng handler `NOT FOUND` trong cursor loop.
5. Tạo cursor đọc `order_id`; viết vòng lặp `OPEN`/`FETCH`/`CLOSE` có cờ `v_done`.
6. Tạo block con bên trong loop; dùng handler `NOT FOUND` riêng cho `SELECT ... INTO` để không làm dừng cursor ngoài ý muốn.
7. Tạo hai cursor trong một block; quan sát vì sao một handler `NOT FOUND` chung không phân biệt được cursor nào hết hàng.
8. So sánh `CONTINUE` và `EXIT` bằng cách ghi lại câu lệnh nào được thực thi sau khi condition xảy ra.
9. Tạo handler `SQLEXCEPTION` có `ROLLBACK` và `RESIGNAL`; kiểm tra caller nhận lại lỗi.
10. Tạo hai handler có mức ưu tiên khác nhau cho cùng lỗi; quan sát handler mã lỗi cụ thể so với `SQLEXCEPTION`.
11. Thử khai báo `DECLARE` trực tiếp trong IF và sau đó bọc bằng `BEGIN ... END`.
12. Dùng `SHOW CREATE PROCEDURE` và `INFORMATION_SCHEMA.ROUTINES` để xác minh routine sau khi tạo.
13. Viết lại một cursor update từng hàng thành một câu DML set-based; so sánh số câu lệnh và thời gian thực thi.

## 20. Ghi nhớ

Trong mỗi block `BEGIN ... END`, `DECLARE` phải đứng ở đầu block trước câu lệnh thực thi. Thứ tự nhóm là **biến và condition trước, cursor tiếp theo, handler cuối cùng**. Biến cục bộ dùng `DECLARE variable type [DEFAULT value]`; condition có tên dùng `DECLARE name CONDITION FOR error_code/SQLSTATE`; cursor dùng `DECLARE name CURSOR FOR SELECT`; handler dùng `DECLARE CONTINUE|EXIT HANDLER FOR condition ...`.

Mỗi block lồng nhau có scope và thứ tự khai báo riêng. `NOT FOUND` có thể xuất hiện khi cursor hết hàng hoặc `SELECT ... INTO` không tìm thấy hàng, vì vậy cần cô lập handler theo đúng nguồn condition. `CONTINUE` tiếp tục sau câu gây lỗi; `EXIT` thoát block chứa handler. Handler cụ thể được ưu tiên hơn nhóm tổng quát; tránh nhiều handler cùng mức ưu tiên cho một condition. Cursor phải được khai báo trước handler, đọc bằng `OPEN`/`FETCH` và đóng bằng `CLOSE`; ưu tiên set-based SQL nếu có thể xử lý cả tập dữ liệu bằng một câu lệnh.
