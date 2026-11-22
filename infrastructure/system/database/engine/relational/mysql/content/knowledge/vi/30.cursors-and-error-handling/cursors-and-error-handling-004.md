# NOT FOUND handler và kết thúc vòng lặp đọc

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Khai báo cursor bằng DECLARE CURSOR FOR SELECT.
- Thực hiện đúng vòng đời OPEN, FETCH và CLOSE.
- Hiểu điều kiện NOT FOUND và SQLSTATE 02000 khi FETCH đã đọc hết kết quả.
- Dùng CONTINUE HANDLER để đặt cờ kết thúc vòng lặp.
- Viết vòng lặp có nhãn, kiểm tra cờ ngay sau FETCH và thoát bằng LEAVE.
- Phân biệt NOT FOUND do cursor hết hàng với NOT FOUND từ SELECT ... INTO.
- Chọn phạm vi handler phù hợp để truy vấn phụ không kết thúc cursor loop ngoài ý muốn.
- Dùng EXIT HANDLER để đóng cursor khi lỗi xảy ra và phát lại lỗi gốc.
- Xử lý cursor rỗng, nhiều cursor và các tình huống OPEN/FETCH/CLOSE không đúng thứ tự.
- Nhận biết giới hạn cursor của MySQL và chọn xử lý theo tập hợp khi phù hợp.

Cursor cho phép stored program đọc kết quả SELECT từng hàng. Mỗi lần FETCH lấy một hàng vào các biến đã khai báo. Khi không còn hàng để đọc, MySQL phát condition NOT FOUND với SQLSTATE 02000. Nếu có CONTINUE HANDLER phù hợp, handler đặt một cờ để vòng lặp biết đã hết dữ liệu và rời khỏi vòng lặp an toàn.

Mẫu quan trọng nhất là: khai báo cờ, khai báo cursor, khai báo handler; mở cursor; FETCH trong vòng lặp; kiểm tra cờ ngay sau FETCH; xử lý hàng; kết thúc vòng lặp; đóng cursor. Việc kiểm tra cờ trước khi xử lý bảo đảm chương trình không dùng lại giá trị của lần FETCH trước khi cursor đã cạn.

## 1. Cursor và vòng đời đọc dữ liệu

Cursor là một đối tượng của stored program dùng để duyệt lần lượt các hàng do một câu SELECT trả về.

Một cursor trong MySQL có ba đặc tính:

- Asensitive: server có thể hoặc không tạo bản sao kết quả; chương trình không nên dựa vào giả định rằng tập kết quả luôn là snapshot độc lập.
- Read-only: cursor chỉ đọc, không dùng để cập nhật hàng trực tiếp thông qua vị trí cursor.
- Non-scrollable: chỉ đọc tiến về phía trước, không quay lại hàng trước hoặc nhảy đến vị trí tùy ý.

Vòng đời cursor gồm bốn giai đoạn:

1. DECLARE: định nghĩa SELECT mà cursor sẽ đọc.
2. OPEN: thực thi việc mở cursor để bắt đầu đọc kết quả.
3. FETCH: lấy lần lượt từng hàng vào biến.
4. CLOSE: giải phóng cursor sau khi đọc xong hoặc khi không còn cần dùng.

Sơ đồ:

~~~mermaid
flowchart TD
    A[DECLARE CURSOR] --> B[OPEN]
    B --> C[FETCH một hàng]
    C --> D{Có hàng?}
    D -->|Có| E[Xử lý hàng hiện tại]
    E --> C
    D -->|Không: NOT FOUND| F[CONTINUE HANDLER đặt cờ]
    F --> G[LEAVE vòng lặp]
    G --> H[CLOSE CURSOR]
~~~

Cursor không tự đóng chỉ vì vòng lặp đã kết thúc. Stored program phải gọi CLOSE trên mọi đường đi bình thường; nếu có lỗi trong lúc đọc, nên có handler dọn dẹp.

## 2. Khai báo cursor

Cú pháp cơ bản:

~~~sql
DECLARE cursor_name CURSOR FOR select_statement;
~~~

Ví dụ:

~~~sql
DECLARE cur_orders CURSOR FOR
    SELECT
        order_id,
        order_status,
        total_amount
    FROM sales_order
    WHERE customer_id = p_customer_id
    ORDER BY order_id;
~~~

Câu SELECT trong cursor xác định:

- Số cột được trả về.
- Thứ tự cột sẽ được FETCH.
- Các hàng thuộc tập kết quả.
- Thứ tự đọc nếu có ORDER BY.

Khi FETCH, số biến và thứ tự biến phải khớp với SELECT list. Kiểu dữ liệu của biến nên tương thích với kiểu cột hoặc biểu thức tương ứng.

Ví dụ, cursor trả ba cột theo thứ tự order_id, order_status, total_amount thì FETCH phải có ba biến theo đúng thứ tự đó.

~~~sql
FETCH cur_orders
INTO v_order_id, v_order_status, v_total_amount;
~~~

Không thêm INTO vào câu SELECT trong khai báo cursor. INTO chỉ xuất hiện ở FETCH để nhận từng hàng.

### 2.1. Thứ tự khai báo trong BEGIN ... END

MySQL yêu cầu các khai báo trong một block theo thứ tự:

1. Biến cục bộ và condition.
2. Cursor.
3. Handler.

Ví dụ đúng:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_amount DECIMAL(14, 2);

    DECLARE cur_orders CURSOR FOR
        SELECT order_id, total_amount
        FROM sales_order
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- Các câu lệnh thực thi bắt đầu từ đây
END;
~~~

Ví dụ sai là khai báo handler trước cursor hoặc khai báo biến sau khi đã có câu lệnh thực thi trong cùng block.

Nếu cần một biến cục bộ khác cho block con, có thể khai báo nó ở đầu block BEGIN ... END lồng nhau. Quy tắc khai báo được áp dụng riêng cho từng block.

### 2.2. Tham số và biến được dùng trong SELECT của cursor

Câu SELECT trong cursor có thể tham chiếu tham số routine và biến cục bộ đã khai báo trước cursor.

~~~sql
DECLARE v_from_date DATETIME DEFAULT '2026-01-01 00:00:00';

DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = p_customer_id
      AND ordered_at >= v_from_date
    ORDER BY ordered_at, order_id;
~~~

Các giá trị biến được dùng khi OPEN cursor. Vì vậy, hãy gán tham số hoặc biến lọc trước OPEN. Nếu thay đổi biến lọc sau khi cursor đã mở, không nên kỳ vọng tập kết quả đang duyệt tự động được tạo lại.

Cursor không phải công cụ để tạo câu SELECT động bằng PREPARE. Câu SELECT phải có trong khai báo cursor.

## 3. OPEN, FETCH và CLOSE

### 3.1. OPEN

OPEN bắt đầu cursor:

~~~sql
OPEN cur_orders;
~~~

Chỉ OPEN cursor đã được DECLARE trong phạm vi hiện tại. Không OPEN lại cursor khi nó vẫn đang mở.

### 3.2. FETCH

FETCH lấy hàng tiếp theo:

~~~sql
FETCH cur_orders
INTO v_order_id, v_order_status, v_total_amount;
~~~

Mỗi lần FETCH thành công, các biến nhận giá trị của hàng hiện tại. FETCH tiếp theo chuyển đến hàng kế tiếp.

Khi cursor không còn hàng, FETCH phát condition NOT FOUND. Đây là tín hiệu bình thường để vòng lặp dừng, không phải bằng chứng rằng câu SELECT của cursor bị lỗi.

Nếu không có handler phù hợp, condition này không được xử lý và có thể làm stored program kết thúc với condition chưa xử lý.

### 3.3. CLOSE

CLOSE kết thúc cursor:

~~~sql
CLOSE cur_orders;
~~~

CLOSE giải phóng tài nguyên gắn với cursor. Không FETCH sau CLOSE và không CLOSE một cursor chưa được OPEN.

Một cursor phải được CLOSE trước khi rời khỏi block sở hữu nó nếu nó đã được mở.

## 4. NOT FOUND và SQLSTATE 02000

NOT FOUND là condition class dùng cho trường hợp không tìm thấy dữ liệu. Với thao tác FETCH, MySQL phát SQLSTATE 02000 khi cursor đã hết hàng.

Có thể khai báo handler trực tiếp:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Hoặc khai báo bằng SQLSTATE:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLSTATE '02000'
    SET v_done = TRUE;
~~~

Hai cách trên nhận diện cùng condition SQLSTATE 02000.

Có thể đặt tên condition trước khi khai báo cursor:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
DECLARE no_more_rows CONDITION FOR SQLSTATE '02000';

DECLARE cur_orders CURSOR FOR
    SELECT order_id
    FROM sales_order;

DECLARE CONTINUE HANDLER FOR no_more_rows
    SET v_done = TRUE;
~~~

Dùng NOT FOUND thường dễ đọc hơn khi mục tiêu là nhận biết cursor đã đọc hết kết quả.

### 4.1. Vì sao handler phải là CONTINUE?

CONTINUE HANDLER xử lý condition rồi tiếp tục thực thi tại câu lệnh ngay sau câu lệnh phát condition.

Với FETCH, điều đó có nghĩa:

1. FETCH cố đọc hàng tiếp theo.
2. Cursor đã hết hàng, MySQL phát NOT FOUND.
3. Handler đặt v_done = TRUE.
4. Chương trình tiếp tục ở câu lệnh sau FETCH.
5. IF kiểm tra v_done và LEAVE vòng lặp.

Nếu dùng EXIT HANDLER trong cùng block, condition sẽ làm thoát block chứa handler. Chương trình có thể rời procedure hoặc block đọc trước khi chạy CLOSE bình thường. Vì vậy, mẫu đọc cursor thông dụng dùng CONTINUE HANDLER để điều khiển vòng lặp bằng cờ.

### 4.2. Cờ kết thúc vòng lặp

Biến cờ thường có kiểu BOOLEAN hoặc TINYINT:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;
~~~

Handler đặt cờ:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Cờ phải được khởi tạo FALSE trước khi mở cursor. Sau khi FETCH hết hàng, handler đổi cờ thành TRUE. Vòng lặp kiểm tra cờ và dừng.

Không đặt lại cờ về FALSE ngay sau FETCH trước khi kiểm tra; làm vậy sẽ xóa tín hiệu hết dữ liệu và có thể khiến vòng lặp chạy sai.

## 5. Mẫu vòng lặp đọc cursor chuẩn

Đây là mẫu nên ghi nhớ:

~~~sql
read_loop: LOOP
    FETCH cur_orders
    INTO v_order_id, v_total_amount;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Xử lý hàng hiện tại ở đây
END LOOP;
~~~

Giải thích:

- read_loop là nhãn của vòng lặp.
- FETCH cố lấy một hàng.
- Nếu hết hàng, handler đặt v_done thành TRUE.
- IF phải nằm ngay sau FETCH.
- LEAVE read_loop thoát đúng vòng lặp có nhãn.
- Phần xử lý chỉ chạy khi FETCH thành công.

### 5.1. Vì sao kiểm tra cờ trước phần xử lý?

Khi FETCH hết hàng, các biến nhận dữ liệu có thể vẫn giữ giá trị của lần FETCH thành công trước đó. Nếu chương trình xử lý biến trước khi kiểm tra v_done, hàng cuối có thể bị xử lý lặp lại.

Thứ tự đúng:

~~~sql
FETCH cur_orders INTO v_order_id;

IF v_done THEN
    LEAVE read_loop;
END IF;

SET v_count = v_count + 1;
~~~

Thứ tự sai:

~~~sql
FETCH cur_orders INTO v_order_id;

SET v_count = v_count + 1;

IF v_done THEN
    LEAVE read_loop;
END IF;
~~~

Trong cách sai, lần FETCH cuối cùng phát NOT FOUND nhưng v_count vẫn tăng thêm một lần.

### 5.2. Cursor không có hàng ngay từ đầu

Nếu SELECT của cursor không trả hàng nào, lần FETCH đầu tiên phát NOT FOUND. Handler đặt v_done = TRUE. IF ngay sau FETCH làm vòng lặp kết thúc mà không chạy phần xử lý.

Vì vậy, không cần kiểm tra COUNT(*) trước OPEN chỉ để xác định cursor có hàng hay không. Hãy để FETCH đầu tiên và NOT FOUND handler xử lý trường hợp tập kết quả rỗng.

## 6. Ví dụ hoàn chỉnh: đọc và tổng hợp đơn hàng

Ví dụ này tạo bảng thực hành, mở cursor theo một khách hàng, đọc từng đơn và tổng hợp số lượng, tổng tiền cùng số đơn đã thanh toán.

### 6.1. Tạo dữ liệu mẫu

~~~sql
CREATE TABLE cursor_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    ordered_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_cursor_customer_order (customer_id, order_id)
) ENGINE = InnoDB;

INSERT INTO cursor_order_demo (
    order_id,
    customer_id,
    order_status,
    total_amount,
    ordered_at
)
VALUES
    (8101, 101, 'PAID',      1250000.00, '2026-02-01 09:15:00'),
    (8102, 101, 'PENDING',   2400000.00, '2026-02-03 11:30:00'),
    (8103, 101, 'PAID',       450000.00, '2026-02-18 10:20:00'),
    (8104, 102, 'PAID',       890000.00, '2026-02-08 14:00:00'),
    (8105, 102, 'CANCELLED',  760000.00, '2026-03-05 13:25:00'),
    (8106, 103, 'PENDING',   3400000.00, '2026-02-15 16:45:00');
~~~

### 6.2. Tạo procedure có NOT FOUND handler

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_summarize_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED,
    OUT p_total_amount DECIMAL(16, 2),
    OUT p_paid_count INT UNSIGNED
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_order_status VARCHAR(20);
    DECLARE v_amount DECIMAL(14, 2);

    DECLARE cur_orders CURSOR FOR
        SELECT
            order_id,
            order_status,
            total_amount
        FROM cursor_order_demo
        WHERE customer_id = p_customer_id
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_cursor_open THEN
            CLOSE cur_orders;
        END IF;
        RESIGNAL;
    END;

    SET p_order_count = 0;
    SET p_total_amount = 0.00;
    SET p_paid_count = 0;

    OPEN cur_orders;
    SET v_cursor_open = TRUE;

    read_loop: LOOP
        FETCH cur_orders
        INTO v_order_id, v_order_status, v_amount;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        SET p_order_count = p_order_count + 1;
        SET p_total_amount = p_total_amount + v_amount;

        IF v_order_status = 'PAID' THEN
            SET p_paid_count = p_paid_count + 1;
        END IF;
    END LOOP;

    CLOSE cur_orders;
    SET v_cursor_open = FALSE;
END$$

DELIMITER ;
~~~

Điểm cần chú ý:

- Biến và cờ được khai báo trước cursor.
- Cursor được khai báo trước handler.
- CONTINUE HANDLER FOR NOT FOUND đặt v_done thành TRUE khi FETCH hết hàng.
- EXIT HANDLER FOR SQLEXCEPTION đóng cursor nếu cursor đang mở, sau đó RESIGNAL để caller nhận lỗi gốc.
- Cờ v_cursor_open được đặt TRUE sau OPEN và FALSE sau CLOSE.
- Các biến OUT được khởi tạo trước vòng lặp.
- IF v_done nằm ngay sau FETCH, trước mọi phép tính.
- ORDER BY order_id giúp thứ tự đọc ổn định theo khóa chính.

### 6.3. Gọi procedure

~~~sql
CALL sp_summarize_customer_orders(
    101,
    @order_count,
    @total_amount,
    @paid_count
);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount,
    @paid_count AS paid_count;
~~~

Kết quả mong đợi với dữ liệu mẫu:

| Chỉ tiêu | Kết quả |
|---|---:|
| Số đơn | 3 |
| Tổng tiền | 4,100,000.00 |
| Số đơn PAID | 2 |

### 6.4. Thử khách hàng không có đơn

~~~sql
CALL sp_summarize_customer_orders(
    999,
    @order_count,
    @total_amount,
    @paid_count
);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount,
    @paid_count AS paid_count;
~~~

Kết quả là 0, 0.00 và 0. Lần FETCH đầu tiên phát NOT FOUND; handler đặt cờ, vòng lặp LEAVE và procedure vẫn CLOSE cursor.

## 7. NOT FOUND từ SELECT ... INTO cũng kích hoạt handler

Một điểm dễ gây lỗi là NOT FOUND không chỉ xuất hiện khi cursor đã hết hàng. SELECT ... INTO không trả hàng cũng phát condition NOT FOUND với SQLSTATE 02000.

Giả sử cùng block vừa có cursor loop vừa có câu SELECT ... INTO:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Nếu SELECT ... INTO không tìm thấy dữ liệu, handler trên cũng đặt v_done = TRUE. Vòng lặp cursor có thể kết thúc sớm ở lần FETCH tiếp theo dù cursor vẫn còn hàng.

Đây là lỗi logic khó phát hiện nếu chỉ thử với dữ liệu luôn tồn tại.

### 7.1. Cách ly SELECT ... INTO bằng block lồng nhau

Dùng block con với handler NOT FOUND riêng:

~~~sql
BEGIN
    DECLARE v_customer_name VARCHAR(100) DEFAULT NULL;
    DECLARE v_lookup_missing BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_lookup_missing = TRUE;

    SELECT c.customer_name
    INTO v_customer_name
    FROM customer AS c
    WHERE c.customer_id = p_customer_id;

    IF v_lookup_missing THEN
        SET v_customer_name = 'Unknown customer';
    END IF;
END;
~~~

Handler trong block con xử lý NOT FOUND của SELECT ... INTO. Nó không thay đổi cờ v_done của block ngoài dùng cho cursor.

Khi block con kết thúc, handler cục bộ cũng hết phạm vi. Handler NOT FOUND ở block ngoài vẫn dùng để nhận biết FETCH hết dữ liệu.

### 7.2. Khởi tạo biến nhận trước SELECT ... INTO

Nếu SELECT ... INTO không trả hàng, biến nhận giữ giá trị trước câu lệnh. Vì vậy, hãy khởi tạo biến trước truy vấn:

~~~sql
SET v_customer_name = NULL;
SET v_lookup_missing = FALSE;

SELECT c.customer_name
INTO v_customer_name
FROM customer AS c
WHERE c.customer_id = p_customer_id;
~~~

Nếu không có hàng, handler đặt v_lookup_missing thành TRUE và v_customer_name vẫn là NULL.

### 7.3. Phân biệt không có hàng và nhiều hàng

SELECT ... INTO có ba tình huống cần phân biệt:

| Kết quả SELECT | Condition/kết quả |
|---|---|
| Chính xác một hàng | Gán giá trị vào biến |
| Không có hàng | NOT FOUND, SQLSTATE 02000; biến giữ nguyên |
| Nhiều hơn một hàng | Lỗi 1172, Result consisted of more than one row |

Handler NOT FOUND không xử lý lỗi 1172. Nếu truy vấn cần duy nhất một hàng, hãy dùng khóa duy nhất hoặc kiểm tra điều kiện. Nếu nghiệp vụ chỉ cần một hàng gần nhất, dùng ORDER BY có tiêu chí phụ ổn định và LIMIT 1.

### 7.4. Cách khác: dùng handler riêng cho từng block

Phạm vi handler là block nơi nó được khai báo. Có thể dùng block con cho truy vấn phụ, block ngoài cho cursor, hoặc tạo routine con chuyên trách lookup. Mục tiêu là mỗi handler chỉ xử lý condition đúng với nhiệm vụ của nó.

Không nên khai báo một NOT FOUND handler toàn cục rồi dùng chung cho nhiều thao tác không liên quan nếu cờ kết thúc cursor có thể bị đặt nhầm.

## 8. NOT FOUND so với SQLWARNING và SQLEXCEPTION

MySQL phân loại condition theo SQLSTATE:

- SQLWARNING: class 01.
- NOT FOUND: class 02.
- SQLEXCEPTION: các class lỗi khác, ngoại trừ class 00, 01 và 02.

Do đó, SQLEXCEPTION không thay thế NOT FOUND handler. Khi FETCH hết cursor, một EXIT HANDLER FOR SQLEXCEPTION không bắt condition SQLSTATE 02000.

Ví dụ:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_orders;
    END IF;
    RESIGNAL;
END;
~~~

Hai handler có mục đích riêng:

- NOT FOUND là tín hiệu điều khiển bình thường để dừng vòng lặp.
- SQLEXCEPTION là đường xử lý lỗi để dọn dẹp rồi truyền lỗi về caller.

Nếu nhiều handler cùng có khả năng áp dụng, MySQL chọn handler có độ ưu tiên cụ thể hơn. Handler cho mã lỗi MySQL cụ thể ưu tiên hơn SQLSTATE cụ thể; SQLSTATE cụ thể ưu tiên hơn condition class như NOT FOUND hoặc SQLEXCEPTION. Hãy tránh khai báo các handler chồng lấn nếu không cần thiết.

## 9. CONTINUE HANDLER và EXIT HANDLER

Handler có hai hành vi chính cần phân biệt:

| Loại handler | Sau khi xử lý condition |
|---|---|
| CONTINUE | Tiếp tục tại câu lệnh ngay sau câu lệnh gây condition |
| EXIT | Thoát khỏi block BEGIN ... END chứa handler |

Mẫu cursor loop dùng CONTINUE vì cần tiếp tục tới IF v_done sau FETCH.

EXIT HANDLER thường dùng cho lỗi cần rời block, ví dụ đóng cursor và phát lại lỗi:

~~~sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_orders;
    END IF;

    RESIGNAL;
END;
~~~

RESIGNAL phát lại condition đang được xử lý để caller nhận đúng lỗi gốc. Nếu handler chỉ ghi log hoặc đặt cờ mà không RESIGNAL, lỗi có thể bị nuốt; chỉ làm vậy khi đó là hợp đồng xử lý lỗi được thiết kế rõ ràng.

### 9.1. Đặt handler ở đúng phạm vi

Handler chỉ áp dụng cho câu lệnh trong block khai báo handler và các block con của nó, trừ khi một handler cụ thể hơn ở block con xử lý condition trước.

Vì vậy:

- Handler cursor nên nằm trong block quản lý cursor.
- Lookup có thể không có hàng nên được đặt trong block con có handler riêng.
- Không nên để handler của một thao tác phụ thay đổi cờ điều khiển của vòng lặp chính.

## 10. Các dạng vòng lặp đọc cursor

### 10.1. LOOP và LEAVE

Đây là mẫu phổ biến và dễ kiểm soát nhất:

~~~sql
OPEN cur_orders;

read_loop: LOOP
    FETCH cur_orders INTO v_order_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Xử lý hàng
END LOOP;

CLOSE cur_orders;
~~~

Ưu điểm là vị trí kiểm tra cờ rõ ràng và không xử lý hàng giả sau khi hết dữ liệu.

### 10.2. REPEAT

Có thể dùng REPEAT nếu phần xử lý được bảo vệ bởi IF:

~~~sql
OPEN cur_orders;

read_loop: REPEAT
    FETCH cur_orders INTO v_order_id;

    IF NOT v_done THEN
        -- Xử lý hàng hiện tại
        SET v_count = v_count + 1;
    END IF;
UNTIL v_done
END REPEAT;

CLOSE cur_orders;
~~~

REPEAT kiểm tra điều kiện kết thúc sau khi chạy thân vòng lặp. Vì vậy, phần xử lý phải có IF NOT v_done để tránh xử lý biến còn giữ giá trị cũ sau lần FETCH cuối.

### 10.3. Vì sao WHILE ít trực tiếp hơn?

WHILE kiểm tra điều kiện trước khi chạy thân vòng lặp. Nhưng để biết có hàng tiếp theo hay không, chương trình vẫn phải FETCH. Điều đó thường đòi hỏi một FETCH ban đầu trước WHILE và một FETCH ở cuối mỗi vòng.

Nếu dùng WHILE, cần thiết kế rõ lần FETCH đầu tiên, cờ done và lần FETCH kế tiếp. Với người mới học cursor, LOOP + FETCH + IF + LEAVE thường ít gây lỗi hơn.

## 11. Đọc nhiều cursor và đặt lại cờ

Một procedure có thể khai báo nhiều cursor. Mỗi cursor có SELECT và vòng đời riêng. Nếu dùng chung một cờ done, phải đặt lại cờ về FALSE trước khi mở cursor tiếp theo.

Ví dụ cấu trúc:

~~~sql
SET v_done = FALSE;
OPEN cur_customers;

customer_loop: LOOP
    FETCH cur_customers INTO v_customer_id;

    IF v_done THEN
        LEAVE customer_loop;
    END IF;

    -- Xử lý khách hàng
END LOOP;

CLOSE cur_customers;

SET v_done = FALSE;
OPEN cur_orders;

order_loop: LOOP
    FETCH cur_orders INTO v_order_id;

    IF v_done THEN
        LEAVE order_loop;
    END IF;

    -- Xử lý đơn hàng
END LOOP;

CLOSE cur_orders;
~~~

Nếu quên đặt lại cờ, cursor thứ hai có thể thoát ngay ở lần kiểm tra đầu tiên vì v_done vẫn là TRUE từ cursor trước.

Khi nhiều cursor có thể hoạt động lồng nhau, dùng cờ riêng cho từng cursor và handler có phạm vi riêng để tránh việc một cursor đặt cờ kết thúc cho cursor khác.

## 12. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Cursor tự đóng khi FETCH hết hàng | Cursor vẫn cần CLOSE | Gọi CLOSE sau vòng lặp |
| NOT FOUND là lỗi SQL nghiêm trọng | Đây là condition bình thường khi FETCH hết dữ liệu | Dùng CONTINUE HANDLER |
| Dùng EXIT HANDLER để dừng cursor loop | EXIT rời block chứa handler | Dùng CONTINUE và cờ done |
| Xử lý biến trước khi kiểm tra done | FETCH cuối có thể để lại giá trị hàng trước | IF done phải nằm ngay sau FETCH |
| Cursor rỗng cần COUNT trước OPEN | FETCH đầu tiên đã phát NOT FOUND | Để handler xử lý cursor rỗng |
| SQLEXCEPTION bắt được NOT FOUND | Class 02 không thuộc SQLEXCEPTION | Khai báo NOT FOUND riêng |
| SELECT ... INTO không có hàng không liên quan cursor handler | Nó cũng phát SQLSTATE 02000 | Cách ly lookup bằng block con hoặc handler riêng |
| Quên đặt lại done khi dùng cursor thứ hai | Cờ vẫn TRUE từ cursor trước | Đặt FALSE trước OPEN tiếp theo |
| FETCH khi cursor chưa OPEN | Cursor chưa sẵn sàng để đọc | OPEN trước FETCH |
| FETCH sau CLOSE | Cursor đã kết thúc vòng đời | Không FETCH sau CLOSE |
| OPEN cursor hai lần | Cursor đang mở không thể OPEN lại | CLOSE trước khi OPEN lại |
| Cursor có thể quay về hàng trước | Cursor MySQL không scrollable | Thiết kế SELECT mới nếu cần duyệt lại |
| Cursor có thể cập nhật hàng hiện tại | Cursor MySQL read-only | Dùng UPDATE với điều kiện khóa |
| Dùng cursor cho phép tính tổng đơn giản | SQL set-based thường hiệu quả hơn | Dùng SUM, COUNT, UPDATE hoặc INSERT ... SELECT |
| ORDER BY không cần khóa phụ | Nhiều hàng có thể có cùng giá trị sắp xếp | Thêm khóa duy nhất để thứ tự ổn định |

## 13. Hiệu năng và giới hạn thực tế

Cursor xử lý từng hàng và thường tạo nhiều lần chuyển điều khiển giữa SQL statement và stored program. Với phép tính có thể biểu diễn bằng một câu SQL, cách set-based thường ngắn và nhanh hơn.

Ví dụ không cần cursor để tính tổng:

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0.00) AS total_amount
FROM cursor_order_demo
WHERE customer_id = 101;
~~~

Thay vì FETCH từng đơn rồi cộng biến, dùng COUNT và SUM để MySQL xử lý theo tập hợp.

Cursor có ích khi mỗi hàng cần một chuỗi xử lý có điều kiện mà không thể diễn đạt gọn bằng SQL set-based, hoặc khi phải gọi các routine/logic khác theo từng hàng. Tuy vậy, hãy cân nhắc chi phí row-by-row, transaction length, khóa và lượng dữ liệu.

Các cursor trong MySQL là asensitive. Server có thể materialize kết quả hoặc không; không nên phụ thuộc vào việc thay đổi bảng nguồn trong khi cursor đang mở sẽ hoặc sẽ không xuất hiện trong tập kết quả hiện tại. Nếu cần hành vi nhất quán, hãy thiết kế transaction và isolation level có chủ đích.

## 14. Quy trình xây dựng cursor loop an toàn

Khi viết procedure đọc cursor:

1. Xác định có thật sự cần xử lý từng hàng hay có thể dùng SQL set-based.
2. Viết SELECT của cursor và chọn cột tối thiểu cần dùng.
3. Thêm điều kiện lọc và ORDER BY ổn định nếu thứ tự xử lý có ý nghĩa.
4. Khai báo biến nhận trước cursor.
5. Khai báo cursor sau biến và condition.
6. Khai báo CONTINUE HANDLER FOR NOT FOUND sau cursor.
7. Khởi tạo cờ done thành FALSE và khởi tạo biến kết quả.
8. OPEN cursor.
9. FETCH vào đúng số biến và đúng thứ tự.
10. Kiểm tra done ngay sau FETCH; LEAVE nếu hết hàng.
11. Chỉ xử lý hàng khi FETCH thành công.
12. CLOSE cursor sau khi vòng lặp kết thúc.
13. Nếu có thể xảy ra SQL exception, dùng EXIT HANDLER để CLOSE cursor khi đang mở rồi RESIGNAL.
14. Nếu có SELECT ... INTO phụ, dùng block handler riêng để tránh đặt nhầm cờ done.
15. Kiểm thử cursor rỗng, một hàng, nhiều hàng và lỗi trong lúc xử lý.

## 15. Bài tập thực hành

### Bài 1: Cursor đọc đơn hàng

Khai báo cursor đọc order_id và total_amount của một khách hàng. FETCH từng hàng và in kết quả bằng SELECT hoặc cộng vào biến tổng.

### Bài 2: NOT FOUND handler

Viết CONTINUE HANDLER FOR NOT FOUND đặt v_done = TRUE. Giải thích khi nào handler được gọi trong vòng lặp.

### Bài 3: Cursor rỗng

Gọi procedure với customer_id không có đơn. Xác nhận lần FETCH đầu tiên đặt cờ done và không chạy phần xử lý hàng.

### Bài 4: Phát hiện xử lý hàng cuối hai lần

Cố ý đặt IF v_done sau phần cộng tổng. So sánh kết quả sai với cách kiểm tra ngay sau FETCH.

### Bài 5: SELECT INTO trong cùng block

Thêm một SELECT ... INTO tìm tên khách hàng vào procedure cursor. Thử một mã không tồn tại và quan sát cờ done bị đặt. Sau đó chuyển lookup vào block con với handler riêng.

### Bài 6: Phân biệt NOT FOUND và SQLEXCEPTION

Viết hai handler riêng. Kiểm tra FETCH hết dữ liệu được NOT FOUND xử lý, còn lỗi SQL thực sự được SQLEXCEPTION handler nhận.

### Bài 7: Đóng cursor khi có lỗi

Thêm EXIT HANDLER FOR SQLEXCEPTION, cờ cursor_open và RESIGNAL. Tạo một lỗi có chủ đích trong phần xử lý và xác minh cursor được đóng trước khi lỗi trả về caller.

### Bài 8: Hai cursor dùng chung cờ

Khai báo hai cursor, đọc cursor thứ nhất rồi cursor thứ hai. Thử bỏ lệnh đặt lại v_done và giải thích vì sao cursor thứ hai thoát sớm.

### Bài 9: LOOP so với REPEAT

Viết hai phiên bản cùng đọc cursor. Bảo đảm phiên bản REPEAT chỉ xử lý khi v_done = FALSE. So sánh khả năng đọc và nguy cơ xử lý hàng cuối lặp lại.

### Bài 10: Thay cursor bằng SQL set-based

Viết một procedure dùng cursor để tính số đơn và tổng tiền. Viết lại bằng COUNT(*) và SUM(). So sánh số câu lệnh, độ phức tạp và thời gian thực thi trên dữ liệu đủ lớn.

## Kết luận

NOT FOUND với SQLSTATE 02000 là tín hiệu MySQL dùng để thông báo cursor đã hết hàng. CONTINUE HANDLER đặt cờ done; vòng lặp kiểm tra cờ ngay sau FETCH rồi LEAVE khi cần. Cursor được OPEN trước khi đọc và phải CLOSE sau khi hoàn tất.

Hãy nhớ ba nguyên tắc: khai báo biến trước cursor và handler; kiểm tra cờ trước khi xử lý dữ liệu sau FETCH; và quản lý phạm vi NOT FOUND handler để SELECT ... INTO không làm kết thúc nhầm vòng lặp. Khi xử lý lỗi khác, EXIT HANDLER có thể đóng cursor đang mở rồi RESIGNAL để giữ nguyên lỗi gốc.

Cursor hữu ích cho logic xử lý từng hàng, nhưng SQL set-based nên là lựa chọn đầu tiên cho phép tổng hợp hoặc cập nhật có thể thực hiện trên cả tập dữ liệu.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Cursors: https://dev.mysql.com/doc/refman/8.4/en/cursors.html
- MySQL 8.4 Reference Manual — DECLARE ... HANDLER Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-handler.html
- MySQL 8.4 Reference Manual — DECLARE ... CONDITION Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-condition.html
- MySQL 8.4 Reference Manual — DECLARE Statement: https://dev.mysql.com/doc/refman/8.4/en/declare.html
- MySQL 8.4 Reference Manual — FETCH Statement: https://dev.mysql.com/doc/refman/8.4/en/fetch.html
- MySQL 8.4 Reference Manual — OPEN Statement: https://dev.mysql.com/doc/refman/8.4/en/open.html
- MySQL 8.4 Reference Manual — CLOSE Statement: https://dev.mysql.com/doc/refman/8.4/en/close.html
- MySQL 8.4 Reference Manual — RESIGNAL Statement: https://dev.mysql.com/doc/refman/8.4/en/resignal.html
- MySQL 8.4 Reference Manual — Condition Handling and Scope: https://dev.mysql.com/doc/refman/8.4/en/handler-scope.html

