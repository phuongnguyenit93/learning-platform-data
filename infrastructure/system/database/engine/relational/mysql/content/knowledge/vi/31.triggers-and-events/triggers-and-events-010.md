# DEFINER, quyền thực thi và trạng thái event

Trigger và Event là hai cơ chế tự động hóa trong MySQL. Trigger chạy khi một thao tác INSERT, UPDATE hoặc DELETE tác động lên bảng; Event được Event Scheduler chạy theo lịch. Cả hai có thể thực hiện SQL mà người dùng gọi trực tiếp không cần gửi từng câu lệnh riêng.

Vì chúng chạy tự động, câu hỏi bảo mật quan trọng là: **SQL bên trong được thực thi với quyền của ai?** MySQL lưu tài khoản DEFINER cho trigger và event. Khi trigger được kích hoạt hoặc event đến lịch chạy, phần thân của đối tượng được thực thi trong security context của definer. Quyền của người gọi thao tác UPDATE hoặc người quản trị đang xem event không tự động thay thế quyền của definer.

Ngoài quyền của definer, Event còn phụ thuộc trạng thái riêng của từng event và biến hệ thống event_scheduler. Event có thể được đánh dấu ENABLE nhưng không chạy vì scheduler đang OFF; scheduler có thể ON nhưng event vẫn DISABLED. Cần kiểm tra cả hai lớp trạng thái.

Bài học này thuộc chương **Trigger và event** của module DATABASE_MYSQL. Nội dung tập trung vào DEFINER, quyền tạo và quyền chạy, vòng đời tài khoản definer, trạng thái event, Event Scheduler, metadata và các tình huống vận hành thường gặp.

## 1. DEFINER là gì?

DEFINER là tài khoản MySQL được gắn với một đối tượng stored object. Với trigger và event, definer xác định security context dùng để thực thi phần thân đối tượng.

Một tài khoản MySQL có cả user và host:

~~~sql
'app_trigger'@'localhost'
'app_trigger'@'%'
~~~

Hai account trên là hai principal khác nhau. Quyền cấp cho app_trigger@localhost không tự động áp dụng cho app_trigger@%. Khi khai báo DEFINER, cần ghi đúng cả user lẫn host.

Nếu không chỉ định DEFINER khi tạo đối tượng, MySQL mặc định dùng tài khoản hiện tại tại thời điểm tạo. Có thể kiểm tra tài khoản hiện tại bằng:

~~~sql
SELECT CURRENT_USER(), USER();
~~~

Trong stored object chạy với security context của definer, CURRENT_USER() phản ánh tài khoản dùng để kiểm tra quyền cho đối tượng. USER() phản ánh danh tính kết nối theo ngữ cảnh session. Không dùng hai hàm này thay thế cho việc kiểm tra metadata DEFINER.

### DEFINER không phải người gọi

Ví dụ:

1. Tài khoản app_writer có quyền UPDATE trên bảng orders.
2. Trigger AFTER UPDATE trên orders được tạo với DEFINER là audit_trigger.
3. Khi app_writer cập nhật một hàng, trigger chạy.
4. Các câu SQL trong trigger được kiểm tra theo quyền của audit_trigger.

Do đó, app_writer không nhất thiết phải có quyền INSERT trên bảng audit_log nếu trigger definer đã có quyền INSERT cần thiết. Đây là một cách đóng gói quyền, nhưng cũng làm cho definer trở thành ranh giới bảo mật quan trọng.

## 2. Trigger và Event dùng security context nào?

Trigger và Event đều gắn với DEFINER, nhưng cú pháp và cách vận hành khác nhau.

| Đối tượng | Security context khi chạy | Có lựa chọn SQL SECURITY INVOKER không? |
|---|---|---|
| Trigger | Quyền của DEFINER đã lưu trong metadata trigger. | Không. Trigger không có tùy chọn SQL SECURITY INVOKER. |
| Event | Quyền của DEFINER đã lưu trong metadata event. | Không. Event không có tùy chọn SQL SECURITY INVOKER. |
| Stored procedure | Phụ thuộc SQL SECURITY DEFINER hoặc INVOKER được khai báo. | Có. |
| Stored function | Phụ thuộc SQL SECURITY DEFINER hoặc INVOKER được khai báo. | Có. |

Không viết SQL SECURITY INVOKER trong định nghĩa trigger hoặc event. Nếu cần routine được gọi từ trigger/event, routine đó có thể có security characteristic riêng; phải đánh giá chuỗi security context của toàn bộ lời gọi.

### Trigger không chạy bằng quyền của user UPDATE

Người gọi cần quyền thực hiện thao tác gốc trên bảng. Khi thao tác kích hoạt trigger, MySQL thực thi trigger theo definer. Vì vậy cần kiểm tra hai phần:

- Quyền của caller đối với INSERT/UPDATE/DELETE trên bảng được ứng dụng thao tác.
- Quyền của trigger definer đối với các bảng, view hoặc routine mà trigger body sử dụng.

### Event không chạy bằng quyền của người quản trị bật scheduler

Event Scheduler là thành phần nội bộ của server. Khi đến thời điểm, scheduler chạy event theo definer được lưu trong event metadata. Account bật event_scheduler hoặc người dùng xem SHOW EVENTS không tự động trở thành người thực thi phần body.

## 3. Quyền tại thời điểm tạo và thời điểm thực thi

Không nên gom tất cả quyền thành một yêu cầu duy nhất. Có ít nhất hai thời điểm cần phân biệt:

1. **Tạo hoặc thay đổi đối tượng:** tài khoản triển khai cần quyền TRIGGER trên bảng khi tạo trigger, quyền EVENT trên schema khi tạo event, và quyền đặc biệt nếu đặt một DEFINER khác tài khoản hiện tại.
2. **Kích hoạt đối tượng:** definer cần quyền đối với các thao tác mà body thực hiện. Nếu quyền bị thu hồi hoặc account không còn hợp lệ, đối tượng có thể lỗi khi chạy.

### Quyền thường cần cho trigger

- Tài khoản tạo trigger cần quyền TRIGGER trên bảng gắn trigger.
- Nếu tạo trigger với DEFINER khác CURRENT_USER, tài khoản triển khai cần dynamic privilege phù hợp để chỉ định definer khác; tên privilege thay đổi theo phiên bản MySQL.
- Trigger definer cần các quyền dữ liệu mà trigger body sử dụng, ví dụ SELECT, INSERT hoặc UPDATE trên các bảng liên quan.

### Quyền thường cần cho event

- Tài khoản tạo event cần quyền EVENT trên schema chứa event.
- Nếu chỉ định DEFINER khác CURRENT_USER, tài khoản triển khai cần quyền đặc biệt để chỉ định definer khác theo phiên bản MySQL.
- Event definer cần các quyền dữ liệu cần thiết để chạy event body, ví dụ SELECT, UPDATE hoặc DELETE trên bảng được xử lý.
- Việc bật/tắt scheduler là thao tác quản trị server và cần quyền quản trị biến hệ thống tương ứng.

### Tài khoản tạo không nhất thiết là tài khoản chạy

Một tài khoản deployment có thể tạo đối tượng và gắn definer service account. Sau khi triển khai, service account sở hữu security context lúc chạy. Tài khoản deployment không cần được dùng làm tài khoản ứng dụng hoặc tài khoản scheduler.

Đây là lý do nên tách:

- Account deployment: tạo/sửa đối tượng trong release.
- Definer account: có quyền tối thiểu để body chạy.
- Application account: chỉ có quyền gọi hoặc thao tác nghiệp vụ cần thiết.
- Operator account: theo dõi trạng thái, bật/tắt scheduler hoặc xử lý sự cố theo phân quyền vận hành.

## 4. Tạo definer account theo nguyên tắc quyền tối thiểu

Không nên dùng root hoặc tài khoản DBA toàn quyền làm definer cho mọi trigger/event. Nếu một đối tượng bị khai thác hoặc định nghĩa sai, quyền quá rộng có thể làm tăng phạm vi ảnh hưởng.

Ví dụ tạo service account dành riêng cho trigger:

~~~sql
CREATE USER 'orders_trigger'@'localhost'
IDENTIFIED BY '<managed-secret>';
~~~

Giả sử trigger cập nhật bảng audit khi trạng thái đơn hàng đổi. Cấp đúng các quyền cần thiết:

~~~sql
GRANT TRIGGER ON shop.orders
TO 'orders_trigger'@'localhost';

GRANT INSERT ON shop.order_audit
TO 'orders_trigger'@'localhost';
~~~

Trigger definer cần quyền TRIGGER trên bảng gắn trigger và quyền thao tác trên các bảng mà body truy cập. OLD và NEW là các giá trị hàng do trigger context cung cấp; không tạo một câu SELECT riêng trên bảng nguồn. Chỉ cấp thêm SELECT nếu body thực sự chạy truy vấn đọc bảng đó.

Tài khoản triển khai cần quyền TRIGGER trên bảng:

~~~sql
GRANT TRIGGER ON shop.orders
TO 'schema_deployer'@'localhost';
~~~

Nếu deployment chỉ định một definer khác tài khoản hiện tại, cần dynamic privilege đặc biệt. Ở một số bản MySQL 8.0, privilege liên quan là SET_USER_ID; các bản mới có thay đổi/deprecation và có thể dùng SET_ANY_DEFINER. Hãy kiểm tra tên privilege đúng với phiên bản server và chỉ cấp cho tài khoản triển khai được kiểm soát.

Không cấp quyền đặc biệt đặt definer cho tài khoản ứng dụng thông thường.

## 5. Tạo trigger với DEFINER

Giả sử có bảng đơn hàng và bảng audit:

~~~sql
CREATE TABLE shop.orders (
    order_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    updated_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE shop.order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE=InnoDB;
~~~

Tạo trigger:

~~~sql
DELIMITER //

CREATE DEFINER = 'orders_trigger'@'localhost'
TRIGGER shop.trg_orders_status_audit
AFTER UPDATE ON shop.orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO shop.order_audit (
            order_id,
            old_status,
            new_status
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status
        );
    END IF;
END//

DELIMITER ;
~~~

Trigger chỉ ghi audit khi status thực sự thay đổi. Toán tử null-safe equality <=> giúp so sánh an toàn cả khi một trong hai phía có thể là NULL; trong schema ví dụ status NOT NULL nên phép so sánh vẫn rõ ràng.

### Khi trigger được kích hoạt

~~~sql
UPDATE shop.orders
SET status = 'PAID'
WHERE order_id = 1001;
~~~

Nếu thao tác UPDATE thành công, trigger AFTER UPDATE được kích hoạt cho từng hàng đã cập nhật. Trigger ghi một hàng vào order_audit bằng quyền của orders_trigger@localhost.

Caller cần quyền UPDATE trên shop.orders. Caller không cần trực tiếp quyền INSERT trên shop.order_audit nếu security context của trigger có quyền cần thiết và các điều kiện khác đều hợp lệ.

### Lỗi trong trigger ảnh hưởng statement gốc

Nếu INSERT vào order_audit thất bại, câu UPDATE kích hoạt trigger cũng thất bại. Với InnoDB, thay đổi của statement được rollback cùng lỗi trigger. Nếu caller đang ở trong transaction có nhiều statement trước đó, transaction không tự động bị rollback toàn bộ chỉ vì trigger lỗi; caller cần quyết định rollback theo hợp đồng transaction.

Không dùng trigger để che giấu lỗi audit bằng cách bỏ qua exception nếu audit là yêu cầu bắt buộc của nghiệp vụ.

## 6. Tài khoản definer phải tồn tại và được quản lý vòng đời

Definer là một tham chiếu tới account MySQL, không phải một bản sao quyền được nhúng vĩnh viễn trong trigger/event. Nếu account bị DROP USER, đổi host hoặc mất các quyền cần thiết, đối tượng có thể không thực thi được.

Các rủi ro phổ biến:

- Account definer bị xóa trong đợt dọn user cũ.
- Account được tạo lại với host khác, khiến account name không còn khớp.
- Quyền SELECT/INSERT/UPDATE/DELETE cần cho body bị thu hồi.
- Definer là tài khoản cá nhân của nhân viên đã rời tổ chức.
- Restore/migrate object sang server khác nhưng không tạo account definer tương ứng.

### Không xóa definer trước khi chuyển giao đối tượng

Trước khi DROP USER, hãy liệt kê trigger và event đang tham chiếu account đó. Chuyển các đối tượng sang service account được quản lý, kiểm tra grants, triển khai lại hoặc ALTER EVENT phù hợp, rồi mới xóa account cũ.

Không giả định DROP USER sẽ tự động cập nhật DEFINER của trigger/event. Việc xóa account không phải quy trình chuyển giao security context.

## 7. Thay đổi DEFINER của trigger và event

### Trigger

MySQL không cung cấp ALTER TRIGGER để đổi riêng DEFINER. Cách quản lý thường dùng là lấy định nghĩa hiện tại, tạo lại trigger với DEFINER mới theo migration có kiểm soát.

Quy trình:

1. Lưu định nghĩa bằng SHOW CREATE TRIGGER.
2. Xác định definer mới và grants cần thiết.
3. Chuẩn bị câu CREATE TRIGGER với DEFINER mới.
4. Triển khai DROP TRIGGER và CREATE TRIGGER trong cửa sổ migration phù hợp.
5. Kiểm tra metadata TRIGGERS và chạy test UPDATE/INSERT/DELETE kích hoạt trigger.

DROP rồi CREATE tạo khoảng thời gian trigger không tồn tại nếu triển khai không nguyên tử theo cách ứng dụng kỳ vọng. Hãy đánh giá tác động ghi trong lúc migration, khóa metadata và quy trình deploy.

### Event

Event có thể thay đổi bằng ALTER EVENT, bao gồm DEFINER:

~~~sql
ALTER DEFINER = 'archive_scheduler'@'localhost'
EVENT shop.evt_archive_expired;
~~~

Sau khi thay đổi, xác minh metadata và quyền của definer mới. Không chỉ nhìn câu ALTER thành công; event có thể chỉ thất bại ở lần chạy lịch tiếp theo nếu definer thiếu quyền trên bảng.

### Kiểm tra định nghĩa hiện tại

~~~sql
SHOW CREATE TRIGGER shop.trg_orders_status_audit;
SHOW CREATE EVENT shop.evt_archive_expired;
~~~

SHOW CREATE giúp xem câu lệnh DDL và các thuộc tính như DEFINER, schedule, status hoặc SQL body. Quyền xem metadata phụ thuộc quyền của tài khoản kiểm tra và cấu hình server.

## 8. Event là gì và Event Scheduler làm gì?

Event là một đối tượng lưu lịch chạy SQL. Event Scheduler là thread nội bộ của MySQL kiểm tra lịch và kích hoạt các event đã được bật khi đến thời điểm.

Một event có:

- Tên và schema.
- DEFINER.
- Lịch chạy một lần hoặc lặp lại.
- Thời điểm bắt đầu/kết thúc nếu có.
- Trạng thái ENABLE/DISABLE.
- Hành vi sau khi hoàn tất với ON COMPLETION.
- SQL body trong mệnh đề DO.
- Time zone dùng để diễn giải lịch.

Event không chạy chỉ vì event được tạo. Cần scheduler đang hoạt động và trạng thái event cho phép chạy.

### Ví dụ event chạy định kỳ

Tạo bảng lưu session hết hạn:

~~~sql
CREATE TABLE shop.user_sessions (
    session_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (session_id),
    KEY idx_user_sessions_expires (expires_at)
) ENGINE=InnoDB;
~~~

Tạo service account cho event:

~~~sql
CREATE USER 'session_cleanup'@'localhost'
IDENTIFIED BY '<managed-secret>';

GRANT DELETE ON shop.user_sessions
TO 'session_cleanup'@'localhost';
~~~

Tài khoản triển khai cần quyền EVENT trên schema:

~~~sql
GRANT EVENT ON shop.*
TO 'event_deployer'@'localhost';
~~~

Tạo event:

~~~sql
CREATE DEFINER = 'session_cleanup'@'localhost'
EVENT shop.evt_delete_expired_sessions
ON SCHEDULE EVERY 1 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 1 HOUR
ON COMPLETION PRESERVE
ENABLE
DO
    DELETE FROM shop.user_sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Event chạy mỗi giờ. Khi đến lịch, Event Scheduler thực thi DELETE bằng quyền của session_cleanup@localhost. Tài khoản event definer chỉ cần quyền DELETE trên bảng này cho body đơn giản ở ví dụ.

Trong môi trường dữ liệu lớn, một lệnh DELETE không giới hạn có thể tạo transaction lớn, undo log, lock và replication lag. Hãy thiết kế batch cleanup, index theo expires_at và giám sát thời gian chạy nếu bảng có quy mô lớn.

## 9. Hai lớp trạng thái: event_scheduler và trạng thái từng event

Để event thực thi, cần cả hai điều kiện:

1. Biến hệ thống event_scheduler cho phép scheduler chạy.
2. Event cụ thể ở trạng thái ENABLED.

| event_scheduler | Trạng thái event | Kết quả |
|---|---|---|
| ON | ENABLED | Scheduler có thể chạy event khi đến lịch. |
| ON | DISABLED | Event không được thực thi. |
| OFF | ENABLED | Event được bật nhưng scheduler không kích hoạt nó trong lúc OFF. |
| OFF | DISABLED | Event không chạy. |
| DISABLED | ENABLED | Scheduler bị vô hiệu hóa ở cấp server; event không chạy. |

### Kiểm tra event_scheduler

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

Các giá trị có ý nghĩa:

- ON: Event Scheduler đang chạy.
- OFF: Scheduler không chạy; có thể bật lại nếu cấu hình và quyền cho phép.
- DISABLED: Scheduler bị vô hiệu hóa ở cấp server và không thể bật lại chỉ bằng SET GLOBAL trong runtime.

Để bật scheduler trong runtime:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

Thao tác này cần quyền quản trị biến hệ thống phù hợp, thường là SYSTEM_VARIABLES_ADMIN trên MySQL 8.0; SUPER là quyền cũ đã bị thay thế/deprecate trong nhiều ngữ cảnh. Nếu server được khởi động với event_scheduler=DISABLED, cần thay đổi cấu hình startup và khởi động lại theo quy trình vận hành.

Không tự bật scheduler trên replica hoặc mọi node trong cluster khi chưa xác định node nào được phép chạy event.

## 10. ENABLE, DISABLE và trạng thái trên replica

Trạng thái của từng event có thể thay đổi bằng ALTER EVENT:

~~~sql
ALTER EVENT shop.evt_delete_expired_sessions DISABLE;

ALTER EVENT shop.evt_delete_expired_sessions ENABLE;
~~~

ENABLE cho phép event được scheduler xem xét chạy. DISABLE giữ định nghĩa nhưng không cho event thực thi. Đây là cách tạm dừng một lịch mà không phải DROP rồi tạo lại.

### DISABLE ON SLAVE / DISABLE ON REPLICA và replication

MySQL có cú pháp DISABLE ON SLAVE cho event trong một số phiên bản và ngữ cảnh replication; các bản mới dùng thuật ngữ DISABLE ON REPLICA. Cú pháp DISABLE ON SLAVE đã bị deprecate trong các bản MySQL 8.0 mới hơn. Metadata có thể vẫn hiển thị trạng thái SLAVESIDE_DISABLED. Kiểm tra manual của đúng phiên bản trước khi tạo hoặc sửa event.

Không dựa vào DISABLE ON SLAVE như biện pháp duy nhất để chống chạy trùng. Hãy thiết kế topology rõ ràng:

- Xác định node primary được phép chạy scheduled job.
- Đặt event_scheduler OFF hoặc bảo đảm event bị disable trên các replica theo chính sách.
- Kiểm tra trạng thái event sau failover.
- Khi replica được promote, xác nhận chỉ node mới được phép chạy job.
- Với job có tác động bên ngoài database, dùng khóa điều phối/idempotency để tránh thực hiện trùng.

### Event được replicate không đồng nghĩa event nên chạy trên mọi node

DDL event có thể được sao chép qua replication. Nếu nhiều server cùng có scheduler ON và event ENABLED, cùng một công việc có thể được chạy ở nhiều nơi tùy topology và trạng thái event. Đây là rủi ro lớn với job gửi email, xóa dữ liệu, tạo invoice hoặc gọi hệ thống ngoài.

## 11. ON COMPLETION và vòng đời event

Event chạy một lần có thể được cấu hình tự xóa sau khi hoàn tất hoặc được giữ lại:

~~~sql
CREATE DEFINER = 'session_cleanup'@'localhost'
EVENT shop.evt_one_time_cleanup
ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 DAY
ON COMPLETION NOT PRESERVE
ENABLE
DO
    DELETE FROM shop.user_sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

ON COMPLETION NOT PRESERVE là hành vi mặc định cho event one-time nếu không chỉ định khác: sau khi hoàn tất, event được tự động xóa. ON COMPLETION PRESERVE giữ lại event trong metadata sau khi lịch one-time hoàn tất và event được chuyển sang trạng thái DISABLED; nó không tự chạy lại nếu không có lịch mới.

Với event lặp lại, thường dùng ON COMPLETION PRESERVE để giữ định nghĩa lịch. Kiểm tra SHOW CREATE EVENT và metadata để xác nhận hành vi mong muốn.

## 12. Time zone của event

Event lưu time zone được dùng để diễn giải lịch. Nếu không chỉ định riêng, time zone của session tạo event được ghi nhận khi tạo. Vì vậy hai operator tạo cùng biểu thức lịch trong hai session có time zone khác nhau có thể tạo lịch chạy khác nhau.

Kiểm tra:

~~~sql
SHOW CREATE EVENT shop.evt_delete_expired_sessions;

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    TIME_ZONE,
    STARTS,
    ENDS,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop';
~~~

Với lịch nghiệp vụ theo giờ địa phương, cần quyết định rõ daylight saving time, server time zone và session time zone. Nếu nghiệp vụ cần lịch theo UTC, tạo và quản lý event trong session UTC và xác minh TIME_ZONE đã lưu. Không giả định CURRENT_TIMESTAMP trong body luôn cùng time zone với thời điểm operator đang nhìn trên máy client.

## 13. Theo dõi trigger metadata

Xem trigger trong schema:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    DEFINER,
    ACTION_ORDER,
    SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION, ACTION_ORDER;
~~~

Các cột quan trọng:

- TRIGGER_NAME: tên trigger.
- EVENT_MANIPULATION: INSERT, UPDATE hoặc DELETE.
- EVENT_OBJECT_TABLE: bảng được trigger theo dõi.
- ACTION_TIMING: BEFORE hoặc AFTER.
- DEFINER: account security context.
- ACTION_ORDER: thứ tự khi có nhiều trigger cùng timing và event trên một bảng.
- SQL_MODE: SQL mode được lưu khi trigger được tạo.

Xem định nghĩa:

~~~sql
SHOW CREATE TRIGGER shop.trg_orders_status_audit;
~~~

Khi điều tra lỗi, so sánh DEFINER với danh sách account hiện có và SHOW GRANTS của account đó. Đừng chỉ kiểm tra quyền của tài khoản ứng dụng.

## 14. Theo dõi event metadata

Xem danh sách event:

~~~sql
SHOW EVENTS FROM shop;
~~~

Hoặc truy vấn INFORMATION_SCHEMA:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    SQL_MODE
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop'
ORDER BY EVENT_NAME;
~~~

Các trạng thái metadata thường gặp:

| STATUS | Ý nghĩa |
|---|---|
| ENABLED | Event được bật và đủ điều kiện ở cấp event để scheduler chạy. |
| DISABLED | Event bị tắt. |
| SLAVESIDE_DISABLED | Event bị vô hiệu hóa ở phía replica theo cơ chế replication/version tương ứng. |

LAST_EXECUTED cho biết thời điểm chạy gần nhất được ghi nhận; NULL thường có nghĩa event chưa chạy hoặc chưa có lần thực thi được ghi nhận. Nó không tự chứng minh lần chạy thành công. Cần kiểm tra error log, kết quả nghiệp vụ hoặc bảng run history do ứng dụng thiết kế.

Xem DDL:

~~~sql
SHOW CREATE EVENT shop.evt_delete_expired_sessions;
~~~

### Theo dõi thread scheduler

~~~sql
SHOW PROCESSLIST;
~~~

Khi Event Scheduler hoạt động, process list có thể hiển thị thread event_scheduler. Không thấy thread này có thể là dấu hiệu scheduler OFF/DISABLED hoặc trạng thái server khác; xác minh bằng biến hệ thống trước khi kết luận.

## 15. Kiểm tra definer và quyền khi có lỗi

Khi trigger/event không chạy như mong đợi, kiểm tra theo thứ tự:

1. Đối tượng có tồn tại không?
2. DEFINER metadata là account nào, host nào?
3. Account đó còn tồn tại không?
4. Account có bị khóa hoặc thay đổi chính sách xác thực không?
5. Quyền SELECT/INSERT/UPDATE/DELETE cần cho body còn đủ không?
6. Body có gọi routine khác với security context riêng không?
7. Event có ENABLED không?
8. event_scheduler có ON không?
9. Schedule, STARTS, ENDS và TIME_ZONE có đúng không?
10. Error log có ghi lỗi ở lần event chạy không?

Kiểm tra account:

~~~sql
SHOW GRANTS FOR 'orders_trigger'@'localhost';
SHOW GRANTS FOR 'session_cleanup'@'localhost';
~~~

Để kiểm tra account tồn tại:

~~~sql
SELECT User, Host
FROM mysql.user
WHERE User IN ('orders_trigger', 'session_cleanup');
~~~

Truy cập mysql.user cần quyền quản trị phù hợp. Trong ứng dụng quản trị có thể dùng công cụ account management thay vì cấp SELECT mysql.* cho operator thông thường.

## 16. Audit các đối tượng có orphan definer

Khi migrate hoặc dọn account, cần tìm đối tượng có DEFINER không còn tương ứng account trong mysql.user. Các truy vấn dưới đây dành cho DBA có quyền đọc metadata hệ thống.

Trigger:

~~~sql
SELECT
    t.TRIGGER_SCHEMA,
    t.TRIGGER_NAME,
    t.DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS AS t
LEFT JOIN mysql.user AS u
  ON t.DEFINER = CONCAT(u.User, '@', u.Host)
WHERE u.User IS NULL;
~~~

Event:

~~~sql
SELECT
    e.EVENT_SCHEMA,
    e.EVENT_NAME,
    e.DEFINER,
    e.STATUS
FROM INFORMATION_SCHEMA.EVENTS AS e
LEFT JOIN mysql.user AS u
  ON e.DEFINER = CONCAT(u.User, '@', u.Host)
WHERE u.User IS NULL;
~~~

Các truy vấn là kiểm tra sơ bộ theo chuỗi DEFINER; cần chú ý cách biểu diễn account, host và quyền metadata trên phiên bản cụ thể. Không tự động sửa tất cả orphan bằng một definer chung. Mỗi đối tượng có quyền cần thiết khác nhau; hãy xác định owner, review body và cấp least privilege cho definer mới.

## 17. Quyền quản trị Event Scheduler

Event Scheduler là biến hệ thống GLOBAL. Tài khoản ứng dụng thông thường không nên có quyền thay đổi nó.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

Biến event_scheduler là system variable, không phải lịch sử chạy. Metadata trong INFORMATION_SCHEMA.EVENTS và server error log là nguồn kiểm tra chính cho định nghĩa/trạng thái và lỗi thực thi.

Bật/tắt runtime:

~~~sql
SET GLOBAL event_scheduler = OFF;
SET GLOBAL event_scheduler = ON;
~~~

Đây là thao tác vận hành có ảnh hưởng tới toàn bộ event trên instance. Trước khi OFF, xác định job nào phụ thuộc scheduler, tác động của việc bỏ lỡ lịch và cách chạy bù. Trước khi ON, xác nhận không có event cũ hoặc event replicate nào sẽ chạy ngoài dự kiến.

### Cấu hình khi khởi động

Có thể cấu hình event_scheduler trong file cấu hình server hoặc tham số startup:

~~~ini
[mysqld]
event_scheduler=ON
~~~

Nếu đặt DISABLED khi server khởi động, scheduler bị vô hiệu hóa ở cấp server và không thể chuyển sang ON bằng SET GLOBAL trong phiên đang chạy. Thay đổi cấu hình startup cần quy trình restart có kiểm soát.

## 18. Replication, failover và scheduled job

Event là đối tượng schema và có thể tham gia replication. Nếu source tạo event, DDL có thể được ghi vào binary log và áp dụng trên replica. Trạng thái event trên replica phụ thuộc cú pháp tạo event, replication behavior và phiên bản.

Với hệ thống có failover:

- Chỉ định rõ node nào là scheduler owner.
- Giữ event không chạy trên replica đang phục vụ read traffic nếu không được phép.
- Sau promote, kiểm tra event_scheduler và trạng thái từng event.
- Tránh khoảng thời gian cả primary cũ lẫn primary mới đều chạy job.
- Thiết kế job idempotent hoặc có distributed lock/lease nếu có khả năng chạy trùng.
- Ghi nhận lần chạy bằng job ID, thời gian, trạng thái và số hàng tác động.

Event Scheduler không phải hệ thống điều phối phân tán. Nó không tự đảm bảo chỉ có một instance trong nhiều server độc lập chạy cùng một logic. Chính sách failover phải nằm trong thiết kế vận hành.

### Không chạy event chỉ vì đang ở replica

Không suy luận node role từ hostname hoặc tên schema. Hãy dùng topology/role metadata của hệ thống, trạng thái replication và quy trình failover được tổ chức quản lý. Việc bật scheduler là quyết định vận hành có ảnh hưởng tới dữ liệu.

## 19. Logging và khả năng quan sát lần chạy event

MySQL không tự cung cấp một bảng nghiệp vụ đầy đủ cho mọi lần event chạy. Đối với job quan trọng, nên ghi run history bằng một thiết kế phù hợp:

~~~sql
CREATE TABLE shop.event_run_log (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(128) NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NULL,
    error_code INT NULL,
    error_message VARCHAR(512) NULL,
    PRIMARY KEY (run_id),
    KEY idx_event_run_log_name_started (event_name, started_at)
) ENGINE=InnoDB;
~~~

Một stored procedure được event gọi có thể ghi trạng thái bắt đầu/kết thúc và bắt exception để ghi lỗi. Cần quyết định rõ transaction của job và log: nếu toàn bộ body rollback, log trong cùng transaction cũng rollback. Có thể dùng log ở application/observability layer hoặc thiết kế ranh giới ghi nhận phù hợp.

Không lưu password, token, thông tin cá nhân hoặc SQL text nhạy cảm vào log. Chỉ ghi mã lỗi, event name, run ID và metadata đủ để điều tra.

## 20. Những lỗi vận hành thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Trigger báo lỗi quyền khi UPDATE | Definer thiếu quyền trên bảng trigger body sử dụng | SHOW CREATE TRIGGER, INFORMATION_SCHEMA.TRIGGERS, SHOW GRANTS. |
| Trigger không còn chạy sau migration | Trigger bị bỏ sót khi dump/restore hoặc definer không tồn tại | Kiểm tra trigger metadata và account definer. |
| Event ENABLED nhưng không chạy | event_scheduler OFF/DISABLED, lịch chưa tới hoặc event đã hết hạn | Kiểm tra biến hệ thống, STATUS, STARTS/ENDS/TIME_ZONE. |
| Event chạy rồi lỗi | Definer thiếu quyền, bảng đổi schema, body phát lỗi | Kiểm tra error log, SHOW CREATE EVENT và grants. |
| Event chạy hai lần ở hai server | Scheduler bật trên nhiều node hoặc failover overlap | Kiểm tra topology, scheduler owner, replication và idempotency. |
| Event chạy sai giờ | Time zone của session tạo event khác kỳ vọng | Kiểm tra TIME_ZONE và SHOW CREATE EVENT. |
| Event biến mất sau khi chạy | ON COMPLETION NOT PRESERVE cho event one-time | Kiểm tra ON_COMPLETION và định nghĩa lịch. |
| Event không chạy sau khi restore | Scheduler OFF, definer chưa được tạo hoặc event DISABLED | Kiểm tra event_scheduler, account, metadata và grants. |
| Trigger làm UPDATE chậm | Trigger body đọc/ghi thêm bảng, thiếu index hoặc xử lý nhiều hàng | Đo statement, xem body, index và lock waits. |
| DROP USER làm stored object hỏng | Account là definer của trigger/event | Audit DEFINER trước khi xóa account. |

## 21. Checklist triển khai an toàn

### Trước khi tạo trigger/event

- [ ] Xác định chính xác bảng hoặc lịch cần tự động hóa.
- [ ] Chọn service account definer riêng, không dùng root.
- [ ] Cấp quyền tối thiểu cho body.
- [ ] Cấp quyền tạo đối tượng cho deployment account.
- [ ] Nếu chỉ định definer khác, kiểm tra dynamic privilege phù hợp phiên bản.
- [ ] Review body để tránh dynamic SQL không cần thiết và thao tác ngoài phạm vi.
- [ ] Xác định transaction behavior và cách xử lý lỗi.
- [ ] Với event, xác định scheduler owner và timezone.

### Sau khi triển khai

- [ ] Chạy SHOW CREATE TRIGGER/EVENT.
- [ ] Kiểm tra DEFINER trong INFORMATION_SCHEMA.
- [ ] Xác nhận account definer tồn tại và có grants cần thiết.
- [ ] Với trigger, test INSERT/UPDATE/DELETE tương ứng.
- [ ] Với event, xác nhận event_scheduler và STATUS.
- [ ] Kiểm tra lịch STARTS/ENDS/TIME_ZONE.
- [ ] Kiểm tra log và kết quả nghiệp vụ sau lần chạy đầu.
- [ ] Xác nhận replica không chạy job ngoài dự kiến.
- [ ] Lưu owner và quy trình đổi definer khi account được thay thế.

### Trước khi xóa hoặc khóa account

- [ ] Tìm mọi trigger và event đang dùng account.
- [ ] Xác định service account thay thế.
- [ ] Review quyền body và cấp least privilege.
- [ ] Thay definer theo quy trình migration phù hợp.
- [ ] Test đối tượng sau thay đổi.
- [ ] Chỉ DROP USER sau khi không còn object phụ thuộc.

## 22. Bài tập thực hành

### Bài tập A — Quan sát DEFINER của trigger

1. Tạo bảng orders và order_audit.
2. Tạo service account orders_trigger với quyền cần thiết.
3. Tạo trigger có DEFINER rõ ràng.
4. Chạy SHOW CREATE TRIGGER và truy vấn INFORMATION_SCHEMA.TRIGGERS.
5. Dùng application account chỉ có quyền UPDATE orders để kích hoạt trigger.
6. Xác nhận audit row được ghi bằng security context của definer.

### Bài tập B — Thiếu quyền của definer

1. Thu hồi quyền INSERT trên order_audit từ orders_trigger.
2. Thực hiện UPDATE orders làm thay đổi status.
3. Quan sát statement thất bại do trigger không thể INSERT.
4. Kiểm tra trạng thái orders và audit_log trong InnoDB.
5. Cấp lại quyền tối thiểu và chạy lại test.

### Bài tập C — Tạo và bật Event

1. Tạo user_sessions và service account session_cleanup.
2. Cấp DELETE trên user_sessions.
3. Tạo event chạy một lần sau một khoảng thời gian ngắn trong môi trường thử nghiệm.
4. Kiểm tra SHOW EVENTS và INFORMATION_SCHEMA.EVENTS.
5. Theo dõi LAST_EXECUTED và kết quả dữ liệu.
6. Thử DISABLE rồi ENABLE event.

### Bài tập D — Phân biệt scheduler và event status

1. Đặt event_scheduler=OFF trong môi trường thử nghiệm có quyền quản trị.
2. Giữ event ở trạng thái ENABLED.
3. Quan sát event không chạy trong khi scheduler OFF.
4. Bật scheduler ON.
5. Tạo một event DISABLED và xác nhận nó vẫn không chạy.
6. Giải thích vì sao cần kiểm tra cả hai lớp trạng thái.

### Bài tập E — Orphan definer và chuyển giao

1. Tạo trigger/event dùng một service account riêng.
2. Truy vấn INFORMATION_SCHEMA để lập danh sách DEFINER.
3. Trong môi trường thử nghiệm, mô phỏng account bị xóa hoặc không còn khớp host.
4. Xác định đối tượng bị ảnh hưởng.
5. Tạo account thay thế, cấp quyền tối thiểu và chuyển definer theo quy trình.
6. Chạy lại trigger/event để xác nhận.

### Bài tập F — Replication và failover

1. Triển khai event trên source và quan sát metadata trên replica.
2. Xác nhận trạng thái event ở replica theo phiên bản/cấu hình.
3. Đảm bảo chỉ node được chỉ định chạy scheduler.
4. Mô phỏng failover trong môi trường staging.
5. Kiểm tra job không chạy trùng và có thể retry an toàn.

Bạn hoàn thành bài khi giải thích được trigger/event chạy bằng quyền của definer, phân biệt quyền tạo với quyền thực thi, chẩn đoán được definer thiếu quyền hoặc bị orphan, và kiểm tra đúng cả event_scheduler lẫn trạng thái của từng event.

## 23. Nguyên tắc cần ghi nhớ

- DEFINER xác định security context của trigger và event khi chạy.
- Trigger và Event không có tùy chọn SQL SECURITY INVOKER.
- Caller cần quyền thao tác gốc; definer cần quyền cho các câu lệnh trong body.
- Tài khoản triển khai cần quyền tạo đối tượng và quyền đặc biệt nếu chỉ định definer khác account hiện tại.
- Dùng service account riêng và quyền tối thiểu; tránh dùng root hoặc account cá nhân.
- Trigger definer bị thiếu quyền có thể làm statement INSERT/UPDATE/DELETE kích hoạt trigger thất bại.
- Event cần cả event_scheduler cho phép chạy và trạng thái event ENABLED.
- event_scheduler có ON, OFF và DISABLED; DISABLED không thể bật lại bằng SET GLOBAL trong runtime.
- ENABLE/DISABLE là trạng thái của từng event, độc lập với biến scheduler toàn server.
- Event lưu time zone; kiểm tra TIME_ZONE trước khi kết luận lịch sai.
- ON COMPLETION ảnh hưởng vòng đời event one-time.
- Kiểm tra DEFINER qua INFORMATION_SCHEMA và SHOW CREATE.
- Không DROP USER trước khi audit trigger/event phụ thuộc account đó.
- Event replication và failover cần một scheduler owner rõ ràng cùng cơ chế chống chạy trùng.
- Dùng run history/log có kiểm soát cho job quan trọng; không dựa riêng LAST_EXECUTED để kết luận thành công.

Khi quản lý đúng DEFINER, grants và trạng thái Event Scheduler, trigger/event có thể tự động hóa công việc mà vẫn giữ ranh giới quyền rõ ràng. Hãy kiểm tra cả account thực thi, quyền trong body, trạng thái event và vai trò của server trước khi đưa cơ chế tự động vào vận hành.
