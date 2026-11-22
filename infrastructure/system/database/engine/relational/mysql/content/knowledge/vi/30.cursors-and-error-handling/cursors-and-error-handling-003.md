# OPEN, FETCH, CLOSE và quản lý vòng đời cursor

Cursor trong stored program cho phép MySQL đọc kết quả của một câu SELECT từng hàng một. Vòng đời cơ bản gồm khai báo cursor, OPEN để mở kết quả, FETCH để lấy từng hàng vào biến cục bộ và CLOSE khi xử lý xong. Cursor hữu ích khi mỗi hàng cần một bước xử lý tuần tự khó biểu diễn bằng một câu SQL tập hợp, nhưng thường tốn tài nguyên và chậm hơn thao tác set-based.

Trong module DATABASE_MYSQL, bài học này tập trung vào thứ tự khai báo cursor, ý nghĩa của OPEN/FETCH/CLOSE, cách phát hiện hết dữ liệu bằng NOT FOUND, xử lý cursor rỗng, đóng cursor khi có lỗi và thiết kế phạm vi handler để không bắt nhầm điều kiện NOT FOUND từ câu lệnh khác.

## 1. Cursor là gì?

Cursor là cơ chế duyệt tuần tự các hàng do một câu SELECT trả về trong stored program. Thay vì xử lý toàn bộ tập kết quả bằng một câu UPDATE, INSERT hoặc SELECT, routine có thể lấy từng hàng, đọc các cột vào biến cục bộ và thực hiện logic cho hàng đó.

Cursor trong MySQL có các đặc điểm quan trọng:

- Read-only: không dùng cursor để sửa trực tiếp hàng hiện tại bằng cú pháp UPDATE ... WHERE CURRENT OF.
- Nonscrollable: chỉ FETCH tuần tự về phía trước; không nhảy đến hàng trước hoặc một vị trí tùy ý.
- Asensitive: server có thể dùng bản sao kết quả hoặc không; routine không nên dựa vào việc thay đổi bảng nguồn trong lúc cursor đang mở sẽ được phản ánh theo một cách cụ thể.
- Gắn với phạm vi khai báo: cursor chỉ được sử dụng trong block đã khai báo nó và các phần lệnh nằm trong phạm vi đó.

Cursor không phải result set được trả về cho ứng dụng. Nó là tài nguyên nội bộ của stored program để routine duyệt dữ liệu.

## 2. Vòng đời cursor

Một cursor được sử dụng theo trình tự:

1. DECLARE CURSOR: khai báo câu SELECT cung cấp dữ liệu.
2. DECLARE handler: chuẩn bị xử lý NOT FOUND khi FETCH hết hàng và các lỗi cần cleanup.
3. OPEN: thực thi truy vấn cursor và mở kết quả để đọc.
4. FETCH: lấy hàng kế tiếp vào các biến đích.
5. Kiểm tra cờ hết dữ liệu trước khi dùng các biến vừa FETCH.
6. Lặp lại FETCH cho đến khi nhận NOT FOUND.
7. CLOSE: đóng cursor và giải phóng tài nguyên.

Sơ đồ:

~~~mermaid
flowchart TD
    A[DECLARE cursor và handler] --> B[OPEN cursor]
    B --> C[FETCH hàng kế tiếp]
    C --> D{Có hàng?}
    D -->|Có| E[Xử lý hàng]
    E --> C
    D -->|Không: NOT FOUND| F[CLOSE cursor]
    F --> G[Kết thúc block]
~~~

OPEN và CLOSE không thể đảo thứ tự. FETCH chỉ hợp lệ sau OPEN và trước CLOSE. Gọi CLOSE trên cursor chưa mở hoặc đã đóng sẽ gây lỗi.

## 3. Khai báo cursor bằng DECLARE

Cú pháp cơ bản:

~~~sql
DECLARE cursor_name CURSOR FOR select_statement;
~~~

SELECT trong khai báo cursor phải trả về một result set. Không đặt INTO biến cục bộ ở cuối SELECT của cursor; việc nhận hàng được thực hiện bằng FETCH.

Ví dụ:

~~~sql
DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_id;
~~~

Cursor có thể tham chiếu parameter hoặc biến cục bộ đã được khai báo trước đó trong cùng phạm vi. Trong ví dụ, p_customer_id là tham số procedure. Điều kiện này giúp cursor chỉ duyệt đơn hàng của một khách hàng.

Định nghĩa SELECT của cursor được cố định trong routine. Cursor không phải cách thay thế cho dynamic SQL để thay đổi tên bảng hoặc cấu trúc SELECT tùy ý ở mỗi lần FETCH.

## 4. Thứ tự DECLARE trong block

MySQL yêu cầu mọi khai báo đứng ở đầu block và theo đúng thứ tự:

1. Biến cục bộ và named condition.
2. Cursor.
3. Handler.

Ví dụ:

~~~sql
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
    -- Các câu lệnh xử lý tiếp theo.
END
~~~

Không đặt DECLARE CURSOR sau OPEN, SET, SELECT hoặc một câu lệnh thực thi khác. Nếu cần cursor chỉ cho một phần xử lý, tạo block BEGIN ... END con và khai báo cursor ở đầu block con đó.

## 5. OPEN: mở cursor và bắt đầu truy vấn

OPEN thực thi câu SELECT đã khai báo cho cursor và chuẩn bị kết quả để FETCH:

~~~sql
OPEN cur_orders;
~~~

Một số điểm cần nhớ:

- Cursor phải được khai báo trong phạm vi hiện tại.
- Không OPEN lại một cursor đang mở.
- OPEN không đưa từng hàng ra cho caller; routine phải dùng FETCH.
- Nếu truy vấn không có hàng, OPEN vẫn có thể thành công; lần FETCH đầu tiên mới phát NOT FOUND.
- Lỗi khi thực thi SELECT có thể xảy ra tại OPEN; handler SQLEXCEPTION phù hợp có thể xử lý và truyền lỗi lên caller.

OPEN không tự động tạo transaction riêng. Câu SELECT của cursor chịu ảnh hưởng transaction, isolation level và storage engine như các truy vấn khác trong session.

## 6. FETCH: lấy một hàng vào biến

Cú pháp:

~~~sql
FETCH cursor_name INTO variable_name [, variable_name] ...;
~~~

Số biến đích phải khớp số cột trong SELECT của cursor, theo đúng thứ tự tương ứng. Kiểu dữ liệu biến nên phù hợp với cột nguồn để tránh chuyển đổi không mong muốn.

Ví dụ cursor trả hai cột:

~~~sql
DECLARE v_order_id BIGINT UNSIGNED;
DECLARE v_amount DECIMAL(12,2);

DECLARE cur_orders CURSOR FOR
    SELECT order_id, total_amount
    FROM orders;

FETCH cur_orders INTO v_order_id, v_amount;
~~~

Sau FETCH thành công, biến v_order_id nhận cột thứ nhất và v_amount nhận cột thứ hai của hàng hiện tại. FETCH tiếp theo di chuyển đến hàng kế tiếp.

MySQL cursor không hỗ trợ FETCH FIRST, LAST, PRIOR hoặc ABSOLUTE như cursor scrollable ở một số hệ quản trị khác. Hãy thiết kế truy vấn ORDER BY nếu cần thứ tự xử lý xác định.

## 7. NOT FOUND handler để phát hiện hết dữ liệu

Khi FETCH không còn hàng, MySQL phát điều kiện NOT FOUND (SQLSTATE class 02). Cách phổ biến là khai báo CONTINUE HANDLER để bật cờ:

~~~sql
DECLARE v_done BOOLEAN DEFAULT FALSE;

DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
~~~

Sau FETCH, kiểm tra cờ trước khi xử lý biến:

~~~sql
FETCH cur_orders INTO v_order_id, v_amount;

IF v_done THEN
    LEAVE read_loop;
END IF;

-- Chỉ xử lý hàng khi FETCH thành công.
SET v_total = v_total + v_amount;
~~~

CONTINUE nghĩa là sau khi handler chạy, luồng thực thi tiếp tục ở câu lệnh sau câu lệnh phát sinh điều kiện. Vì vậy, routine cần tự kiểm tra v_done và thoát vòng lặp. Nếu không kiểm tra, nó có thể xử lý lại giá trị biến còn sót từ lần FETCH trước.

Không dùng EXIT HANDLER FOR NOT FOUND nếu muốn tiếp tục thực hiện logic cleanup sau lần FETCH cuối trong cùng block; EXIT handler sẽ thoát khỏi block mà handler được khai báo. Với vòng đọc thông thường, CONTINUE HANDLER kết hợp cờ done dễ kiểm soát hơn.

## 8. Vòng FETCH chuẩn

Mẫu cơ bản:

~~~sql
read_loop: LOOP
    FETCH cur_orders INTO v_order_id, v_amount;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Xử lý hàng hiện tại.
    SET v_total = v_total + v_amount;
END LOOP;
~~~

Điều kiện v_done phải được kiểm tra ngay sau FETCH và trước khi dùng các biến đích. Lần FETCH cuối cùng không trả hàng; handler bật cờ, vòng lặp thoát và routine chuyển đến CLOSE.

Không viết:

~~~sql
FETCH cur_orders INTO v_order_id, v_amount;
SET v_total = v_total + v_amount;
IF v_done THEN
    LEAVE read_loop;
END IF;
~~~

Đoạn trên xử lý biến trước khi kiểm tra FETCH thất bại. Khi hết dữ liệu, biến đích có thể vẫn chứa giá trị từ lần FETCH trước, dẫn đến cộng lặp hàng cuối.

## 9. CLOSE: đóng cursor đúng lúc

Sau khi duyệt xong, gọi:

~~~sql
CLOSE cur_orders;
~~~

CLOSE kết thúc việc sử dụng cursor hiện tại. Sau CLOSE, không được FETCH tiếp cho đến khi cursor được OPEN lại. Cursor cũng được MySQL tự đóng khi block khai báo nó kết thúc, nhưng nên CLOSE tường minh để vòng đời tài nguyên dễ đọc và dễ kiểm soát.

Không gọi CLOSE hai lần. Không gọi CLOSE nếu OPEN chưa thành công. Trong routine có nhiều nhánh thoát, cần đảm bảo mọi đường đi sau OPEN đều đóng cursor trước khi rời block.

## 10. Cursor rỗng và dữ liệu thay đổi

Cursor có thể trả về 0 hàng:

- OPEN vẫn mở cursor.
- FETCH đầu tiên phát NOT FOUND.
- Handler đặt v_done = TRUE.
- Vòng lặp thoát mà không xử lý hàng nào.
- CLOSE vẫn được gọi.

Không xem cursor rỗng là lỗi ứng dụng nếu nghiệp vụ cho phép không có dữ liệu. Nếu bắt buộc phải có ít nhất một hàng, hãy kiểm tra sau vòng lặp và phát lỗi nghiệp vụ phù hợp.

Vì cursor là asensitive, MySQL không cam kết routine sẽ nhìn thấy mọi thay đổi được thực hiện đồng thời trên bảng nguồn theo một cách cố định. Tránh cập nhật/xóa chính các hàng nguồn trong lúc đang duyệt cursor nếu thuật toán phụ thuộc vào thứ tự hoặc tập kết quả ổn định. Nếu cần một tập làm việc ổn định, hãy xác định transaction/isolation hoặc chụp khóa hàng vào bảng staging phù hợp.

## 11. NOT FOUND có thể đến từ câu lệnh khác

NOT FOUND không chỉ được phát bởi FETCH. Một SELECT ... INTO không trả hàng cũng phát NOT FOUND. Nếu cùng một handler được khai báo ở block chứa cả cursor và SELECT ... INTO, handler có thể bật v_done ngoài ý muốn và khiến vòng lặp kết thúc sớm.

Ví dụ dễ gây lỗi logic:

~~~sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_name VARCHAR(120);
    DECLARE cur_orders CURSOR FOR
        SELECT order_id FROM orders;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = -1;

    -- SELECT INTO không có hàng đã bật v_done.
    -- Vòng FETCH có thể thoát ngay cả khi cursor còn hàng.
END
~~~

Giải pháp tốt là giới hạn phạm vi handler. Đặt vòng cursor trong một block con riêng, trong đó NOT FOUND chỉ được dùng cho FETCH. Nếu cần SELECT ... INTO có thể không có hàng, xử lý nó trong block khác với handler riêng hoặc dùng một cách truy vấn trả đúng một hàng như aggregate khi phù hợp.

## 12. Ví dụ đầy đủ: duyệt đơn hàng và cộng tổng

Giả sử có bảng:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_order (customer_id, order_id)
) ENGINE=InnoDB;
~~~

Procedure sau duyệt các đơn hàng của một khách hàng, đếm số đơn và cộng tổng tiền:

~~~sql
DELIMITER //

CREATE PROCEDURE summarize_customer_orders(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_order_count BIGINT DEFAULT 0;
    DECLARE v_total_amount DECIMAL(14,2) DEFAULT 0.00;

    BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
        DECLARE v_order_id BIGINT UNSIGNED;
        DECLARE v_order_amount DECIMAL(12,2);

        DECLARE cur_orders CURSOR FOR
            SELECT order_id, total_amount
            FROM orders
            WHERE customer_id = p_customer_id
            ORDER BY order_id;

        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            IF v_cursor_open THEN
                CLOSE cur_orders;
                SET v_cursor_open = FALSE;
            END IF;
            RESIGNAL;
        END;

        OPEN cur_orders;
        SET v_cursor_open = TRUE;

        read_loop: LOOP
            FETCH cur_orders INTO v_order_id, v_order_amount;

            IF v_done THEN
                LEAVE read_loop;
            END IF;

            SET v_order_count = v_order_count + 1;
            SET v_total_amount = v_total_amount + v_order_amount;
        END LOOP;

        CLOSE cur_orders;
        SET v_cursor_open = FALSE;
    END;

    SELECT
        p_customer_id AS customer_id,
        v_order_count AS order_count,
        v_total_amount AS total_amount;
END//

DELIMITER ;
~~~

Khối ngoài giữ v_order_count và v_total_amount vì cần trả kết quả sau khi block cursor kết thúc. Khối con chứa cursor, biến FETCH, cờ done và các handler. Khi có lỗi SQLEXCEPTION sau khi cursor đã mở, EXIT HANDLER đóng cursor rồi RESIGNAL để caller vẫn nhận lỗi gốc.

Nếu không có đơn hàng, FETCH đầu tiên phát NOT FOUND, v_done chuyển thành TRUE, vòng lặp kết thúc, cursor được đóng và procedure trả số lượng 0 cùng tổng 0.00.

Gọi procedure:

~~~sql
CALL summarize_customer_orders(42);
~~~

Ví dụ này nhằm minh họa vòng đời cursor. Trong ứng dụng thật, phép tính đếm và tổng tiền nên được viết bằng một câu truy vấn tập hợp:

~~~sql
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(total_amount), 0.00) AS total_amount
FROM orders
WHERE customer_id = 42;
~~~

Truy vấn set-based thường ngắn hơn, giảm số lần chuyển hàng qua stored program và cho optimizer nhiều cơ hội chọn kế hoạch hiệu quả. Chỉ dùng cursor khi mỗi hàng thực sự cần logic tuần tự hoặc tương tác không thể biểu diễn hợp lý bằng SQL tập hợp.

## 13. Đóng cursor khi có lỗi

Nếu một câu lệnh trong vòng lặp phát lỗi, luồng có thể rời routine trước khi đến CLOSE. Khi cần quản lý tài nguyên tường minh, khai báo EXIT HANDLER FOR SQLEXCEPTION sau khai báo cursor:

~~~sql
DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
DECLARE cur_items CURSOR FOR
    SELECT item_id FROM order_items;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_items;
        SET v_cursor_open = FALSE;
    END IF;
    RESIGNAL;
END;
~~~

Sau OPEN, đặt cờ:

~~~sql
OPEN cur_items;
SET v_cursor_open = TRUE;
~~~

Sau CLOSE bình thường:

~~~sql
CLOSE cur_items;
SET v_cursor_open = FALSE;
~~~

Cờ chỉ phản ánh trạng thái OPEN thành công trong logic routine. Nếu OPEN thất bại, cờ vẫn FALSE nên handler không cố CLOSE cursor chưa mở. Nếu lỗi phát sinh sau OPEN, handler đóng cursor rồi RESIGNAL để không nuốt lỗi.

Không thay RESIGNAL bằng một SELECT thông báo rồi tiếp tục như thể xử lý thành công, trừ khi routine có hợp đồng lỗi được thiết kế rõ. Caller cần biết thao tác thất bại để quyết định rollback hoặc retry.

## 14. Transaction và khóa khi dùng cursor

Cursor không tự mở transaction và không tự khóa tất cả hàng mà nó đọc. SELECT của cursor tuân theo transaction hiện tại, isolation level và storage engine.

Với InnoDB:

- Nếu autocommit bật và caller không mở transaction tường minh, các câu lệnh độc lập tuân theo autocommit.
- Nếu caller đã mở transaction, truy vấn cursor tham gia ngữ cảnh transaction của session.
- Một SELECT thông thường thường là consistent read theo isolation level hiện tại.
- Cursor không tự biến SELECT thành SELECT ... FOR UPDATE.

Không giữ cursor mở trong lúc chờ người dùng, gọi HTTP hoặc thực hiện công việc ngoài database lâu dài. Việc giữ transaction/cursor lâu có thể kéo dài snapshot, giữ tài nguyên và làm tăng áp lực vận hành.

Nếu cần khóa các hàng để xử lý cạnh tranh, hãy thiết kế transaction và locking read riêng, giới hạn phạm vi hàng bằng index, xử lý nhanh và commit/rollback rõ ràng. Đừng dựa vào cursor read-only để bảo đảm độc quyền cập nhật.

## 15. Hiệu năng và giới hạn thực tế

Cursor xử lý theo từng hàng nên thường có overhead cho mỗi lần FETCH và mỗi thao tác trong vòng lặp. Với hàng trăm nghìn hoặc hàng triệu bản ghi, row-by-row có thể chậm hơn nhiều so với một câu SQL set-based.

Trước khi dùng cursor, hãy tự hỏi:

- Có thể thay vòng lặp bằng UPDATE ... JOIN, INSERT ... SELECT hoặc aggregate không?
- Có thể dùng CASE, CTE hoặc window function để biểu diễn quy tắc không?
- Có cần xử lý theo thứ tự từng hàng hay chỉ cần kết quả cuối?
- Có thể chia batch bằng khóa tăng dần thay vì giữ một cursor rất lâu không?
- Cursor SELECT có index hỗ trợ WHERE và ORDER BY không?

Trong ví dụ orders, index (customer_id, order_id) hỗ trợ lọc theo customer_id và duyệt theo order_id. Index không loại bỏ chi phí xử lý từng hàng, nhưng có thể giảm chi phí tìm và sắp thứ tự dữ liệu đầu vào.

Không thêm index chỉ để phục vụ một cursor nếu index đó làm workload ghi bị chậm đáng kể. Đo bằng EXPLAIN cho SELECT của cursor và đo toàn bộ procedure trên dữ liệu đại diện.

## 16. Cursor lồng nhau

Có thể khai báo cursor trong block con để duyệt tập kết quả thứ hai cho từng hàng của cursor ngoài. Khi làm vậy, mỗi cursor cần:

- Biến đích FETCH riêng.
- Cờ done riêng.
- Handler NOT FOUND có phạm vi rõ.
- OPEN và CLOSE ở đúng block.

Không dùng chung một cờ done cho hai cursor nếu hai luồng FETCH có thể kết thúc độc lập. Một NOT FOUND từ cursor trong có thể bật cờ của cursor ngoài và làm vòng lặp ngoài kết thúc sai.

Mẫu tổ chức an toàn là đặt mỗi vòng cursor trong block con riêng với handler NOT FOUND riêng. Tuy nhiên, cursor lồng nhau có thể tạo số truy vấn tăng theo số hàng ngoài (N+1 pattern). Nếu có thể, thay bằng JOIN hoặc truy vấn set-based.

## 17. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| FETCH trước OPEN | Cursor chưa có result set đang mở | Gọi OPEN trước FETCH |
| Quên CLOSE | Không giải phóng cursor đúng lúc | CLOSE trên mọi đường thoát bình thường và cleanup trong handler |
| CLOSE cursor chưa mở | OPEN thất bại hoặc cursor đã đóng | Theo dõi trạng thái mở bằng cờ |
| Thiếu NOT FOUND handler | FETCH hết hàng phát lỗi | Khai báo CONTINUE HANDLER và cờ done |
| Xử lý biến trước khi kiểm tra done | Có thể dùng lại giá trị FETCH trước | Kiểm tra cờ ngay sau FETCH |
| Handler NOT FOUND bắt SELECT INTO | Cùng block có truy vấn không tìm thấy hàng | Tách block và phạm vi handler |
| Số biến FETCH không khớp số cột | Danh sách đích sai | Đối chiếu số cột và thứ tự SELECT |
| Dùng cursor để tính SUM/COUNT đơn giản | Xử lý từng hàng không cần thiết | Dùng aggregate set-based |
| Thay đổi bảng nguồn khi cursor đang duyệt | Kết quả asensitive, hành vi không nên được giả định | Dùng staging hoặc transaction/locking strategy rõ |
| Không truyền lỗi ra caller | Handler nuốt SQLEXCEPTION | Cleanup rồi RESIGNAL nếu không xử lý triệt để |
| Cursor lồng dùng chung done flag | Handler của một cursor ảnh hưởng cursor kia | Dùng block, cờ và handler riêng |

## 18. Checklist quản lý vòng đời cursor

1. Xác nhận bài toán thực sự cần xử lý từng hàng; ưu tiên set-based khi có thể.
2. Chọn SELECT có thứ tự xác định nếu thứ tự xử lý quan trọng.
3. Đảm bảo WHERE và ORDER BY có index phù hợp với workload.
4. Khai báo biến/condition trước cursor và cursor trước handler.
5. Khai báo handler NOT FOUND trong phạm vi chỉ chứa các thao tác cần bắt.
6. OPEN đúng một lần trước khi FETCH.
7. FETCH vào đúng số lượng biến và đúng thứ tự cột.
8. Kiểm tra cờ done ngay sau FETCH.
9. CLOSE sau vòng lặp dù cursor có 0 hàng.
10. Dùng EXIT HANDLER để CLOSE khi lỗi sau OPEN và RESIGNAL nếu cần truyền lỗi lên.
11. Không CLOSE hai lần hoặc FETCH sau CLOSE.
12. Không giữ cursor/transaction mở khi làm công việc ngoài database.
13. Kiểm tra hành vi với tập rỗng, một hàng, nhiều hàng và lỗi giữa vòng lặp.
14. Đo hiệu năng toàn bộ routine, không chỉ câu SELECT của cursor.

## 19. Bài tập thực hành

1. Tạo bảng orders với order_id, customer_id và total_amount; khai báo cursor lọc theo customer_id.
2. Viết procedure OPEN cursor, FETCH một hàng và CLOSE; kiểm tra giá trị nhận được.
3. Viết vòng LOOP có CONTINUE HANDLER FOR NOT FOUND và cờ v_done.
4. Thử customer_id không có đơn hàng; xác nhận cursor rỗng vẫn được đóng bình thường.
5. Cố tình đặt lệnh cộng tổng trước kiểm tra v_done; quan sát lỗi cộng lặp hàng cuối rồi sửa lại thứ tự.
6. Thêm SELECT ... INTO không tìm thấy hàng vào cùng block; quan sát handler NOT FOUND có thể ảnh hưởng cờ cursor. Sau đó tách thành block riêng.
7. Thêm EXIT HANDLER FOR SQLEXCEPTION để đóng cursor khi câu lệnh xử lý hàng phát lỗi; dùng RESIGNAL để caller nhận lỗi.
8. Tạo hai cursor lồng nhau với cờ done và handler riêng; xác nhận cursor trong kết thúc không làm cursor ngoài thoát sớm.
9. So sánh procedure dùng cursor để tính COUNT/SUM với một SELECT aggregate; đo thời gian trên tập dữ liệu đủ lớn.
10. Dùng EXPLAIN cho SELECT của cursor và đánh giá index hỗ trợ điều kiện lọc cùng thứ tự ORDER BY.

Bạn hoàn thành bài khi triển khai đúng vòng đời DECLARE → OPEN → FETCH → CLOSE, xử lý được tập rỗng bằng NOT FOUND, bảo đảm cursor được đóng cả khi có lỗi và giải thích được khi nào nên thay cursor bằng câu SQL set-based. Quản lý phạm vi handler và tài nguyên đúng cách quan trọng không kém cú pháp FETCH.
