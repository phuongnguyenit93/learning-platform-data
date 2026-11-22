# CONTINUE/EXIT handler và phạm vi khối áp dụng

Stored program của MySQL có thể gặp nhiều loại điều kiện khi chạy: truy vấn không tìm thấy hàng, phép chuyển đổi dữ liệu phát sinh cảnh báo, vi phạm constraint hoặc lỗi SQL. Handler cho phép routine phản ứng với các điều kiện đó ngay trong luồng thực thi.

Hai kiểu handler chính là:

- **CONTINUE**: chạy phần thân handler rồi tiếp tục thực thi tại câu lệnh ngay sau câu lệnh đã phát sinh điều kiện.
- **EXIT**: chạy phần thân handler rồi thoát khỏi khối BEGIN ... END nơi handler được khai báo.

Điểm dễ nhầm là EXIT không phải lúc nào cũng thoát toàn bộ procedure. Nếu handler được khai báo trong một block lồng bên trong, EXIT chỉ kết thúc block đó; các câu lệnh sau block trong routine bên ngoài vẫn có thể chạy.

Bài viết giải thích cách khai báo handler, phân biệt CONTINUE và EXIT, phạm vi của handler trong các block lồng nhau, phân loại điều kiện SQL, thứ tự ưu tiên khi nhiều handler cùng khớp và cách thiết kế handler có thể dự đoán được.

## 1. Handler là gì?

Handler là một khai báo trong stored program để xử lý một điều kiện cụ thể. Điều kiện có thể là một SQLSTATE, một mã lỗi MySQL hoặc một nhóm điều kiện được đặt tên.

Cú pháp tổng quát:

~~~sql
DECLARE { CONTINUE | EXIT } HANDLER
FOR condition_value [, condition_value] ...
statement;
~~~

MySQL hỗ trợ hai loại handler CONTINUE và EXIT. Từ khóa UNDO có trong một số mô tả SQL nhưng không được MySQL hỗ trợ.

Trong đó:

- CONTINUE hoặc EXIT xác định luồng thực thi sau khi handler chạy.
- FOR xác định điều kiện mà handler nhận xử lý.
- statement là một câu lệnh hoặc một block BEGIN ... END làm phần thân handler.

Ví dụ handler đơn giản:

~~~sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_not_found = TRUE;
~~~

Khi điều kiện NOT FOUND xảy ra trong phạm vi handler, MySQL đặt v_not_found thành TRUE rồi tiếp tục sau câu lệnh gây ra điều kiện.

Handler thường được dùng để:

- Đánh dấu đã đọc hết dữ liệu khi FETCH cursor không còn hàng.
- Phát hiện SELECT ... INTO không tìm thấy hàng.
- Ghi nhận hoặc chuyển tiếp lỗi SQL.
- Thực hiện dọn dẹp trạng thái trước khi thoát một block.
- Biến lỗi kỹ thuật thành một kết quả hoặc thông báo phù hợp với hợp đồng của routine.

Handler không phải cơ chế thay thế constraint, transaction hoặc kiểm tra dữ liệu đầu vào. Nó quyết định cách routine phản ứng sau khi một điều kiện đã xảy ra.

## 2. Điều kiện SQL mà handler có thể bắt

MySQL cho phép khai báo handler theo nhiều dạng điều kiện:

| Dạng điều kiện | Ý nghĩa |
|---|---|
| SQLSTATE value | Mã trạng thái SQL gồm 5 ký tự, ví dụ '02000' hoặc '45000' |
| MySQL error code | Mã lỗi số cụ thể, ví dụ 1062 |
| SQLWARNING | Nhóm SQLSTATE class 01 |
| NOT FOUND | Nhóm SQLSTATE class 02 |
| SQLEXCEPTION | Các SQLSTATE khác class 00, 01 và 02 |
| Condition name | Tên điều kiện đã khai báo bằng DECLARE ... CONDITION |

SQLEXCEPTION không bắt SQLWARNING hoặc NOT FOUND vì hai nhóm này có SQLSTATE class riêng. Nếu routine cần xử lý cả ba nhóm, khai báo handler tương ứng và xác định rõ mỗi nhóm cần tiếp tục hay thoát block.

### 2.1. SQLWARNING

SQLWARNING đại diện cho các điều kiện cảnh báo, tức SQLSTATE thuộc class 01.

~~~sql
BEGIN
    DECLARE v_warning_seen BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLWARNING
        SET v_warning_seen = TRUE;

    -- Các câu lệnh có thể phát sinh warning.
END
~~~

Handler này có thể bắt nhiều loại warning khác nhau. Nếu cần phản ứng riêng với một warning cụ thể, dùng SQLSTATE hoặc condition name tương ứng thay vì gom tất cả vào SQLWARNING.

### 2.2. NOT FOUND

NOT FOUND đại diện cho SQLSTATE class 02. Các trường hợp phổ biến:

- SELECT ... INTO không tìm thấy hàng.
- FETCH cursor đã đi đến cuối tập kết quả.

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- Các câu lệnh có thể phát sinh NOT FOUND.
END
~~~

Với cursor, đây là mẫu thường dùng để đặt cờ kết thúc vòng lặp. Với SELECT ... INTO, cờ giúp routine phân biệt không tìm thấy hàng với một hàng có giá trị NULL.

### 2.3. SQLEXCEPTION

SQLEXCEPTION đại diện cho các điều kiện SQLSTATE không thuộc class 00, 01 hoặc 02. Ví dụ thường gặp là lỗi constraint hoặc lỗi thực thi câu SQL.

~~~sql
BEGIN
    DECLARE v_failed BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET v_failed = TRUE;
        RESIGNAL;
    END;

    -- Các câu lệnh có thể phát sinh lỗi SQL.
END
~~~

RESIGNAL phát lại điều kiện hiện tại để caller vẫn nhận được lỗi. Nếu handler chỉ ghi cờ rồi nuốt lỗi, caller có thể tưởng thao tác đã thành công; chỉ làm vậy khi routine có hợp đồng xử lý lỗi rõ ràng.

### 2.4. SQLSTATE cụ thể

Có thể bắt một SQLSTATE cụ thể:

~~~sql
BEGIN
    DECLARE v_business_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_business_error = TRUE;

    -- Các câu lệnh có thể SIGNAL SQLSTATE '45000'.
END
~~~

SQLSTATE '45000' thường được dùng với SIGNAL để phát sinh điều kiện do ứng dụng định nghĩa:

~~~sql
SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'Trạng thái đơn hàng không hợp lệ';
~~~

Handler bắt điều kiện này giống như một điều kiện SQL khác. Dùng SQLSTATE cụ thể khi cần kiểm soát đúng một tình huống; tránh bắt quá rộng nếu các lỗi khác cần được chuyển đến caller.

## 3. CONTINUE handler hoạt động như thế nào?

CONTINUE handler chạy phần thân handler, sau đó luồng thực thi tiếp tục tại câu lệnh ngay sau câu lệnh gây ra điều kiện.

Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_continue_handler()
BEGIN
    DECLARE v_step INT DEFAULT 0;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_step = v_step + 1;

    SET v_step = 10;

    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Điều kiện thử nghiệm';

    SET v_step = v_step + 100;

    SELECT v_step AS final_step;
END//

DELIMITER ;
~~~

Trình tự:

1. v_step được gán 10.
2. SIGNAL phát sinh SQLSTATE '45000'.
3. CONTINUE handler tăng v_step thêm 1.
4. MySQL tiếp tục sau SIGNAL.
5. Câu SET tiếp theo tăng thêm 100.
6. SELECT trả về 111.

CONTINUE không quay lại chạy lại câu lệnh đã lỗi. Nó tiếp tục sau câu lệnh đó.

### 3.1. Khi nào nên dùng CONTINUE?

CONTINUE phù hợp khi routine có thể xử lý điều kiện và tiếp tục công việc một cách an toàn:

- Đặt cờ done khi FETCH không còn hàng.
- Đánh dấu một bản ghi không tồn tại và đi sang nhánh xử lý khác.
- Ghi nhận warning nhưng vẫn tiếp tục nếu warning không làm mất tính đúng đắn.
- Bỏ qua một trường hợp đã được xác định là có thể phục hồi.

Không dùng CONTINUE một cách máy móc cho mọi SQLEXCEPTION. Nếu câu lệnh thất bại nhưng các câu lệnh sau vẫn chạy, routine có thể tạo trạng thái một phần hoặc kết quả không nhất quán.

### 3.2. CONTINUE không xóa điều kiện

Handler không làm cho câu lệnh gây lỗi trở thành thành công. Nó chỉ quy định điều gì xảy ra tiếp theo.

Ví dụ, nếu INSERT vi phạm khóa duy nhất và handler CONTINUE bắt lỗi 1062, hàng không được chèn. Các câu lệnh tiếp theo vẫn chạy, vì vậy routine cần quyết định rõ có tiếp tục xử lý bản ghi kế tiếp, cập nhật trạng thái hay trả kết quả lỗi.

## 4. EXIT handler hoạt động như thế nào?

EXIT handler chạy phần thân handler rồi kết thúc block BEGIN ... END nơi handler được khai báo. Luồng thực thi tiếp tục sau block đó, nếu có block bên ngoài.

Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_exit_handler()
main_block: BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT 'Bắt đầu';

    DECLARE EXIT HANDLER FOR SQLSTATE '45000'
    BEGIN
        SET v_message = 'Đã xử lý lỗi trong main_block';
        SELECT v_message AS handler_result;
    END;

    SET v_message = 'Trước SIGNAL';

    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Dừng block';

    SET v_message = 'Không chạy đến đây';
    SELECT v_message AS normal_result;
END main_block//

DELIMITER ;
~~~

Khi SIGNAL xảy ra, EXIT handler chạy. Sau đó main_block kết thúc; các câu lệnh sau SIGNAL trong cùng block không được thực thi.

Vì handler được khai báo trong block ngoài cùng của procedure, việc EXIT block này cũng kết thúc phần thân procedure. Nếu handler nằm trong block con, phạm vi thoát nhỏ hơn.

### 4.1. Khi nào nên dùng EXIT?

EXIT phù hợp khi điều kiện khiến phần còn lại của block không còn an toàn hoặc không còn ý nghĩa:

- Không thể tiếp tục xử lý vì dữ liệu đầu vào không hợp lệ.
- Một câu lệnh bắt buộc thất bại.
- Cần kết thúc sớm một bước xử lý con nhưng vẫn cho block ngoài thực hiện việc khác.
- Cần dọn dẹp hoặc phát lại lỗi trước khi rời block.

Nếu handler xử lý lỗi nghiêm trọng, cân nhắc RESIGNAL để caller nhận được lỗi ban đầu. Không nuốt lỗi nếu caller cần biết thao tác thất bại.

## 5. Phạm vi handler trong block lồng nhau

Mỗi handler thuộc về block BEGIN ... END nơi nó được khai báo. Handler có thể xử lý điều kiện phát sinh trong block đó và các block con, theo quy tắc tìm handler của MySQL.

Khi điều kiện xảy ra, MySQL tìm handler phù hợp trong block hiện tại trước. Nếu block hiện tại không có handler phù hợp, việc tìm kiếm tiếp tục ở các block bao ngoài.

Điều này tạo ra hai hệ quả quan trọng:

- Handler ở block con có thể xử lý điều kiện cục bộ mà không làm thay đổi cách block cha xử lý các lỗi khác.
- EXIT handler ở block con chỉ thoát block con. Sau khi block con kết thúc, block cha tiếp tục tại câu lệnh sau block đó.

### 5.1. EXIT ở block con, block cha vẫn tiếp tục

~~~sql
DELIMITER //

CREATE PROCEDURE demo_nested_exit()
outer_block: BEGIN
    DECLARE v_message VARCHAR(200) DEFAULT 'Bắt đầu';

    inner_block: BEGIN
        DECLARE EXIT HANDLER FOR SQLSTATE '45000'
            SET v_message = 'Đã thoát inner_block';

        SET v_message = 'Đang ở inner_block';

        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Lỗi trong block con';

        SET v_message = 'Câu lệnh này không chạy';
    END inner_block;

    SET v_message = CONCAT(v_message, '; outer_block tiếp tục');
    SELECT v_message AS final_message;
END outer_block//

DELIMITER ;
~~~

Trình tự:

1. outer_block bắt đầu.
2. inner_block bắt đầu và khai báo EXIT handler của riêng nó.
3. SIGNAL phát sinh SQLSTATE '45000'.
4. Handler trong inner_block chạy và cập nhật v_message.
5. EXIT kết thúc inner_block; câu SET ngay sau SIGNAL bị bỏ qua.
6. Luồng thực thi trở lại outer_block tại câu lệnh sau END inner_block.
7. SELECT trả về thông báo cho biết block ngoài vẫn tiếp tục.

Đây là lý do không nên hiểu EXIT là “thoát procedure” trong mọi trường hợp. Phạm vi thoát được xác định bởi block chứa khai báo handler.

### 5.2. CONTINUE ở block con

~~~sql
DELIMITER //

CREATE PROCEDURE demo_nested_continue()
outer_block: BEGIN
    DECLARE v_message VARCHAR(200) DEFAULT 'Bắt đầu';

    inner_block: BEGIN
        DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
            SET v_message = 'Đã xử lý trong inner_block';

        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Điều kiện trong block con';

        SET v_message = CONCAT(v_message, '; tiếp tục trong inner_block');
    END inner_block;

    SET v_message = CONCAT(v_message, '; outer_block tiếp tục');
    SELECT v_message AS final_message;
END outer_block//

DELIMITER ;
~~~

CONTINUE handler chạy xong thì MySQL tiếp tục câu SET ngay sau SIGNAL bên trong inner_block. Sau khi block con kết thúc bình thường, block cha tiếp tục.

### 5.3. Handler ở block ngoài xử lý điều kiện từ block con

Nếu block con không có handler phù hợp, handler ở block cha có thể nhận điều kiện:

~~~sql
DELIMITER //

CREATE PROCEDURE demo_outer_handler()
outer_block: BEGIN
    DECLARE v_handled BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '45000'
        SET v_handled = TRUE;

    inner_block: BEGIN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Block con không có handler';
    END inner_block;

    IF v_handled THEN
        SELECT 'Outer handler đã xử lý' AS result_message;
    END IF;
END outer_block//

DELIMITER ;
~~~

Handler được khai báo ở outer_block và có thể xử lý điều kiện phát sinh trong inner_block. Vì handler là CONTINUE, sau khi xử lý, luồng thực thi tiếp tục sau câu lệnh SIGNAL trong block con; sau đó block ngoài chạy phần còn lại.

Nếu handler ở outer_block là EXIT, cùng một điều kiện không được xử lý trong inner_block sẽ làm handler ngoài chạy và kết thúc outer_block. Phạm vi thoát luôn là block chứa khai báo handler được chọn, không phải block nơi câu lệnh gây lỗi nằm.

## 6. Đặt handler ở đúng vị trí khai báo

DECLARE HANDLER phải nằm trong một block BEGIN ... END và phải xuất hiện ở phần khai báo đầu block, trước các câu lệnh thực thi.

Thứ tự khai báo trong block:

1. Biến cục bộ và named condition.
2. Cursor.
3. Handler.
4. Các câu lệnh thực thi.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;

    DECLARE order_cursor CURSOR FOR
        SELECT order_id
        FROM sales_orders
        ORDER BY order_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN order_cursor;
    -- Các câu lệnh xử lý cursor đặt ở đây.
    CLOSE order_cursor;
END
~~~

Ví dụ chỉ minh họa thứ tự khai báo. Một vòng FETCH hoàn chỉnh cần kiểm tra v_done sau mỗi lần FETCH và đóng cursor ở cả luồng bình thường lẫn luồng lỗi.

### 6.1. Không khai báo handler trực tiếp trong IF hoặc LOOP

IF, CASE, LOOP, WHILE và REPEAT không tự tạo một vùng khai báo handler. Muốn giới hạn handler cho một nhánh hoặc một vòng lặp, đặt một block BEGIN ... END bên trong:

Giả sử procedure đã khai báo tham số p_process_detail, p_order_id và các biến v_detail_missing, v_detail_value, v_result ở block ngoài.

~~~sql
IF p_process_detail THEN
    detail_block: BEGIN
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_detail_missing = TRUE;

        SELECT d.detail_value
          INTO v_detail_value
        FROM order_details AS d
        WHERE d.order_id = p_order_id;

        IF NOT v_detail_missing THEN
            SET v_result = v_detail_value;
        END IF;
    END detail_block;
END IF;
~~~

Handler chỉ thuộc detail_block. Sau khi block này kết thúc, nó không còn là handler áp dụng cho các câu lệnh tiếp theo của block cha.

### 6.2. Vì sao nên dùng block nhỏ?

Block nhỏ giúp:

- Giới hạn nơi handler có thể bắt điều kiện.
- Tránh handler NOT FOUND của cursor vô tình bắt cả SELECT ... INTO không liên quan.
- Tách lỗi có thể phục hồi khỏi lỗi phải chuyển lên routine ngoài.
- Dễ xác định EXIT sẽ kết thúc phần công việc nào.
- Giảm nguy cơ một handler tổng quát che giấu lỗi của thao tác khác.

Không cần tạo block lồng cho mọi câu lệnh. Tạo block khi cần ranh giới xử lý khác nhau hoặc cần EXIT chỉ rời một phần công việc.

## 7. Thứ tự ưu tiên khi nhiều handler cùng khớp

Một điều kiện có thể khớp nhiều handler. Ví dụ lỗi duplicate key 1062 có SQLSTATE '23000', vì vậy có thể khớp handler cho mã lỗi 1062, handler cho SQLSTATE '23000' và handler chung SQLEXCEPTION.

MySQL áp dụng thứ tự ưu tiên:

1. Mã lỗi MySQL cụ thể có độ ưu tiên cao nhất.
2. SQLSTATE cụ thể có độ ưu tiên tiếp theo.
3. Nhóm điều kiện tổng quát như SQLEXCEPTION, SQLWARNING hoặc NOT FOUND có độ ưu tiên thấp hơn.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE v_integrity_error BOOLEAN DEFAULT FALSE;
    DECLARE v_other_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    DECLARE CONTINUE HANDLER FOR SQLSTATE '23000'
        SET v_integrity_error = TRUE;

    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
        SET v_other_error = TRUE;

    -- Các câu lệnh thực thi nằm sau phần khai báo.
END
~~~

Nếu lỗi 1062 xảy ra, handler cho mã lỗi cụ thể được ưu tiên hơn handler SQLSTATE và handler SQLEXCEPTION.

### 7.1. Tránh nhiều handler cùng mức ưu tiên

Nếu có nhiều handler cùng độ ưu tiên có thể xử lý cùng một điều kiện trong cùng phạm vi, lựa chọn có thể không xác định. Không thiết kế routine dựa vào thứ tự khai báo để giải quyết sự chồng lấn đó.

Nên:

- Dùng điều kiện cụ thể nhất có ý nghĩa nghiệp vụ.
- Tránh khai báo nhiều handler cùng nhóm tổng quát có thể khớp cùng một lỗi.
- Dùng named condition để biểu đạt rõ điều kiện.
- Dùng một handler chung rồi phân nhánh bằng GET DIAGNOSTICS nếu cần xử lý nhiều mã lỗi trong cùng block.

## 8. Đặt tên điều kiện bằng DECLARE ... CONDITION

Named condition giúp câu lệnh handler dễ đọc hơn mã số hoặc SQLSTATE rải rác:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_order CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_order
        SET v_duplicate = TRUE;

    -- Các câu lệnh thực thi.
END
~~~

Condition name có thể tham chiếu mã lỗi MySQL hoặc SQLSTATE:

~~~sql
DECLARE invalid_order_state CONDITION
    FOR SQLSTATE '45000';
~~~

Condition name không tự tạo ra lỗi mới; nó chỉ đặt tên cho một điều kiện đã được xác định. Để phát sinh điều kiện do ứng dụng định nghĩa, dùng SIGNAL với SQLSTATE phù hợp.

Tên điều kiện phải được khai báo trong block trước khi được dùng trong DECLARE HANDLER. Nếu nhiều block cần cùng điều kiện, khai báo condition riêng trong từng block hoặc đặt ở block ngoài có phạm vi phù hợp.

## 9. NOT FOUND handler với cursor

Một cursor đọc từng hàng từ result set. Khi FETCH không còn hàng, MySQL phát sinh NOT FOUND. Mẫu thông dụng là CONTINUE handler đặt cờ done:

~~~sql
DELIMITER //

CREATE PROCEDURE count_orders_with_cursor()
BEGIN
    DECLARE v_count BIGINT DEFAULT 0;

    cursor_block: BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_order_id BIGINT UNSIGNED;

        DECLARE order_cursor CURSOR FOR
            SELECT order_id
            FROM sales_orders
            ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        OPEN order_cursor;

        read_loop: LOOP
            FETCH order_cursor INTO v_order_id;

            IF v_done THEN
                LEAVE read_loop;
            END IF;

            SET v_count = v_count + 1;
        END LOOP;

        CLOSE order_cursor;
    END cursor_block;

    SELECT v_count AS processed_orders;
END//

DELIMITER ;
~~~

Handler được khai báo trong cursor_block, vì vậy nó chỉ tồn tại trong phạm vi xử lý cursor và các block con của block này. Khi FETCH cuối cùng không tìm thấy hàng:

1. NOT FOUND kích hoạt handler.
2. Handler đặt v_done = TRUE.
3. CONTINUE đưa luồng thực thi đến câu IF ngay sau FETCH.
4. LEAVE kết thúc read_loop.
5. CLOSE đóng cursor.
6. cursor_block kết thúc và handler hết phạm vi.
7. SELECT bên ngoài trả số hàng đã xử lý.

### 9.1. Vì sao không đặt NOT FOUND handler quá rộng?

NOT FOUND không chỉ phát sinh khi cursor hết hàng. SELECT ... INTO không tìm thấy hàng cũng phát sinh điều kiện thuộc class 02.

Nếu cùng một block có:

- Cursor FETCH.
- SELECT ... INTO có thể không tìm thấy hàng.
- Một thao tác khác có thể phát sinh NOT FOUND.

thì cùng một handler NOT FOUND có thể bắt cả các tình huống đó. Ví dụ, một SELECT ... INTO không tìm thấy hàng có thể đặt v_done = TRUE; vòng cursor sau đó hiểu nhầm rằng đã đọc hết cursor.

Giải pháp là giới hạn handler cursor trong block riêng như ví dụ trên. Nếu cần SELECT ... INTO, đặt nó ở block khác với handler riêng và cờ riêng.

### 9.2. Cờ phải được kiểm tra ngay sau FETCH

Không xử lý v_order_id trước khi kiểm tra v_done:

~~~sql
FETCH order_cursor INTO v_order_id;

IF v_done THEN
    LEAVE read_loop;
END IF;

SET v_count = v_count + 1;
~~~

Khi FETCH không tìm thấy hàng, biến đích không nhận một hàng mới. Kiểm tra cờ trước khi sử dụng v_order_id giúp tránh xử lý lại giá trị của lần FETCH trước.

## 10. CONTINUE handler cho một lỗi có thể phục hồi

CONTINUE hữu ích khi một lỗi cụ thể đã được dự kiến và routine có nhánh xử lý rõ ràng.

Ví dụ bảng lưu mã tham chiếu duy nhất:

~~~sql
CREATE TABLE external_order_refs (
    ref_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_ref VARCHAR(100) NOT NULL,
    PRIMARY KEY (ref_id),
    UNIQUE KEY uq_external_ref (external_ref)
) ENGINE = InnoDB;
~~~

Procedure sau bắt riêng lỗi duplicate key:

~~~sql
DELIMITER //

CREATE PROCEDURE register_external_ref(
    IN p_external_ref VARCHAR(100),
    OUT p_inserted BOOLEAN
)
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    SET p_inserted = FALSE;

    INSERT INTO external_order_refs (external_ref)
    VALUES (p_external_ref);

    IF v_duplicate = FALSE THEN
        SET p_inserted = TRUE;
    END IF;
END//

DELIMITER ;
~~~

Nếu external_ref đã tồn tại, INSERT phát sinh lỗi 1062, handler đặt cờ và CONTINUE cho phép routine chạy đến IF. Nếu không có lỗi, p_inserted trở thành TRUE.

Mẫu này chỉ phù hợp khi duplicate thực sự có nghĩa là “đã được đăng ký”. Nếu caller cần phân biệt duplicate với các lỗi khác, không khai báo handler SQLEXCEPTION chung để nuốt mọi lỗi.

## 11. EXIT handler cho lỗi cần chuyển về caller

Với lỗi không thể phục hồi trong routine, EXIT handler có thể ghi nhận thông tin chẩn đoán rồi RESIGNAL:

~~~sql
DELIMITER //

CREATE PROCEDURE insert_external_ref(
    IN p_external_ref VARCHAR(100)
)
BEGIN
    DECLARE v_sqlstate CHAR(5) DEFAULT NULL;
    DECLARE v_errno INT DEFAULT NULL;
    DECLARE v_message VARCHAR(512) DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_errno = MYSQL_ERRNO,
            v_message = MESSAGE_TEXT;

        RESIGNAL;
    END;

    INSERT INTO external_order_refs (external_ref)
    VALUES (p_external_ref);
END//

DELIMITER ;
~~~

GET DIAGNOSTICS đọc thông tin của điều kiện hiện tại:

- RETURNED_SQLSTATE: SQLSTATE của điều kiện.
- MYSQL_ERRNO: mã lỗi MySQL.
- MESSAGE_TEXT: thông báo lỗi.

Ví dụ giữ các giá trị trong biến cục bộ để minh họa cách lấy thông tin. Vì handler RESIGNAL, lỗi ban đầu vẫn được phát lại cho caller. Nếu cần ghi log bền vững, phải thiết kế nơi lưu log và transaction boundary phù hợp; không mặc định một thao tác ghi log trong cùng transaction sẽ còn tồn tại sau rollback.

### 11.1. RESIGNAL và SIGNAL

Hai câu lệnh có mục đích khác nhau:

| Câu lệnh | Mục đích |
|---|---|
| SIGNAL | Chủ động phát sinh một condition mới |
| RESIGNAL | Phát lại condition đang được handler xử lý, có thể giữ nguyên hoặc thay đổi một số thuộc tính |

Ví dụ phát lỗi nghiệp vụ:

~~~sql
IF p_external_ref IS NULL OR p_external_ref = '' THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'external_ref không được để trống';
END IF;
~~~

Ví dụ phát lại lỗi hiện tại:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    -- Các câu lệnh có thể phát sinh lỗi.
END
~~~

Nếu thay RESIGNAL bằng SIGNAL SQLSTATE '45000', routine tạo một condition mới và có thể làm mất mã lỗi, SQLSTATE hoặc thông tin chẩn đoán gốc. Chỉ thay lỗi khi hợp đồng của routine chủ động yêu cầu ánh xạ lỗi.

## 12. Handler không tự động rollback transaction

CONTINUE và EXIT chỉ điều khiển luồng thực thi trong stored program. Chúng không tự động COMMIT hoặc ROLLBACK transaction.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_failed BOOLEAN DEFAULT FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        SET v_failed = TRUE;
        RESIGNAL;
    END;

    -- Các câu lệnh có thể phát sinh lỗi.
END
~~~

Đoạn handler trên không rollback dữ liệu đã thay đổi. Việc rollback phụ thuộc transaction và quyết định của caller hoặc logic routine được thiết kế để sở hữu transaction.

Nếu routine có chủ đích mở transaction và sở hữu ranh giới đó, handler có thể rollback trước khi phát lại lỗi:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    -- Các câu lệnh thuộc transaction do routine sở hữu.
    COMMIT;
END
~~~

Chỉ dùng mẫu này khi routine thực sự sở hữu transaction. Stored procedure có thể được gọi bên trong transaction do ứng dụng mở; ROLLBACK trong procedure khi đó có thể rollback công việc của caller. Không thêm ROLLBACK vào handler chung nếu chưa xác định rõ ai sở hữu transaction.

Nếu ví dụ mở transaction bằng START TRANSACTION, chỉ gọi procedure theo hợp đồng không có transaction chưa kết thúc của caller; START TRANSACTION khi được thực thi trong lúc transaction khác đang mở có thể kết thúc transaction trước đó.

Với savepoint, có thể rollback về điểm đã đặt nếu thiết kế cho phép và savepoint còn tồn tại. Handler không làm cho các thao tác DDL hoặc engine không hỗ trợ transaction trở nên rollback được.

## 13. Phân biệt EXIT handler với LEAVE

EXIT handler và LEAVE đều có thể khiến luồng thực thi rời khỏi một block, nhưng chúng được kích hoạt theo cách khác nhau:

| Cơ chế | Khi nào chạy | Tác dụng |
|---|---|---|
| EXIT handler | Khi điều kiện khớp xảy ra | Chạy handler rồi thoát block nơi handler được khai báo |
| CONTINUE handler | Khi điều kiện khớp xảy ra | Chạy handler rồi tiếp tục sau câu lệnh gây điều kiện |
| LEAVE label | Khi câu lệnh LEAVE được thực thi | Chủ động rời block hoặc loop có label tương ứng |

Ví dụ LEAVE chủ động kết thúc loop:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;

    read_loop: LOOP
        IF v_count >= 100 THEN
            LEAVE read_loop;
        END IF;

        SET v_count = v_count + 1;
    END LOOP;
END
~~~

Ví dụ EXIT handler phản ứng với lỗi:

~~~sql
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    -- Các câu lệnh có thể phát sinh lỗi.
END
~~~

LEAVE không bắt lỗi và không chạy phần thân handler. EXIT handler không phải một câu lệnh LEAVE; nó được MySQL kích hoạt khi điều kiện khớp.

## 14. Điều kiện NOT FOUND từ SELECT ... INTO

NOT FOUND thường được nhắc đến cùng cursor, nhưng SELECT ... INTO không có hàng cũng phát sinh điều kiện này.

Ví dụ đặt handler trong block nhỏ để chỉ xử lý một truy vấn:

Giả sử đoạn mã nằm trong procedure có tham số IN p_order_id và OUT p_total.

~~~sql
BEGIN
    DECLARE v_order_total DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_order_found BOOLEAN DEFAULT TRUE;

    lookup_block: BEGIN
        DECLARE v_not_found BOOLEAN DEFAULT FALSE;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_not_found = TRUE;

        SELECT so.total
          INTO v_order_total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id;

        IF v_not_found THEN
            SET v_order_found = FALSE;
        END IF;
    END lookup_block;

    IF v_order_found THEN
        SET p_total = v_order_total;
    ELSE
        SET p_total = NULL;
    END IF;
END
~~~

Handler chỉ có hiệu lực trong lookup_block. Khi block kết thúc, các câu lệnh tiếp theo ở block ngoài không bị handler này bắt.

Nếu bảng có hàng nhưng cột total chứa NULL, NOT FOUND không xảy ra; v_order_found vẫn TRUE và v_order_total là NULL. Vì vậy, cần phân biệt “không có hàng” với “có hàng nhưng giá trị cột là NULL”.

## 15. Condition name và phạm vi khai báo

Condition name có phạm vi trong block nơi nó được khai báo và các block con theo quy tắc scope của stored program.

Ví dụ khai báo condition ở block ngoài để handler trong cùng block sử dụng:

~~~sql
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;
    DECLARE duplicate_reference CONDITION FOR 1062;

    DECLARE CONTINUE HANDLER FOR duplicate_reference
        SET v_duplicate = TRUE;

    -- Các câu lệnh INSERT có thể phát sinh lỗi duplicate key.
END
~~~

Nếu block con cần dùng cùng condition name, có thể đặt khai báo condition ở block ngoài. Nếu condition chỉ có ý nghĩa trong một thao tác con, khai báo nó trong block con để giới hạn phạm vi và tránh phụ thuộc không cần thiết.

Condition name chỉ là tên đại diện. Handler vẫn tuân theo mức ưu tiên của condition thực tế mà tên đó tham chiếu, chẳng hạn mã lỗi cụ thể hoặc SQLSTATE.

## 16. Những lỗi thiết kế handler thường gặp

### 16.1. Bắt SQLEXCEPTION rồi tiếp tục như không có lỗi

~~~sql
BEGIN
    DECLARE v_error BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
        SET v_error = TRUE;

    -- Các câu lệnh thực thi.
END
~~~

Handler này bắt nhiều lỗi khác nhau rồi tiếp tục câu lệnh sau lỗi. Nếu routine không kiểm tra v_error trước các bước tiếp theo, nó có thể tạo kết quả một phần hoặc ghi dữ liệu không nhất quán.

Chỉ dùng CONTINUE cho lỗi mà routine có thể phục hồi có chủ đích. Với lỗi nghiêm trọng, thường dùng EXIT và RESIGNAL để dừng block và thông báo caller.

### 16.2. Dùng một NOT FOUND handler cho cả cursor và SELECT INTO

Nếu cursor và SELECT ... INTO nằm cùng block, handler NOT FOUND của cursor có thể bắt cả trường hợp SELECT ... INTO không tìm thấy hàng. Cờ done có thể bị bật sớm và vòng cursor kết thúc nhầm.

Đặt cursor trong block riêng, dùng cờ riêng cho SELECT ... INTO và tránh dùng một handler chung cho các thao tác có ý nghĩa khác nhau.

### 16.3. Khai báo EXIT ở block quá rộng

EXIT handler khai báo ở block ngoài có thể kết thúc toàn bộ phần thân routine khi lỗi xảy ra ở một thao tác nhỏ. Nếu chỉ muốn bỏ qua một bước phụ và tiếp tục bước chính, đặt handler EXIT trong block con riêng.

### 16.4. Dùng nhiều handler tổng quát chồng lấn

Không khai báo nhiều handler cùng mức ưu tiên có thể khớp cùng một điều kiện rồi trông đợi MySQL chọn theo thứ tự viết. Lựa chọn có thể không xác định. Hãy thu hẹp điều kiện hoặc gom xử lý vào một handler.

### 16.5. Nuốt lỗi bằng handler rỗng

~~~sql
BEGIN
    DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    BEGIN
    END;

    -- Các câu lệnh có thể phát sinh lỗi.
END
~~~

Handler rỗng làm routine tiếp tục mà caller không nhận được lỗi. Nếu đây không phải hợp đồng xử lý lỗi được thiết kế rõ, nó làm mất dấu nguyên nhân thất bại và khiến việc vận hành khó điều tra.

### 16.6. Ghi log rồi làm mất lỗi gốc

Nếu handler ghi log nhưng không RESIGNAL, caller có thể không biết câu lệnh đã thất bại. Nếu handler phát sinh một lỗi mới trong lúc ghi log, thông tin ban đầu cũng có thể bị che khuất.

Giữ handler ngắn, lấy diagnostics trước khi thực hiện thao tác khác, và RESIGNAL khi caller cần nhận lỗi gốc. Việc ghi log bền vững cần thiết kế transaction riêng phù hợp.

### 16.7. Giả định EXIT luôn rollback

EXIT chỉ rời block. Dữ liệu đã ghi trong transaction có thể vẫn còn pending và cần quyết định COMMIT/ROLLBACK từ nơi sở hữu transaction. Đừng suy ra rollback chỉ từ từ khóa EXIT.

### 16.8. Khai báo handler sau câu lệnh thực thi

DECLARE HANDLER phải nằm trong phần khai báo đầu block. Đặt handler sau OPEN, SELECT hoặc SET sẽ làm routine không hợp lệ.

## 17. Quy trình chọn handler

Khi một stored program cần xử lý lỗi, đi theo thứ tự:

1. Xác định điều kiện thực tế: SQLSTATE, mã lỗi, SQLWARNING, NOT FOUND hay SQLEXCEPTION.
2. Quyết định có thể phục hồi và tiếp tục hay phải kết thúc block.
3. Chọn CONTINUE nếu cần chạy tiếp sau câu lệnh phát sinh điều kiện.
4. Chọn EXIT nếu phần còn lại của block không nên tiếp tục.
5. Đặt handler trong block nhỏ nhất có thể sở hữu logic xử lý đó.
6. Nếu nhiều handler có thể khớp, ưu tiên condition cụ thể và tránh cùng mức ưu tiên chồng lấn.
7. Nếu cần thông báo lỗi cho caller, dùng RESIGNAL hoặc ánh xạ lỗi một cách có chủ đích.
8. Xác định rõ transaction do caller hay routine sở hữu; handler không tự quyết định rollback.
9. Kiểm tra các trường hợp điều kiện không xảy ra, xảy ra một lần và xảy ra ở block con.
10. Với cursor, dùng NOT FOUND handler trong block cursor và kiểm tra cờ ngay sau FETCH.

## 18. Checklist trước khi hoàn tất routine

- [ ] Mọi DECLARE HANDLER nằm trong phần khai báo đầu block BEGIN ... END.
- [ ] Biến và condition được khai báo trước cursor; cursor trước handler.
- [ ] CONTINUE và EXIT được chọn theo luồng thực thi mong muốn.
- [ ] Đã xác định EXIT thoát block nào bằng vị trí khai báo handler.
- [ ] Handler ở block con không làm gián đoạn block cha ngoài dự kiến.
- [ ] Handler ở block ngoài chỉ bắt điều kiện chưa được xử lý ở block trong.
- [ ] Đã phân biệt SQLWARNING, NOT FOUND và SQLEXCEPTION.
- [ ] NOT FOUND của cursor không bắt nhầm SELECT ... INTO không liên quan.
- [ ] Cờ kết thúc được kiểm tra ngay sau FETCH.
- [ ] Điều kiện cụ thể được ưu tiên hơn nhóm điều kiện tổng quát.
- [ ] Không có nhiều handler cùng mức ưu tiên chồng lấn mà routine phụ thuộc vào lựa chọn của MySQL.
- [ ] Handler không vô tình nuốt lỗi mà caller cần biết.
- [ ] RESIGNAL được dùng khi cần phát lại lỗi ban đầu.
- [ ] GET DIAGNOSTICS được gọi trước khi thông tin lỗi bị thay đổi bởi thao tác khác.
- [ ] Không giả định EXIT tự động rollback transaction.
- [ ] Đã kiểm tra luồng bình thường, lỗi trong block con và lỗi ở block ngoài.

## Kết luận

CONTINUE và EXIT khác nhau ở điểm tiếp tục luồng thực thi. CONTINUE chạy handler rồi tiếp tục sau câu lệnh phát sinh điều kiện; EXIT chạy handler rồi thoát block nơi handler được khai báo. Phạm vi block vì vậy quyết định mức ảnh hưởng của một lỗi đến phần còn lại của routine.

Hãy đặt handler gần thao tác cần xử lý, dùng NOT FOUND riêng cho vùng cursor, chọn điều kiện đủ cụ thể và tránh nuốt lỗi ngoài ý muốn. Khi lỗi cần chuyển về caller, lấy diagnostics nếu cần rồi RESIGNAL. Cuối cùng, luôn xác định transaction do ai sở hữu vì handler chỉ điều khiển luồng stored program, không tự động rollback dữ liệu.
