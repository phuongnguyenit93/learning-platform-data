# SQL SECURITY, DEFINER và quyền người thực thi

Stored program trong MySQL có thể chạy bằng quyền của tài khoản định nghĩa đối tượng hoặc quyền của tài khoản gọi đối tượng. Cơ chế này được điều khiển bởi thuộc tính DEFINER và đặc tính SQL SECURITY. Hiểu đúng hai khái niệm giúp thiết kế procedure, function, view, trigger và event an toàn, đồng thời tránh cấp quyền trực tiếp lên bảng dữ liệu cho mọi ứng dụng.

Với SQL SECURITY DEFINER, câu lệnh bên trong routine hoặc view được kiểm tra quyền theo tài khoản DEFINER. Người gọi vẫn cần quyền tham chiếu đối tượng, chẳng hạn EXECUTE cho procedure hoặc SELECT cho view, nhưng không nhất thiết có quyền trực tiếp trên các bảng mà đối tượng truy cập. Với SQL SECURITY INVOKER, các thao tác bên trong được kiểm tra theo quyền của người gọi. Trigger và event không có tùy chọn SQL SECURITY; chúng luôn chạy trong security context của DEFINER.

Đây là ranh giới bảo mật quan trọng. Một procedure DEFINER có thể cung cấp một thao tác dữ liệu được giới hạn cho ứng dụng, nhưng cũng có thể trở thành đường nâng quyền nếu DEFINER quá mạnh, tham số không được kiểm tra hoặc SQL động được ghép từ dữ liệu không tin cậy. Bài học này trình bày cách MySQL xác định security context, cách cấp quyền tối thiểu, cách triển khai DEFINER ổn định và cách kiểm tra các đối tượng có nguy cơ trở thành orphan.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt DEFINER với tài khoản tạo đối tượng và tài khoản gọi đối tượng.
- Giải thích SQL SECURITY DEFINER và SQL SECURITY INVOKER.
- Biết mặc định SQL SECURITY của stored routine và view.
- Xác định security context của trigger và event.
- Phân biệt USER() và CURRENT_USER() khi kiểm tra quyền thực thi.
- Thiết kế procedure DEFINER để cung cấp quyền truy cập có kiểm soát.
- Thiết kế routine INVOKER khi người gọi phải có quyền trên dữ liệu nguồn.
- Cấp CREATE ROUTINE, ALTER ROUTINE và EXECUTE đúng phạm vi.
- Hiểu quyền cần có để đặt DEFINER khác tài khoản hiện tại.
- Quản lý role và quyền hiệu lực của tài khoản DEFINER.
- Tránh orphan stored object khi đổi tên hoặc xóa tài khoản.
- Kiểm tra DEFINER, SQL SECURITY và grants bằng SHOW CREATE cùng INFORMATION_SCHEMA.
- Áp dụng nguyên tắc least privilege, kiểm tra tham số và phòng chống SQL injection.

## 1. Ba danh tính cần phân biệt

Khi một ứng dụng gọi stored procedure, có thể có ba danh tính khác nhau:

1. **Creator**: tài khoản đã chạy câu lệnh CREATE để tạo procedure.
2. **DEFINER**: tài khoản được lưu trong định nghĩa đối tượng và được dùng làm security context khi đối tượng chạy theo chế độ DEFINER.
3. **Invoker**: tài khoản thực sự gọi procedure hoặc tham chiếu view.

Ba danh tính có thể trùng nhau, nhưng không bắt buộc. Ví dụ, pipeline triển khai có thể tạo procedure với DEFINER là tài khoản service chuyên dụng; người dùng ứng dụng chỉ có EXECUTE trên procedure đó.

Nếu câu lệnh CREATE không chỉ định DEFINER, MySQL mặc định dùng tài khoản thực thi câu lệnh CREATE làm DEFINER. Vì vậy, chạy migration bằng tài khoản deploy mà bỏ qua DEFINER có thể vô tình khiến tài khoản deploy trở thành DEFINER của tất cả routine mới.

DEFINER không phải tên nhóm quyền và cũng không phải một bản sao quyền được chụp tại thời điểm CREATE. Khi routine chạy theo DEFINER, MySQL kiểm tra quyền theo tài khoản DEFINER tại thời điểm thực thi. Nếu quyền cần thiết bị thu hồi, routine có thể bắt đầu lỗi dù định nghĩa routine không thay đổi.

## 2. DEFINER là gì?

DEFINER là thuộc tính nhận diện một MySQL account theo cặp user và host. Ví dụ:

    DEFINER = 'orders_api_definer'@'localhost'

Tài khoản này là security principal được tham chiếu trong metadata của đối tượng. Nó không nhất thiết là người đã tạo đối tượng.

Khi bỏ qua DEFINER:

    CREATE PROCEDURE app_db.list_orders()
    BEGIN
        SELECT order_id
        FROM app_db.orders;
    END;

MySQL gán tài khoản thực thi CREATE PROCEDURE làm DEFINER. Để làm rõ ý định và giảm phụ thuộc vào tài khoản migration, có thể chỉ định rõ:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.list_orders()
    BEGIN
        SELECT order_id
        FROM app_db.orders;
    END;

CURRENT_USER trong mệnh đề DEFINER đại diện cho tài khoản hiện hành đã xác thực với server tại thời điểm tạo đối tượng.

### 2.1. DEFINER không tự cấp quyền

Việc ghi:

    DEFINER = 'orders_api_definer'@'localhost'

không tự động cấp SELECT, INSERT, UPDATE hoặc DELETE cho tài khoản đó. Tài khoản DEFINER phải được tạo và được cấp các quyền mà phần thân routine cần thực hiện.

Nếu routine đọc app_db.orders, tài khoản DEFINER cần quyền SELECT thích hợp trên bảng đó. Nếu routine cập nhật bảng, DEFINER cần quyền UPDATE hoặc quyền ghi tương ứng. Quyền được kiểm tra theo ngữ cảnh thực thi.

Không dùng tài khoản root hoặc tài khoản DBA làm DEFINER chỉ để tránh lỗi quyền. Hãy tạo tài khoản chuyên dụng có đúng quyền cần thiết cho đối tượng.

## 3. SQL SECURITY điều khiển quyền của ai được kiểm tra

Đối với stored procedure, stored function và view, MySQL hỗ trợ hai giá trị:

- DEFINER: kiểm tra các thao tác bên trong bằng quyền của tài khoản DEFINER.
- INVOKER: kiểm tra các thao tác bên trong bằng quyền của tài khoản gọi hoặc tham chiếu đối tượng.

Nếu bỏ qua SQL SECURITY, mặc định là DEFINER.

| Đặc tính | SQL SECURITY DEFINER | SQL SECURITY INVOKER |
|---|---|---|
| Quyền truy cập đối tượng nguồn | Quyền của DEFINER | Quyền của invoker |
| Người gọi cần quyền trên routine | Có, thường là EXECUTE | Có, thường là EXECUTE |
| Người gọi cần quyền trực tiếp trên bảng nguồn | Không nhất thiết | Có, theo các thao tác routine thực hiện |
| Dùng để đóng gói quyền truy cập giới hạn | Phù hợp | Không phải mục tiêu chính |
| Rủi ro nếu định nghĩa sai | Có thể tạo đường nâng quyền | Thường giới hạn theo quyền người gọi |

SQL SECURITY không thay đổi logic SQL trong routine. Nó thay đổi danh tính mà MySQL dùng để kiểm tra quyền khi các statement bên trong được thực thi.

Các characteristic như READS SQL DATA, MODIFIES SQL DATA, CONTAINS SQL và NO SQL mô tả loại hoạt động của routine cho server và người đọc schema. Chúng không thay thế GRANT và không phải cơ chế sandbox tự động ngăn routine thực hiện statement khác với nhãn đã khai báo. Quyền thực tế vẫn được kiểm tra theo SQL SECURITY context và các privilege của account tương ứng.

### 3.1. SQL SECURITY DEFINER

Ví dụ:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_order_summary(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY DEFINER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END;

Giả sử DEFINER có SELECT trên app_db.orders, còn tài khoản ứng dụng chỉ có EXECUTE trên procedure. Ứng dụng có thể gọi procedure và nhận kết quả mà không được cấp SELECT trực tiếp trên toàn bộ bảng orders.

Đây là cách đóng gói quyền truy cập thường dùng cho API database. Procedure phải giới hạn dữ liệu được trả về theo tham số và quy tắc nghiệp vụ. Nếu procedure cho phép đọc mọi khách hàng bằng một tham số tùy ý, nó có thể mở rộng quyền dữ liệu vượt quá ý định ban đầu.

Ví dụ trên chỉ minh họa ranh giới quyền giữa caller và DEFINER; nó chưa triển khai tenant authorization. Trong hệ thống nhiều khách hàng, không được coi p_customer_id do caller gửi là bằng chứng caller sở hữu dữ liệu đó. Procedure production phải kiểm tra customer/tenant ownership bằng một danh tính đáng tin cậy và quy tắc nghiệp vụ đã xác thực. Nếu ứng dụng dùng chung một database account cho nhiều người dùng, USER() cũng chỉ nhận diện account kết nối dùng chung, không tự nhận diện end user.

### 3.2. SQL SECURITY INVOKER

Ví dụ:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_my_order_rows(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY INVOKER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END;

Với INVOKER, caller phải có EXECUTE trên procedure và quyền SELECT cần thiết trên app_db.orders. Nếu caller chỉ có EXECUTE mà không có SELECT trên bảng, câu lệnh bên trong sẽ thất bại vì quyền của DEFINER không được dùng thay cho quyền của caller.

INVOKER phù hợp khi routine chỉ tổ chức lại SQL hoặc chuẩn hóa thao tác, nhưng chính sách phân quyền vẫn phải do quyền của người gọi quyết định.

### 3.3. Không nhầm DEFINER với SQL SECURITY

DEFINER chỉ ra tài khoản nào được gắn với đối tượng. SQL SECURITY cho biết có dùng quyền của tài khoản đó khi thực thi hay không.

Một routine có thể khai báo:

    CREATE DEFINER = 'admin'@'localhost'
    PROCEDURE app_db.read_sensitive_data()
    SQL SECURITY INVOKER
    BEGIN
        SELECT sensitive_value
        FROM app_db.sensitive_table;
    END;

Trong ví dụ này, DEFINER vẫn là admin@localhost, nhưng routine chạy bằng quyền của invoker vì SQL SECURITY INVOKER. Không được suy luận rằng chỉ cần thấy DEFINER là người gọi đã được dùng quyền của DEFINER.

## 4. USER() và CURRENT_USER() giúp quan sát security context

Hai hàm này phục vụ hai mục đích khác nhau:

- USER() trả về danh tính user/host được client dùng khi kết nối.
- CURRENT_USER() trả về MySQL account đang được dùng để kiểm tra quyền trong security context hiện tại.

Chạy trực tiếp trong session:

    SELECT
        USER() AS connection_identity,
        CURRENT_USER() AS privilege_identity;

Trong routine SQL SECURITY DEFINER, CURRENT_USER() trả về tài khoản DEFINER của routine. USER() vẫn phản ánh danh tính kết nối của client.

Ví dụ:

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.show_security_context()
    SQL SECURITY DEFINER
    BEGIN
        SELECT
            USER() AS connection_identity,
            CURRENT_USER() AS privilege_identity;
    END;

Khi một tài khoản ứng dụng gọi procedure, kết quả có thể cho thấy USER() là tài khoản ứng dụng còn CURRENT_USER() là tài khoản DEFINER.

Nếu đổi procedure sang SQL SECURITY INVOKER, CURRENT_USER() phản ánh security context của invoker.

Đây là phép kiểm tra hữu ích khi điều tra lỗi quyền. Không dùng USER() thay cho CURRENT_USER() để kết luận tài khoản nào đang được dùng khi MySQL kiểm tra quyền của statement bên trong routine.

## 5. Quyền khi tạo và gọi stored routine

Các quyền cơ bản liên quan đến stored procedure và stored function:

| Quyền | Mục đích |
|---|---|
| CREATE ROUTINE | Tạo stored procedure hoặc stored function |
| ALTER ROUTINE | Thay đổi hoặc xóa stored routine |
| EXECUTE | Gọi stored procedure hoặc stored function |
| SET_ANY_DEFINER / quyền tương ứng theo phiên bản | Chỉ định DEFINER khác tài khoản hiện tại |
| SHOW_ROUTINE | Xem định nghĩa routine theo phạm vi quyền được cấp, trên phiên bản hỗ trợ quyền này |

CREATE ROUTINE thường được cấp ở cấp schema. ALTER ROUTINE và EXECUTE có thể được cấp ở cấp routine cụ thể.

Ví dụ:

    GRANT CREATE ROUTINE
    ON app_db.*
    TO 'routine_deployer'@'localhost';

    GRANT EXECUTE
    ON PROCEDURE app_db.get_order_summary
    TO 'app_runtime'@'%';

Để thu hồi:

    REVOKE EXECUTE
    ON PROCEDURE app_db.get_order_summary
    FROM 'app_runtime'@'%';

Tên account và host phải khớp với tài khoản đã được tạo. Không cấp CREATE ROUTINE hoặc quyền đặt DEFINER cho tài khoản runtime của ứng dụng nếu ứng dụng chỉ cần gọi routine.

### 5.1. automatic_sp_privileges

MySQL có system variable automatic_sp_privileges. Khi bật (mặc định thường là 1), server tự cấp ALTER ROUTINE và EXECUTE cho tài khoản tạo routine nếu cần; các quyền tự cấp này được gỡ khi routine bị xóa.

Kiểm tra:

    SHOW VARIABLES LIKE 'automatic_sp_privileges';

Nếu biến này tắt, creator không tự động nhận các quyền đó. Tài khoản DEFINER của routine SQL SECURITY DEFINER cũng cần EXECUTE trên routine theo quy tắc kiểm tra quyền của MySQL. Khi creator và DEFINER khác nhau, đừng giả định quyền tự động cấp cho creator đã được cấp cho DEFINER.

Kiểm tra quyền:

    SHOW GRANTS FOR 'routine_deployer'@'localhost';
    SHOW GRANTS FOR 'app_runtime'@'%';

Đối với tài khoản DEFINER, kiểm tra riêng cả quyền trên bảng nguồn lẫn quyền EXECUTE trên routine.

### 5.2. Quyền của invoker và definer trong DEFINER routine

Với routine SQL SECURITY DEFINER:

- Invoker cần EXECUTE trên routine.
- DEFINER cần quyền thực hiện các statement trong routine.
- DEFINER cũng cần EXECUTE trên routine theo quy tắc kiểm tra của MySQL.
- Invoker không cần quyền trực tiếp trên bảng nguồn nếu quyền đó được cung cấp thông qua DEFINER routine.

Với routine SQL SECURITY INVOKER:

- Invoker cần EXECUTE trên routine.
- Invoker cần quyền trên các bảng, view hoặc đối tượng được truy cập trong routine.
- Quyền của DEFINER không thay thế quyền còn thiếu của invoker.

Quyền cần thiết cụ thể phụ thuộc statement và đường chạy trong routine. Ví dụ một nhánh IF có UPDATE chỉ cần quyền UPDATE khi nhánh đó thực sự được thực thi, nhưng thiết kế quyền phải bao phủ mọi đường chạy được phép.

## 6. Ví dụ hoàn chỉnh: đóng gói quyền đọc đơn hàng

Giả sử ứng dụng chỉ được phép gọi một procedure để đọc đơn của một khách hàng. Ứng dụng không được SELECT trực tiếp toàn bảng orders.

### 6.1. Tạo tài khoản DEFINER chuyên dụng

Thực hiện bằng tài khoản quản trị:

    CREATE USER 'orders_api_definer'@'localhost'
    IDENTIFIED BY 'replace-with-secret-from-secret-manager';

    GRANT CREATE ROUTINE
    ON app_db.*
    TO 'orders_api_definer'@'localhost';

    GRANT SELECT
    ON app_db.orders
    TO 'orders_api_definer'@'localhost';

Trong hệ thống thực tế, mật khẩu phải được quản lý bằng secret manager và không lưu trong repository hoặc log migration. Nếu quy trình triển khai có thể kết nối trực tiếp bằng account DEFINER, hãy bảo vệ thông tin xác thực và hạn chế đường đăng nhập.

### 6.2. Tạo procedure bằng chính tài khoản DEFINER

Kết nối bằng orders_api_definer@localhost rồi chạy:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.get_order_summary(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY DEFINER
    READS SQL DATA
    BEGIN
        IF p_customer_id IS NULL OR p_customer_id = 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'customer_id is required';
        END IF;

        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;
    END//

    DELIMITER ;

DEFINER được đặt là CURRENT_USER nên đối tượng gắn với account đang tạo routine. Phần thân chỉ đọc bảng orders. Tham số được dùng như một giá trị SQL, không được nối thành chuỗi SQL động.

### 6.3. Chỉ cấp EXECUTE cho ứng dụng

Chạy bằng tài khoản quản trị:

    GRANT EXECUTE
    ON PROCEDURE app_db.get_order_summary
    TO 'app_runtime'@'%';

Không cấp:

    -- Không cấp quyền đọc toàn bảng cho runtime nếu không cần:
    -- GRANT SELECT ON app_db.orders TO 'app_runtime'@'%';

Ứng dụng gọi:

    CALL app_db.get_order_summary(1001);

Kết quả được đọc bằng quyền của DEFINER. Tài khoản app_runtime chỉ có quyền gọi procedure theo grants đã cấp.

### 6.4. Kiểm tra hành vi quyền

Kết nối bằng app_runtime và thử:

    CALL app_db.get_order_summary(1001);

Nếu EXECUTE đã được cấp và DEFINER có đủ quyền, procedure có thể chạy.

Thử truy cập trực tiếp:

    SELECT *
    FROM app_db.orders;

Nếu app_runtime không có SELECT trên bảng, câu lệnh trực tiếp phải bị từ chối. Đây là cách kiểm chứng ranh giới quyền đã được thiết kế.

Lưu ý: ví dụ giả định account DEFINER đã có quyền EXECUTE trên procedure. Nếu automatic_sp_privileges tắt hoặc creator khác DEFINER, quản trị viên cần cấp quyền EXECUTE cho DEFINER theo chính sách của server.

## 7. Ví dụ SQL SECURITY INVOKER

Nếu muốn routine chỉ hoạt động khi người gọi có quyền đọc bảng, khai báo INVOKER:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    PROCEDURE app_db.list_orders_as_invoker(
        IN p_customer_id BIGINT UNSIGNED
    )
    SQL SECURITY INVOKER
    READS SQL DATA
    BEGIN
        SELECT
            order_id,
            order_date,
            total_amount
        FROM app_db.orders
        WHERE customer_id = p_customer_id;
    END//

    DELIMITER ;

Cấp EXECUTE cho ứng dụng:

    GRANT EXECUTE
    ON PROCEDURE app_db.list_orders_as_invoker
    TO 'app_runtime'@'%';

Nếu app_runtime chưa có SELECT trên app_db.orders, CALL sẽ thất bại ở statement SELECT bên trong. Sau khi cấp SELECT, routine mới có thể đọc bảng:

    GRANT SELECT
    ON app_db.orders
    TO 'app_runtime'@'%';

Đây là khác biệt cốt lõi giữa DEFINER và INVOKER. Đừng chọn INVOKER chỉ vì tên gọi có vẻ an toàn hơn; hãy chọn theo chính sách quyền mà ứng dụng cần thực thi.

## 8. SQL SECURITY và VIEW

View cũng có DEFINER và SQL SECURITY. Mặc định view dùng SQL SECURITY DEFINER.

Ví dụ view DEFINER:

    CREATE DEFINER = CURRENT_USER
    SQL SECURITY DEFINER
    VIEW app_db.v_public_order_summary AS
    SELECT
        order_id,
        customer_id,
        order_date,
        total_amount
    FROM app_db.orders
    WHERE order_status = 'PAID';

Người dùng tham chiếu view cần quyền SELECT trên view. Quyền truy cập bảng nguồn được kiểm tra theo DEFINER của view. Điều này cho phép cung cấp một tập cột/hàng được giới hạn mà không cấp quyền SELECT trực tiếp trên bảng gốc.

View INVOKER:

    CREATE DEFINER = CURRENT_USER
    SQL SECURITY INVOKER
    VIEW app_db.v_order_rows_invoker AS
    SELECT
        order_id,
        customer_id,
        order_date,
        total_amount
    FROM app_db.orders;

Với view INVOKER, tài khoản tham chiếu view phải có quyền thích hợp trên các đối tượng nền. Quyền SELECT trên view không tự thay thế quyền SELECT trên bảng nguồn trong security context INVOKER.

### 8.1. View gọi stored function

Một view có thể gọi stored function. Khi đó security context có thể chuyển tiếp qua các đối tượng:

- View SQL SECURITY DEFINER dùng quyền của view DEFINER khi truy cập các bảng nền.
- Nếu view gọi function SQL SECURITY DEFINER, function dùng quyền của function DEFINER.
- Nếu view gọi function SQL SECURITY INVOKER, function dùng quyền được xác định bởi SQL SECURITY context của view. Với view DEFINER, function INVOKER chạy theo quyền của view DEFINER; với view INVOKER, function dùng quyền của người tham chiếu view.

Vì vậy, không giả định rằng người dùng cuối luôn là context của mọi function được gọi gián tiếp. Khi ghép view và routine, hãy kiểm tra định nghĩa từng đối tượng và thử bằng tài khoản có quyền hạn thực tế.

## 9. Trigger luôn chạy trong DEFINER context

Trigger không có mệnh đề SQL SECURITY DEFINER hoặc INVOKER. Trigger luôn chạy bằng quyền của tài khoản DEFINER.

Ví dụ:

    DELIMITER //

    CREATE DEFINER = CURRENT_USER
    TRIGGER app_db.orders_before_insert
    BEFORE INSERT ON app_db.orders
    FOR EACH ROW
    BEGIN
        IF NEW.total_amount < 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'total_amount cannot be negative';
        END IF;
    END//

    DELIMITER ;

Người dùng thực hiện INSERT trên bảng sẽ kích hoạt trigger tự động. Trigger không yêu cầu người dùng gọi một routine bằng EXECUTE. Vì vậy, quyền hạn của DEFINER trigger đặc biệt quan trọng: người dùng có thể kích hoạt trigger thông qua thao tác trên bảng dù không trực tiếp tham chiếu trigger.

Tài khoản DEFINER cần có các quyền mà phần thân trigger sử dụng. Nếu trigger ghi audit table, DEFINER cần quyền INSERT trên audit table. Người dùng gọi INSERT vào orders không nhất thiết phải có INSERT trực tiếp vào audit table nếu trigger thực hiện thao tác đó trong DEFINER context.

Khi tạo trigger, tài khoản thực hiện CREATE cần quyền TRIGGER trên bảng liên quan. Cần quản lý riêng quyền tạo trigger và quyền thực thi trigger.

Không tạo trigger với DEFINER là tài khoản quá mạnh. Một trigger bị lạm dụng có thể biến quyền INSERT/UPDATE trên một bảng thành khả năng thực hiện thêm các thao tác nhạy cảm.

## 10. Event luôn chạy trong DEFINER context

Event Scheduler chạy event theo lịch. Event không có SQL SECURITY INVOKER; phần thân event luôn dùng security context của DEFINER.

Ví dụ:

    CREATE DEFINER = CURRENT_USER
    EVENT app_db.expire_old_sessions
    ON SCHEDULE EVERY 1 DAY
    DO
        DELETE FROM app_db.user_session
        WHERE expires_at < CURRENT_TIMESTAMP;

Tài khoản DEFINER cần quyền DELETE trên bảng user_session. Người dùng ứng dụng không gọi event trực tiếp; server tự chạy event khi Event Scheduler hoạt động.

Kiểm tra:

    SHOW VARIABLES LIKE 'event_scheduler';

Event Scheduler phải được bật để event chạy theo lịch. Tài khoản tạo event cần quyền EVENT phù hợp trên schema. Tài khoản DEFINER phải có quyền cho các thao tác trong event body.

Do event chạy tự động, không có quyền EXECUTE của invoker làm hàng rào như procedure. Hãy giới hạn quyền tạo/sửa event và kiểm tra định kỳ DEFINER của event.

## 11. So sánh security context của các loại đối tượng

| Đối tượng | Có SQL SECURITY? | Mặc định/hành vi | Quyền người tham chiếu |
|---|---|---|---|
| Procedure | Có | Mặc định DEFINER | Cần EXECUTE; quyền trong body theo DEFINER hoặc INVOKER |
| Function | Có | Mặc định DEFINER | Cần quyền gọi function; quyền trong body theo DEFINER hoặc INVOKER |
| View | Có | Mặc định DEFINER | Cần quyền trên view; quyền bảng nền theo DEFINER hoặc INVOKER |
| Trigger | Không | Luôn DEFINER | Được kích hoạt qua thao tác trên bảng; body chạy theo DEFINER |
| Event | Không | Luôn DEFINER | Server chạy theo lịch; body chạy theo DEFINER |

Chỉ procedure, function và view cho phép chọn SQL SECURITY INVOKER. Không cố thêm mệnh đề SQL SECURITY vào CREATE TRIGGER hoặc CREATE EVENT.

## 12. DEFINER account phải có quyền gì?

Tài khoản DEFINER cần đúng quyền cho các statement có thể thực thi trong object:

| Statement trong object | Quyền cần xem xét |
|---|---|
| SELECT từ bảng | SELECT trên bảng hoặc cột phù hợp |
| INSERT vào bảng | INSERT |
| UPDATE cột | UPDATE trên bảng/cột phù hợp |
| DELETE hàng | DELETE |
| Gọi procedure/function khác | EXECUTE trên routine được gọi |
| Tạo hoặc thay đổi đối tượng | Quyền DDL tương ứng nếu body/logic được phép thực hiện |
| Đọc view | SELECT trên view và quyền cần thiết theo security context của view |

Không cấp ALL PRIVILEGES chỉ để routine chạy. Đọc body và liệt kê các thao tác thực tế, sau đó cấp quyền tối thiểu.

Nếu routine có nhiều nhánh, hãy đánh giá tất cả nhánh có thể chạy. Một nhánh hiếm dùng UPDATE hoặc DELETE vẫn cần quyền tương ứng khi nhánh đó được thực thi.

### 12.1. Quyền trên routine được gọi lồng nhau

Một procedure có thể gọi procedure khác. Mỗi routine có security context riêng theo SQL SECURITY của chính nó. Vì vậy, hãy kiểm tra chuỗi gọi:

    app_runtime
       |
       v
    app_db.api_procedure
       |
       v
    app_db.internal_procedure
       |
       v
    app_db.orders

Nếu api_procedure là DEFINER nhưng gọi internal_procedure là INVOKER, routine thứ hai sử dụng context của invoker đối với lần gọi đó. Nếu internal_procedure là DEFINER, nó chuyển sang quyền của DEFINER riêng. Chuỗi chuyển context phải được hiểu theo từng đối tượng, không suy từ routine ngoài cùng.

Khi điều tra lỗi quyền, dùng SHOW CREATE cho toàn bộ routine/view liên quan và thử bằng account runtime thực tế.

## 13. Roles và quyền hiệu lực của DEFINER

MySQL hỗ trợ roles để nhóm quyền. Tuy nhiên, không nên giả định mọi role được GRANT cho DEFINER đều tự động có hiệu lực trong stored routine DEFINER.

Đối với stored routine SQL SECURITY DEFINER, mặc định MySQL kích hoạt các default roles của tài khoản DEFINER; các role không phải default không tự động có hiệu lực. Nếu activate_all_roles_on_login được bật, server có thể kích hoạt tất cả role được cấp theo quy tắc của biến này. Stored program cũng có thể thực hiện SET ROLE để kích hoạt role cần thiết, nhưng phải kiểm soát cẩn thận vì quyền của role có thể thay đổi sau khi routine được triển khai.

Kiểm tra:

    SHOW VARIABLES LIKE 'activate_all_roles_on_login';

    SHOW GRANTS FOR 'orders_api_definer'@'localhost';

Để security context dễ dự đoán, có thể cấp trực tiếp các quyền tối thiểu cần thiết cho account DEFINER thay vì phụ thuộc vào một tập role thay đổi theo session. Nếu dùng roles, hãy kiểm tra default role, active role và hành vi trong đúng phiên bản MySQL.

Không dùng role quản trị rộng làm quyền nền cho DEFINER routine. Quyền hiệu lực của routine cần ổn định và có thể kiểm toán.

## 14. Quyền đặt DEFINER khác tài khoản hiện tại

Thông thường, khi tạo stored object, tài khoản tạo có thể đặt DEFINER là chính mình hoặc CURRENT_USER. Để đặt một account khác, cần quyền quản trị tương ứng theo phiên bản MySQL.

| Phiên bản/quy tắc | Quyền cần chú ý |
|---|---|
| Các bản MySQL 8.0 trước thay đổi privilege model | SET_USER_ID hoặc quyền SUPER theo quy tắc của bản phát hành |
| MySQL 8.4 | SET_ANY_DEFINER để chỉ định account khác; ALLOW_NONEXISTENT_DEFINER dùng để vượt một số bảo vệ orphan object |

SET_USER_ID đã bị deprecated trong nhánh MySQL mới và bị loại bỏ ở MySQL 8.4. Hãy kiểm tra tài liệu đúng phiên bản trước khi viết migration hoặc GRANT.

SET_ANY_DEFINER là quyền nhạy cảm vì người có quyền này có thể tạo đối tượng chạy với quyền của account khác. Không cấp cho tài khoản ứng dụng hoặc tài khoản triển khai thông thường nếu không có quy trình kiểm soát.

Nếu target DEFINER có quyền SYSTEM_USER, người tạo object còn cần quyền SYSTEM_USER theo quy tắc bảo vệ account hệ thống của MySQL.

ALLOW_NONEXISTENT_DEFINER cho phép vượt các kiểm tra bảo vệ orphan object trong những trường hợp đặc biệt. Trên MySQL 8.4, việc chủ động tạo stored object mới với DEFINER không tồn tại cần cả SET_ANY_DEFINER và ALLOW_NONEXISTENT_DEFINER. Không cấp các quyền này chỉ để làm migration hết lỗi; hãy tạo account DEFINER trước và triển khai object sau.

### 14.1. Triển khai dưới account DEFINER hay chỉ định từ deployment account?

Hai cách phổ biến:

**Cách A: tạo object khi đăng nhập bằng account DEFINER**

- Account DEFINER có CREATE ROUTINE và quyền dữ liệu cần thiết.
- CREATE không cần chỉ định một user khác làm DEFINER; dùng CURRENT_USER.
- Sau khi tạo, cấp EXECUTE cho account runtime.

**Cách B: deployment account chỉ định DEFINER riêng**

- Deployment account cần quyền đặt DEFINER khác account hiện tại.
- DEFINER account phải tồn tại trên server đích.
- Quyền của DEFINER phải được cấp trước hoặc được quản lý trong migration có thứ tự rõ ràng.
- Kiểm tra DEFINER sau khi deploy.

Cách A thường giảm nhu cầu cấp quyền SET_ANY_DEFINER cho pipeline. Cách B thuận tiện cho migration tập trung nhưng cần bảo vệ quyền đặt DEFINER rất chặt.

## 15. Orphan stored object là gì?

Orphan stored object là đối tượng có DEFINER trỏ đến một account không còn tồn tại. Tình huống này có thể xảy ra khi:

- Account DEFINER bị xóa.
- Account DEFINER bị đổi tên.
- Dump/restore object sang môi trường chưa tạo account DEFINER.
- Migration tạo object tham chiếu đến account chưa được provision.
- Một thao tác quản trị bỏ qua bảo vệ orphan object.

Hậu quả phụ thuộc loại object và security context:

- Routine SQL SECURITY DEFINER có thể lỗi khi thực thi vì account DEFINER không tồn tại.
- View SQL SECURITY DEFINER có thể lỗi khi được tham chiếu.
- Event có thể lỗi khi đến lịch chạy.
- Trigger có DEFINER không tồn tại có thể có hành vi không xác định theo quy tắc kiểm tra quyền; không để trigger chạy trong tình trạng này.
- Routine/view SQL SECURITY INVOKER vẫn cần được kiểm tra metadata và quy trình quản trị, dù quyền thực thi được xác định theo invoker.

Không tạo orphan object có chủ đích. Việc một account sau này được tạo lại với cùng tên/host có thể khiến object cũ bất ngờ gắn với account mới, tạo rủi ro bảo mật.

### 15.1. Kiểm tra DEFINER của routine

    SELECT
        ROUTINE_SCHEMA,
        ROUTINE_NAME,
        ROUTINE_TYPE,
        DEFINER,
        SECURITY_TYPE
    FROM information_schema.ROUTINES
    WHERE ROUTINE_SCHEMA = 'app_db'
    ORDER BY ROUTINE_TYPE, ROUTINE_NAME;

### 15.2. Kiểm tra DEFINER của view

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        DEFINER,
        SECURITY_TYPE
    FROM information_schema.VIEWS
    WHERE TABLE_SCHEMA = 'app_db'
    ORDER BY TABLE_NAME;

### 15.3. Kiểm tra DEFINER của trigger

    SELECT
        TRIGGER_SCHEMA,
        TRIGGER_NAME,
        EVENT_OBJECT_TABLE,
        DEFINER
    FROM information_schema.TRIGGERS
    WHERE TRIGGER_SCHEMA = 'app_db'
    ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;

### 15.4. Kiểm tra DEFINER của event

    SELECT
        EVENT_SCHEMA,
        EVENT_NAME,
        DEFINER,
        STATUS
    FROM information_schema.EVENTS
    WHERE EVENT_SCHEMA = 'app_db'
    ORDER BY EVENT_NAME;

Các truy vấn trên cần quyền metadata phù hợp. Không phải tài khoản nào cũng nhìn thấy toàn bộ định nghĩa routine hoặc đối tượng của schema khác.

## 16. Không xóa hoặc đổi tên DEFINER tùy tiện

Trước khi chạy DROP USER hoặc RENAME USER, hãy tìm các stored object đang tham chiếu account đó. Nếu có, cần lập kế hoạch thay DEFINER hoặc xóa/recreate object theo đúng quy trình.

Trong MySQL 8.4, server có các kiểm tra bảo vệ orphan object. DROP USER hoặc RENAME USER có thể bị từ chối nếu account đang được dùng làm DEFINER. CREATE USER cũng có thể bị từ chối nếu account mới sẽ nhận các orphan object hiện có. Các quyền quản trị đặc biệt như ALLOW_NONEXISTENT_DEFINER có thể vượt một số kiểm tra này; không dùng chúng như giải pháp thường ngày.

Ví dụ tìm object đang dùng account:

    SELECT
        ROUTINE_SCHEMA,
        ROUTINE_NAME,
        ROUTINE_TYPE
    FROM information_schema.ROUTINES
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME
    FROM information_schema.VIEWS
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        TRIGGER_SCHEMA,
        TRIGGER_NAME
    FROM information_schema.TRIGGERS
    WHERE DEFINER = 'orders_api_definer@localhost';

    SELECT
        EVENT_SCHEMA,
        EVENT_NAME
    FROM information_schema.EVENTS
    WHERE DEFINER = 'orders_api_definer@localhost';

Nếu cần thay DEFINER của procedure hoặc function, thông thường phải drop và tạo lại routine với DEFINER mới. Với view hoặc event, có thể dùng ALTER VIEW hoặc ALTER EVENT theo cú pháp hỗ trợ. Với trigger, cần drop và tạo lại trigger. Trước khi thay đổi, lưu định nghĩa đầy đủ bằng SHOW CREATE.

## 17. Kiểm tra định nghĩa và quyền của object

Các lệnh hữu ích:

    SHOW CREATE PROCEDURE app_db.get_order_summary;

    SHOW CREATE FUNCTION app_db.calculate_tax;

    SHOW CREATE VIEW app_db.v_public_order_summary;

    SHOW TRIGGERS FROM app_db;

    SHOW EVENTS FROM app_db;

Kiểm tra quyền của account:

    SHOW GRANTS FOR 'orders_api_definer'@'localhost';
    SHOW GRANTS FOR 'app_runtime'@'%';

Kiểm tra định nghĩa trong INFORMATION_SCHEMA:

    SELECT
        ROUTINE_NAME,
        ROUTINE_TYPE,
        DEFINER,
        SECURITY_TYPE,
        SQL_DATA_ACCESS
    FROM information_schema.ROUTINES
    WHERE ROUTINE_SCHEMA = 'app_db';

SHOW CREATE là nguồn tốt để lưu lại DDL đầy đủ của object trước migration. INFORMATION_SCHEMA hữu ích để kiểm kê hàng loạt và phát hiện account DEFINER bất thường.

## 18. Rủi ro bảo mật của SQL SECURITY DEFINER

DEFINER là một cơ chế mạnh. Nó cho phép người dùng có ít quyền hơn kích hoạt một thao tác chạy bằng quyền của account khác. Nếu routine được thiết kế sai, đây có thể trở thành đường nâng quyền.

Các rủi ro thường gặp:

- Dùng root hoặc DBA làm DEFINER.
- Cấp EXECUTE cho quá nhiều tài khoản.
- Procedure nhận customer_id tùy ý và trả dữ liệu của mọi khách hàng.
- Procedure nhận tên bảng/cột/sort expression rồi ghép trực tiếp vào SQL động.
- Trigger có quyền ghi/xóa dữ liệu nhạy cảm mà người gọi có thể kích hoạt gián tiếp.
- Event có quyền quản trị quá rộng và chạy theo lịch.
- Account DEFINER bị xóa, đổi tên hoặc thay đổi grants mà không rà soát object.
- Pipeline deploy tạo object bằng account có quyền cao ngoài ý muốn.

### 18.1. Nguyên tắc least privilege

- Tạo một account DEFINER riêng cho từng nhóm trách nhiệm hoặc nhóm object có quyền tương tự.
- Chỉ cấp quyền trên schema, bảng hoặc cột thực sự cần.
- Không dùng root, SUPER hoặc quyền quản trị toàn cục làm quyền thực thi routine.
- Chỉ cấp EXECUTE cho role/user cần gọi.
- Không cấp CREATE ROUTINE, TRIGGER hoặc EVENT cho account runtime nếu không cần.
- Rà soát grants định kỳ và sau mỗi thay đổi nghiệp vụ.
- Theo dõi các object có DEFINER khác tài khoản triển khai.

### 18.2. Kiểm tra đầu vào và SQL động

SQL SECURITY DEFINER không tự động bảo vệ routine khỏi SQL injection. Nếu procedure tạo SQL động bằng CONCAT, dữ liệu không tin cậy có thể biến thành cú pháp SQL.

Không làm:

    -- Ví dụ nguy hiểm, không dùng:
    -- SET @sql_text = CONCAT(
    --     'SELECT * FROM app_db.orders ORDER BY ',
    --     p_sort_column
    -- );

Tham số giá trị nên được truyền qua parameter marker của prepared statement khi dùng SQL động. Identifier như tên bảng, tên cột hoặc hướng sort không thể bind như giá trị thông thường; hãy ánh xạ chúng qua whitelist cố định trước khi đưa vào SQL.

Ví dụ logic whitelist:

    BEGIN
        DECLARE v_order_expression VARCHAR(64);

        IF p_sort_mode = 'newest' THEN
            SET v_order_expression = 'order_date DESC';
        ELSEIF p_sort_mode = 'largest' THEN
            SET v_order_expression = 'total_amount DESC';
        ELSE
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Unsupported sort mode';
        END IF;
    END;

Chỉ các chuỗi cố định do chương trình định nghĩa mới được đưa vào phần identifier/expression của SQL động. Không nối trực tiếp input người dùng.

### 18.3. Giới hạn dữ liệu trả về

Một procedure DEFINER đọc bảng rộng có thể vô tình làm lộ dữ liệu. Hãy:

- Giới hạn cột được SELECT.
- Áp dụng tenant/customer ownership check phù hợp.
- Kiểm tra quyền truy cập của chủ thể theo nghiệp vụ, không chỉ kiểm tra tham số có hợp lệ về kiểu.
- Giới hạn số hàng và khoảng thời gian.
- Tránh trả thông tin bí mật không cần thiết.
- Ghi audit cho các thao tác nhạy cảm nếu yêu cầu hệ thống cần theo dõi.

Không coi việc caller không có SELECT trên bảng là đủ để bảo vệ dữ liệu nếu caller có EXECUTE trên procedure trả toàn bộ dữ liệu đó.

## 19. Quy trình triển khai stored object an toàn

Một migration triển khai routine/view/trigger/event nên có thứ tự rõ ràng:

1. Tạo account DEFINER trên môi trường đích.
2. Cấp các quyền tối thiểu cho DEFINER.
3. Kiểm tra account và grants bằng SHOW GRANTS.
4. Tạo object với DEFINER tường minh hoặc chạy CREATE dưới chính account DEFINER.
5. Chọn SQL SECURITY phù hợp với mô hình quyền.
6. Cấp EXECUTE hoặc quyền tham chiếu object cho role/user runtime.
7. Kiểm tra SHOW CREATE để xác nhận DEFINER và SQL SECURITY.
8. Kiểm thử bằng account runtime có đúng quyền production.
9. Kiểm thử trường hợp quyền bị thiếu để bảo đảm fail đúng cách.
10. Kiểm tra event scheduler hoặc trigger path nếu object được tự động kích hoạt.
11. Ghi nhận object nào phụ thuộc account DEFINER để tránh xóa/đổi tên nhầm.

### 19.1. Khi restore hoặc triển khai sang môi trường mới

Dump của database có thể chứa DEFINER trong DDL. Nếu restore object trước khi tạo account DEFINER, quá trình import có thể lỗi hoặc tạo orphan tùy phiên bản và quyền thực hiện.

Thứ tự nên là:

- Provision account và quyền.
- Restore/create stored objects.
- Cấp quyền runtime.
- Kiểm tra DEFINER và security type.
- Chạy smoke test bằng tài khoản ứng dụng.

Không thay toàn bộ DEFINER bằng root trong dump chỉ để import thành công. Hãy ánh xạ sang account chuyên dụng của môi trường đích và giữ nguyên nguyên tắc least privilege.

## 20. Các lỗi thường gặp

- Nghĩ DEFINER là tài khoản tạo object trong mọi trường hợp.
- Nghĩ DEFINER tự động có tất cả quyền cần thiết.
- Nghĩ SQL SECURITY INVOKER vẫn sử dụng quyền của DEFINER khi đọc bảng.
- Nghĩ bỏ SQL SECURITY sẽ mặc định INVOKER.
- Thêm SQL SECURITY vào trigger hoặc event dù hai loại này luôn chạy bằng DEFINER.
- Cấp SELECT trên bảng cho app runtime dù chỉ cần EXECUTE trên procedure DEFINER.
- Quên DEFINER cũng cần quyền EXECUTE trên routine theo quy tắc của MySQL.
- Quên automatic_sp_privileges có thể bị tắt.
- Nhầm USER() với CURRENT_USER() khi điều tra security context.
- Dùng account root làm DEFINER.
- Cấp SET_ANY_DEFINER hoặc quyền tương đương cho tài khoản ứng dụng.
- Dùng ALLOW_NONEXISTENT_DEFINER để bỏ qua lỗi account chưa tồn tại.
- Dùng role mà không kiểm tra default/active roles của DEFINER.
- Xóa hoặc đổi tên account đang được routine, view, trigger hoặc event tham chiếu.
- Restore stored object trước khi provision account DEFINER.
- Ghép input người dùng trực tiếp vào SQL động trong DEFINER routine.
- Nghĩ SQL SECURITY DEFINER tự động giới hạn dữ liệu theo người gọi.
- Chỉ thử routine bằng tài khoản admin thay vì account runtime thật.

## 21. Checklist bảo mật trước khi triển khai

- Đã xác định creator, DEFINER và invoker.
- Đã chọn DEFINER hoặc INVOKER theo chính sách quyền.
- Đã hiểu default SQL SECURITY của loại object.
- Đã xác định trigger/event luôn dùng DEFINER context.
- Đã tạo account DEFINER tồn tại trên mọi môi trường.
- Đã tránh dùng root hoặc account quản trị rộng làm DEFINER.
- Đã cấp quyền tối thiểu cho DEFINER.
- Đã cấp EXECUTE hoặc quyền tham chiếu object tối thiểu cho caller.
- Đã kiểm tra quyền EXECUTE của DEFINER khi cần.
- Đã kiểm tra automatic_sp_privileges và quyền được tự động cấp.
- Đã kiểm tra role hiệu lực của DEFINER.
- Đã xác minh quyền đặt DEFINER theo đúng phiên bản MySQL.
- Đã kiểm tra USER() và CURRENT_USER() trong môi trường thử nghiệm.
- Đã kiểm tra SQL động, whitelist identifier và bind value.
- Đã giới hạn dữ liệu trả về theo tenant/ownership nghiệp vụ.
- Đã kiểm tra DEFINER của routines, views, triggers và events.
- Đã có quy trình đổi DEFINER trước khi xóa hoặc đổi tên account.
- Đã kiểm thử bằng account runtime thật, không chỉ tài khoản quản trị.
- Đã kiểm tra DDL sau restore/deploy và lưu SHOW CREATE.

## 22. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Stored Object Access Control: https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html
- MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 Reference Manual — Stored Routines and MySQL Privileges: https://dev.mysql.com/doc/refman/8.4/en/stored-routines-privileges.html
- MySQL 8.4 Reference Manual — CREATE VIEW: https://dev.mysql.com/doc/refman/8.4/en/create-view.html
- MySQL 8.4 Reference Manual — Privileges Provided by MySQL: https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html

DEFINER xác định account gắn với stored object; SQL SECURITY quyết định quyền của DEFINER hay invoker được dùng khi routine hoặc view thực thi. Procedure, function và view mặc định dùng DEFINER nhưng có thể chọn INVOKER; trigger và event luôn chạy bằng quyền của DEFINER. Thiết kế an toàn cần account DEFINER chuyên dụng, quyền tối thiểu, quyền EXECUTE được cấp đúng đối tượng, kiểm tra security context bằng CURRENT_USER(), quản lý role và tránh orphan object. Đừng xem DEFINER như một cách bỏ qua phân quyền: đây là một ranh giới quyền lực cần được thiết kế, triển khai, kiểm thử và kiểm toán cẩn thận.
