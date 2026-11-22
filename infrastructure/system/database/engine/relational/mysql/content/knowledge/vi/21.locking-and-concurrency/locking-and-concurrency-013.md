# LOCK TABLES và ranh giới với khóa giao dịch của InnoDB

MySQL có nhiều cơ chế khóa với phạm vi và vòng đời khác nhau. LOCK TABLES đặt khóa ở mức bảng cho session hiện tại; InnoDB đồng thời có khóa bản ghi, khóa khoảng và khóa ý định để điều phối các transaction. Các cơ chế này không thể thay thế cho nhau. Nếu dùng LOCK TABLES như thể đó là một phần của transaction InnoDB, ứng dụng có thể vô tình commit dữ liệu sớm, làm mất SAVEPOINT hoặc chặn những session khác lâu hơn dự kiến.

LOCK TABLES thường được dùng trong tác vụ quản trị hoặc quy trình cần kiểm soát truy cập ở mức bảng. Với ứng dụng giao dịch thông thường dùng InnoDB, khóa theo hàng thông qua UPDATE, DELETE, SELECT ... FOR UPDATE hoặc SELECT ... FOR SHARE thường phù hợp hơn. Bài học này giải thích cú pháp READ/WRITE, phạm vi session, cách khóa nhiều bảng, ranh giới transaction và sự khác biệt giữa table lock, row lock, intention lock và metadata lock.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích LOCK TABLES, UNLOCK TABLES và phạm vi khóa theo session.
- Phân biệt READ, READ LOCAL và WRITE table lock.
- Khóa nhiều bảng và dùng alias đúng cách.
- Dự đoán session khác có thể đọc hoặc ghi bảng đang bị khóa hay không.
- Hiểu vì sao LOCK TABLES gây implicit commit trước khi lấy khóa.
- Nhận biết ảnh hưởng của UNLOCK TABLES, START TRANSACTION, COMMIT, ROLLBACK và autocommit.
- Phân biệt table lock của SQL layer với khóa bản ghi và khóa khoảng của InnoDB.
- Hiểu intention lock và metadata lock không phải là khóa dữ liệu cùng một mục đích.
- Dùng SELECT ... FOR UPDATE hoặc FOR SHARE trong transaction khi cần khóa hàng.
- Quan sát lock wait, deadlock và metadata lock.
- Chọn cơ chế khóa phù hợp với tác vụ và thiết kế thời gian giữ khóa ngắn.

## 1. Bốn khái niệm khóa cần tách biệt

Khi nói “khóa bảng” hoặc “khóa hàng”, cần xác định chính xác loại khóa và mục tiêu:

| Cơ chế | Phạm vi/chức năng | Vòng đời thường gặp |
|---|---|---|
| LOCK TABLES | Khóa bảng ở SQL layer, giới hạn quyền đọc/ghi của các session | Theo session, thường đến UNLOCK TABLES hoặc khi session kết thúc |
| InnoDB record/gap/next-key lock | Bảo vệ bản ghi hoặc khoảng index trước thao tác xung đột | Theo transaction, giải phóng khi COMMIT hoặc ROLLBACK |
| InnoDB intention lock | Báo hiệu transaction dự định khóa bản ghi trong bảng | Theo transaction, phối hợp với table-level lock |
| Metadata lock (MDL) | Bảo vệ định nghĩa bảng, view và metadata khỏi thay đổi xung đột | Thường gắn với thời gian statement hoặc transaction tùy loại truy cập |

Các khóa này có thể cùng xuất hiện trong một thao tác. Ví dụ, UPDATE một hàng InnoDB lấy khóa bản ghi và intention lock trên bảng; câu lệnh cũng cần metadata lock để bảo vệ định nghĩa bảng trong lúc thực thi. LOCK TABLES lại là một cơ chế khóa bảng tường minh khác ở SQL layer.

Không suy luận rằng một truy vấn có “table lock” nghĩa là InnoDB đã khóa mọi bản ghi theo cùng một cơ chế, hoặc rằng row lock có thể ngăn mọi thay đổi schema. Mỗi loại khóa giải quyết một lớp xung đột khác nhau.

## 2. Cú pháp LOCK TABLES

Cú pháp tổng quát:

    LOCK TABLES
        table_name [AS alias] lock_type
        [, table_name [AS alias] lock_type] ...;

Các loại khóa thông dụng:

- READ: session giữ khóa được đọc; session khác cũng có thể đọc, nhưng phải chờ nếu muốn ghi.
- READ LOCAL: biến thể READ cho phép một số concurrent INSERT không xung đột trên storage engine hỗ trợ hành vi này, chẳng hạn MyISAM. Với InnoDB, READ LOCAL tương đương READ.
- WRITE: session giữ khóa được đọc và ghi; các session khác phải chờ khi truy cập bảng theo cách xung đột, bao gồm đọc thông thường.

Ví dụ:

    LOCK TABLES inventory_demo READ;

    SELECT * FROM inventory_demo;

    UNLOCK TABLES;

Ví dụ khóa ghi:

    LOCK TABLES inventory_demo WRITE;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    UNLOCK TABLES;

READ và WRITE là khóa tường minh ở mức bảng. Chúng có thể chặn nhiều thao tác hơn mức cần thiết nếu ứng dụng chỉ muốn bảo vệ một vài hàng.

## 3. READ lock và WRITE lock khác nhau thế nào?

Bảng sau mô tả hành vi khái quát của table lock:

| Tình huống | Session đang giữ READ | Session khác khi bảng bị READ | Session đang giữ WRITE | Session khác khi bảng bị WRITE |
|---|---|---|---|---|
| SELECT | Được phép | Được phép | Được phép | Phải chờ |
| INSERT | Không được phép theo quyền của READ lock | Phải chờ | Được phép | Phải chờ |
| UPDATE | Không được phép theo quyền của READ lock | Phải chờ | Được phép | Phải chờ |
| DELETE | Không được phép theo quyền của READ lock | Phải chờ | Được phép | Phải chờ |

READ lock phù hợp khi session cần đọc ổn định ở mức bảng trong một tác vụ và chấp nhận chặn ghi từ session khác. WRITE lock độc quyền hơn: session giữ khóa có thể đọc/ghi, session khác phải chờ truy cập xung đột.

Hành vi cụ thể còn chịu ảnh hưởng bởi storage engine, loại statement, quyền và cơ chế khóa khác. Đặc biệt với InnoDB, LOCK TABLES không nên được xem là cách mặc định để bảo vệ các hàng trong luồng nghiệp vụ. Phần sau sẽ so sánh với row-level locking.

## 4. Khóa nhiều bảng trong một câu lệnh

Nếu một tác vụ cần truy cập nhiều bảng, hãy liệt kê tất cả bảng cần dùng trong một câu LOCK TABLES:

    LOCK TABLES
        account_demo READ,
        transfer_audit_demo WRITE;

    SELECT account_id, balance
    FROM account_demo
    WHERE account_id = 1;

    INSERT INTO transfer_audit_demo
        (transfer_id, description)
    VALUES
        (9001, 'Manual reconciliation');

    UNLOCK TABLES;

Không nên khóa từng bảng rời rạc bằng nhiều lần LOCK TABLES rồi cho rằng các khóa cũ vẫn luôn được giữ. Một câu LOCK TABLES mới có thể thay thế tập khóa explicit hiện tại của session. Hãy xác định trước toàn bộ bảng cần thiết và khóa chúng trong một lần theo thứ tự thống nhất.

Khi khóa một view, MySQL đưa các bảng nền của view vào tập khóa. Khi thao tác qua trigger hoặc quan hệ khóa ngoại, MySQL cũng tự mở và khóa các bảng liên quan theo quy tắc của trigger và foreign key. Hãy tính cả những truy cập gián tiếp này khi đánh giá phạm vi khóa và quyền. Với nghiệp vụ phức tạp, transaction InnoDB và khóa theo hàng thường dễ quản lý hơn.

### 4.1. Khóa bảng có alias

Nếu câu truy vấn dùng alias, khai báo alias trong LOCK TABLES và dùng đúng alias đó:

    LOCK TABLES
        inventory_demo AS i WRITE,
        warehouse_demo AS w READ;

    SELECT i.product_id, i.available_quantity, w.warehouse_name
    FROM inventory_demo AS i
    JOIN warehouse_demo AS w
        ON w.warehouse_id = i.warehouse_id;

    UNLOCK TABLES;

Sau khi khóa bằng alias, hãy tham chiếu bảng qua alias tương ứng trong các statement của session. Không giả định rằng khóa tên bảng gốc tự động bao phủ mọi alias khác mà câu truy vấn có thể sử dụng.

### 4.2. Tránh khóa cùng bảng nhiều lần bằng nhiều alias

LOCK TABLES có quy tắc quản lý alias riêng. Không khóa cùng một bảng nhiều lần dưới các alias khác nhau để mô phỏng self-join. Nếu truy vấn cần tự nối một bảng, hãy thiết kế câu LOCK TABLES và alias theo cú pháp MySQL cho đúng; nếu không chắc chắn, ưu tiên transaction InnoDB với câu truy vấn có alias rõ ràng.

Ví dụ self-join khi chỉ đọc bình thường không cần LOCK TABLES:

    SELECT
        child.employee_id,
        manager.employee_id AS manager_id
    FROM employee_demo AS child
    LEFT JOIN employee_demo AS manager
        ON manager.employee_id = child.manager_id;

Chỉ thêm explicit table lock khi có lý do vận hành cụ thể và đã xác minh các quy tắc alias của phiên bản server.

## 5. Phạm vi và vòng đời của table lock

LOCK TABLES tạo khóa cho session hiện tại. Session khác không thể giải phóng khóa thay cho session đang giữ. Thông thường khóa được giữ cho đến khi:

- Session thực hiện UNLOCK TABLES.
- Session kết thúc hoặc connection bị đóng.
- Một thao tác transaction/DDL khác làm giải phóng table lock theo quy tắc MySQL.

Điều này có nghĩa một ứng dụng giữ connection trong connection pool mà quên UNLOCK TABLES có thể để khóa tồn tại lâu hơn thời gian xử lý request. Nếu connection được tái sử dụng, request tiếp theo có thể kế thừa trạng thái session không mong muốn.

Luôn dùng cleanup rõ ràng trong code ứng dụng:

1. Lấy connection.
2. Thực hiện LOCK TABLES.
3. Chạy thao tác cần thiết với thời gian ngắn.
4. Trong nhánh thành công hoặc lỗi, bảo đảm UNLOCK TABLES khi session còn hoạt động.
5. Đưa connection về pool chỉ sau khi xác minh trạng thái session đã sạch.

Nếu connection bị mất, server sẽ giải phóng khóa gắn với session khi session thực sự kết thúc. Không nên dựa vào việc ứng dụng đã timeout để giả định connection trên server đã đóng ngay lập tức.

LOCK TABLES cũng lấy metadata lock để bảo vệ đối tượng được khóa. Một số DDL không được phép chạy khi table lock đang có hiệu lực, và ALTER TABLE trên bảng đã khóa có thể làm bảng bị unlock theo quy tắc MySQL. Vì vậy, không dùng table lock như một cách giữ nguyên quyền truy cập xuyên qua migration schema.

LOCK TABLES và UNLOCK TABLES không được gọi bên trong stored program. Nếu cần khóa trong stored procedure hoặc trigger, hãy thiết kế lại ranh giới thao tác bằng transaction và khóa InnoDB phù hợp.

## 6. LOCK TABLES và ranh giới transaction

Đây là điểm quan trọng nhất của bài học: LOCK TABLES không phải một câu lệnh mở đầu transaction. MySQL commit transaction đang hoạt động trước khi cố gắng lấy explicit table lock.

Ví dụ:

    START TRANSACTION;

    UPDATE account_demo
    SET balance = balance - 20.00
    WHERE account_id = 1;

    LOCK TABLES account_demo WRITE;

    ROLLBACK;

UPDATE trước LOCK TABLES đã bị commit bởi implicit commit của LOCK TABLES. ROLLBACK sau đó không hoàn tác thay đổi số dư đó.

Sơ đồ:

    START TRANSACTION
           |
           v
    UPDATE account_demo
           |
           v
    LOCK TABLES account_demo WRITE
           |
           +---- implicit commit transaction đang mở
           |
           +---- sau đó mới lấy explicit table lock
           |
           v
    ROLLBACK
           |
           +---- không thể hoàn tác UPDATE đã commit

Vì vậy, không đặt LOCK TABLES giữa một chuỗi DML mà ứng dụng mong muốn rollback cùng nhau.

### 6.1. UNLOCK TABLES có thể commit transaction

UNLOCK TABLES giải phóng các khóa được lấy bằng LOCK TABLES. Nếu session dùng LOCK TABLES để lấy table lock, UNLOCK TABLES có thể implicit commit transaction đang hoạt động theo quy tắc của MySQL.

Điều này có nghĩa UNLOCK TABLES cũng là một ranh giới cần xem xét. Không dùng nó như một lệnh “chỉ nhả khóa” mà không kiểm tra transaction state.

Ngoại lệ cần phân biệt: UNLOCK TABLES không commit transaction chỉ vì session đang giải phóng global read lock được tạo bằng FLUSH TABLES WITH READ LOCK. Global read lock là cơ chế khác với tập khóa tạo bởi LOCK TABLES.

### 6.2. START TRANSACTION giải phóng table lock hiện có

Bắt đầu transaction mới bằng START TRANSACTION hoặc BEGIN sẽ kết thúc transaction hiện tại nếu có và giải phóng các table lock hiện đang giữ theo quy tắc MySQL.

Do đó, không viết:

    LOCK TABLES account_demo WRITE;
    START TRANSACTION;
    UPDATE account_demo
    SET balance = balance - 10
    WHERE account_id = 1;

rồi cho rằng WRITE lock vẫn được giữ. START TRANSACTION làm thay đổi ranh giới và giải phóng explicit table lock đã có. Nếu cần bảo vệ dữ liệu giao dịch, hãy dùng transaction InnoDB và row-level locking thay vì cố ghép hai cơ chế.

### 6.3. COMMIT và ROLLBACK không phải cách thay thế UNLOCK TABLES

COMMIT hoặc ROLLBACK kết thúc transaction InnoDB và giải phóng các row lock cùng internal InnoDB table lock thuộc transaction. Explicit table lock ở MySQL layer do LOCK TABLES quản lý có vòng đời riêng. Dùng UNLOCK TABLES để giải phóng table lock và dùng COMMIT/ROLLBACK để kết thúc transaction theo đúng mục đích.

Không thiết kế code theo giả định rằng COMMIT luôn tương đương UNLOCK TABLES hoặc ngược lại. Các lệnh có tương tác theo quy tắc MySQL, nên cần tách rõ:

- Table lock được quản lý bởi LOCK TABLES/UNLOCK TABLES.
- Transaction được quản lý bởi START TRANSACTION, COMMIT và ROLLBACK.
- Row lock của InnoDB được giữ theo transaction.

ROLLBACK không giải phóng table lock được lấy bằng LOCK TABLES. Nếu rollback một transaction trong lúc đang giữ table lock, vẫn phải gọi UNLOCK TABLES để nhả khóa ở MySQL layer.

### 6.4. Autocommit và LOCK TABLES

Kiểm tra autocommit của session:

    SELECT @@SESSION.autocommit;

Với autocommit = 1, DML thông thường được commit khi statement hoàn tất. Explicit table lock ở MySQL layer có thể vẫn được giữ theo session đến UNLOCK TABLES, nhưng InnoDB không lấy internal table lock cho LOCK TABLES trong chế độ này. Điều đó làm InnoDB không phối hợp đầy đủ table lock với row lock của transaction khác; deadlock liên quan hai lớp khóa có thể khó phát hiện. Vì vậy, không nên dùng LOCK TABLES trên bảng InnoDB với autocommit = 1 như một cơ chế đồng bộ giao dịch.

Nếu thật sự cần dùng LOCK TABLES với bảng transactional như InnoDB, MySQL hướng dẫn bắt đầu bằng SET autocommit = 0, sau đó LOCK TABLES; không dùng START TRANSACTION ngay trước LOCK TABLES. Ví dụ:

    SET autocommit = 0;

    LOCK TABLES
        inventory_demo WRITE,
        warehouse_demo READ;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    SELECT warehouse_id, warehouse_name
    FROM warehouse_demo;

    COMMIT;
    UNLOCK TABLES;
    SET autocommit = 1;

Với autocommit = 0 và innodb_table_locks = 1 (mặc định), LOCK TABLES lấy khóa ở MySQL layer và khóa nội bộ tương ứng trong InnoDB. COMMIT giải phóng các khóa InnoDB của transaction; khóa table ở MySQL layer vẫn còn cho đến UNLOCK TABLES. Vì vậy, thứ tự an toàn là commit transaction trước rồi mới unlock table. Nếu transaction cần hủy, dùng ROLLBACK rồi UNLOCK TABLES; ROLLBACK không tự giải phóng table lock ở MySQL layer.

Đổi autocommit từ 0 sang 1 có thể commit transaction đang hoạt động. Trong ứng dụng dùng connection pool, hãy khôi phục autocommit và trạng thái khóa sau khi hoàn tất, kể cả trong nhánh lỗi. Chỉ dùng quy trình này khi có lý do rõ ràng; với ứng dụng InnoDB thông thường, row-level locking vẫn là lựa chọn nên ưu tiên.

## 7. InnoDB row-level locking hoạt động ra sao?

InnoDB dùng khóa ở mức index record và các khoảng index cần thiết để bảo vệ thao tác. Khi một transaction cập nhật hoặc xóa hàng, InnoDB khóa các record liên quan. Một locking read như SELECT ... FOR UPDATE yêu cầu khóa độc quyền trên các record được đọc; SELECT ... FOR SHARE yêu cầu khóa chia sẻ.

Ví dụ:

    START TRANSACTION;

    SELECT product_id, available_quantity
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100
      AND available_quantity > 0;

    COMMIT;

Transaction khóa hàng sản phẩm trước khi kiểm tra và cập nhật tồn kho. Session khác muốn cập nhật cùng record sẽ phải chờ khóa được giải phóng hoặc nhận lỗi timeout/deadlock tùy tình huống.

Khóa được giữ đến COMMIT hoặc ROLLBACK. Đây là điểm khác biệt cơ bản với explicit table lock theo session.

### 7.1. Khóa bản ghi thực chất dựa trên index

InnoDB tổ chức row lock dựa trên index record, không phải một khóa trừu tượng chỉ gắn vào “hàng” theo cách người dùng nhìn thấy. Truy vấn có điều kiện trên primary key thường khóa phạm vi rất cụ thể. Truy vấn theo điều kiện không có index phù hợp có thể phải quét và khóa nhiều record hơn dự kiến.

Ví dụ:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

Nếu product_id là primary key, InnoDB có thể tìm đúng record theo index. Nếu điều kiện lọc không có index phù hợp, phạm vi record được scan và khóa có thể rộng hơn, làm tăng tranh chấp.

Vì vậy, index không chỉ ảnh hưởng tốc độ đọc mà còn ảnh hưởng phạm vi khóa và khả năng đồng thời.

### 7.2. Record lock, gap lock và next-key lock

- Record lock khóa một index record.
- Gap lock khóa khoảng trống giữa các index record, ngăn một số thao tác insert vào khoảng đó.
- Next-key lock kết hợp record lock với khoảng ngay trước record, thường dùng để ngăn phantom trong các điều kiện và isolation level phù hợp.

Không phải mọi SELECT ... FOR UPDATE đều khóa đúng một hàng. Với truy vấn theo range, isolation level và execution plan có thể làm InnoDB khóa cả khoảng index. Hãy kiểm tra điều kiện, index và isolation level khi phân tích lock contention.

### 7.3. Locking read và consistent read

SELECT thông thường trong InnoDB thường là consistent read dựa trên MVCC; nó đọc một snapshot phù hợp với isolation level mà không lấy row lock chỉ để đọc.

SELECT ... FOR UPDATE và SELECT ... FOR SHARE là locking read. Chúng yêu cầu khóa để bảo vệ các hàng được đọc khỏi thay đổi xung đột trong transaction.

Không thêm FOR UPDATE vào mọi SELECT. Chỉ dùng khi transaction cần bảo vệ một quyết định hoặc cập nhật dựa trên dữ liệu vừa đọc.

## 8. SELECT ... FOR UPDATE và FOR SHARE

Hai cú pháp thường dùng:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR SHARE;

FOR UPDATE lấy khóa độc quyền cho locking read; FOR SHARE lấy khóa chia sẻ. Các transaction khác có thể cùng giữ shared lock nếu tương thích, nhưng muốn sửa record sẽ phải chờ shared lock được giải phóng.

FOR SHARE là cú pháp của MySQL 8.0. Trên MySQL 5.7, cú pháp tương ứng thường dùng là LOCK IN SHARE MODE. Hãy chọn cú pháp theo phiên bản server mà ứng dụng hỗ trợ.

Trong MySQL 8.0, cú pháp có thể bổ sung NOWAIT hoặc SKIP LOCKED:

    SELECT *
    FROM job_queue
    WHERE job_status = 'READY'
    ORDER BY created_at, job_id
    LIMIT 10
    FOR UPDATE SKIP LOCKED;

SKIP LOCKED bỏ qua các hàng đang bị transaction khác khóa, hữu ích cho nhiều worker cùng lấy việc từ queue. Kết quả không đại diện cho một view nhất quán đầy đủ của hàng phù hợp vì các hàng đang bị khóa bị bỏ qua. Không dùng nó cho báo cáo cần đọc đầy đủ.

NOWAIT yêu cầu truy vấn trả lỗi ngay nếu không lấy được khóa thay vì chờ:

    SELECT *
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE NOWAIT;

NOWAIT và SKIP LOCKED có yêu cầu phiên bản; xác minh MySQL server đang triển khai trước khi sử dụng.

### 8.1. Cần transaction rõ ràng

Để giữ row lock qua nhiều statement, hãy mở transaction:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory_demo
    WHERE product_id = 100
    FOR UPDATE;

    -- Ứng dụng kiểm tra và cập nhật trong cùng connection.

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

    COMMIT;

Nếu dùng autocommit và không mở transaction rõ ràng, statement kết thúc có thể kết thúc transaction ngầm và giải phóng khóa ngay sau statement. Khi cần khóa qua nhiều bước, phải kiểm soát transaction boundary.

## 9. InnoDB intention lock không phải LOCK TABLES

InnoDB dùng intention lock ở mức bảng để báo rằng transaction đang hoặc sẽ khóa các record trong bảng:

- IS (intention shared): transaction dự định lấy shared lock ở mức record.
- IX (intention exclusive): transaction dự định lấy exclusive lock ở mức record.

Ví dụ UPDATE một record thường cần intention exclusive lock trên bảng và exclusive record lock trên index record tương ứng.

Intention lock cho phép InnoDB phối hợp row lock với các thao tác cần table-level lock. Nó không có nghĩa toàn bộ bảng đã bị khóa để ngăn mọi session đọc/ghi. Nhiều transaction có thể cùng giữ IX trên một bảng và khóa các record khác nhau.

Phân biệt:

| Khóa | Ai yêu cầu? | Ý nghĩa |
|---|---|---|
| IX/IS | InnoDB transaction tự quản lý | Báo hiệu ý định khóa record |
| LOCK TABLES ... WRITE | Session yêu cầu tường minh | Khóa bảng ở SQL layer, chặn truy cập xung đột từ session khác |
| Record lock | InnoDB transaction | Khóa index record cụ thể |

Không nhầm intention lock với explicit WRITE lock. Intention lock là một phần của hệ thống phối hợp khóa InnoDB, không phải lệnh quản trị khóa toàn bảng.

## 10. Metadata lock khác table lock và row lock

Metadata lock (MDL) bảo vệ định nghĩa đối tượng database. Một truy vấn SELECT hoặc DML cần metadata lock phù hợp để bảo đảm cấu trúc bảng không bị thay đổi không an toàn trong lúc statement đang sử dụng.

Ví dụ:

- Session A mở transaction và truy vấn một bảng.
- Transaction của A giữ metadata lock cần thiết trong thời gian transaction.
- Session B chạy ALTER TABLE trên cùng bảng và phải chờ metadata lock tương thích.

Đây là lý do một ALTER TABLE có thể chờ dù không có row lock nào trên các hàng mà DDL cần sửa. MDL bảo vệ metadata, không phải giá trị của từng hàng.

| Cơ chế | Bảo vệ | Ví dụ xung đột |
|---|---|---|
| Metadata lock | Cấu trúc bảng/view | ALTER TABLE chờ transaction đang dùng bảng |
| Table lock | Truy cập bảng ở SQL layer | WRITE lock chặn session khác đọc/ghi |
| InnoDB row/index lock | Record hoặc khoảng index | Hai transaction cập nhật cùng hàng |

Khi điều tra “database bị khóa”, cần xác định loại lock đang chờ trước khi chọn cách xử lý. KILL một transaction đang giữ MDL, bỏ table lock hoặc giảm row-lock contention là các hành động khác nhau và có ảnh hưởng dữ liệu khác nhau.

## 11. So sánh LOCK TABLES với khóa giao dịch InnoDB

| Tiêu chí | LOCK TABLES | InnoDB row-level locking |
|---|---|---|
| Phạm vi | Bảng | Index record và có thể cả khoảng |
| Cách yêu cầu | LOCK TABLES READ/WRITE | UPDATE/DELETE hoặc SELECT ... FOR UPDATE/FOR SHARE |
| Vòng đời | Theo session và quy tắc UNLOCK/transaction/DDL | Theo transaction |
| Tương tác transaction | LOCK TABLES gây implicit commit trước khi lấy khóa | Được thiết kế để hoạt động trong transaction |
| Mức độ đồng thời | Thường thô và dễ chặn nhiều session | Có thể cho transaction khác làm việc trên record không xung đột |
| Phù hợp | Tác vụ quản trị hoặc quy trình đặc biệt cần khóa bảng | Luồng giao dịch ứng dụng |
| Rủi ro | Giữ khóa lâu làm chặn rộng; dễ phá transaction boundary | Deadlock, lock wait và phạm vi khóa rộng nếu thiếu index |

Với bảng InnoDB, hãy ưu tiên transaction và row-level locking cho nghiệp vụ. LOCK TABLES không phải cách đơn giản hóa SELECT ... FOR UPDATE; nó có semantics commit và phạm vi chặn khác.

## 12. Thực hành hai session: quan sát READ và WRITE lock

Chạy ví dụ trong database sandbox bằng hai connection độc lập. Không chạy trên bảng production.

Các bước ở phần này minh họa khả năng chặn của table lock ở MySQL layer. Với InnoDB production, nếu cần phối hợp table lock với khóa nội bộ của engine, hãy dùng đúng quy trình autocommit = 0 ở mục 6.4; không lấy ví dụ autocommit mặc định ở đây làm mẫu thiết kế transaction.

### 12.1. Tạo bảng thử nghiệm

    CREATE TABLE lock_table_demo (
        item_id INT NOT NULL PRIMARY KEY,
        item_name VARCHAR(80) NOT NULL,
        quantity INT NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO lock_table_demo (item_id, item_name, quantity)
    VALUES
        (1, 'Keyboard', 10),
        (2, 'Mouse', 20);

Đảm bảo cả hai session đều kết nối đến cùng database.

### 12.2. Session A lấy READ lock

    LOCK TABLES lock_table_demo READ;

    SELECT * FROM lock_table_demo;

Giữ session A ở trạng thái này và chuyển sang session B.

### 12.3. Session B thử đọc và ghi

Đọc từ session B:

    SELECT * FROM lock_table_demo;

READ lock cho phép session khác đọc, vì vậy SELECT có thể hoàn tất.

Ghi từ session B:

    UPDATE lock_table_demo
    SET quantity = quantity + 1
    WHERE item_id = 1;

UPDATE phải chờ vì session A đang giữ READ lock. Không để session B chờ vô hạn trong bài lab; sau khi quan sát trạng thái, quay lại session A và chạy:

    UNLOCK TABLES;

Session B có thể tiếp tục sau khi khóa được giải phóng.

### 12.4. Session A lấy WRITE lock

Trong session A:

    LOCK TABLES lock_table_demo WRITE;

    UPDATE lock_table_demo
    SET quantity = quantity - 1
    WHERE item_id = 1;

    SELECT * FROM lock_table_demo;

Session A có thể đọc và ghi bảng. Trong session B, thử:

    SELECT * FROM lock_table_demo;

Truy vấn đọc của B phải chờ WRITE lock. Sau khi A chạy:

    UNLOCK TABLES;

B mới có thể tiếp tục. Thử nghiệm cho thấy WRITE lock chặn cả đọc và ghi từ session khác trong thời gian giữ khóa.

## 13. Thực hành hai session: khóa hàng InnoDB

Tạo bảng tồn kho:

    CREATE TABLE row_lock_demo (
        product_id INT NOT NULL PRIMARY KEY,
        available_quantity INT NOT NULL
    ) ENGINE = InnoDB;

    INSERT INTO row_lock_demo (product_id, available_quantity)
    VALUES (100, 5), (200, 8);

### 13.1. Session A khóa một hàng

    START TRANSACTION;

    SELECT product_id, available_quantity
    FROM row_lock_demo
    WHERE product_id = 100
    FOR UPDATE;

Giữ transaction mở. Record product_id = 100 đang bị khóa độc quyền bởi A.

### 13.2. Session B cập nhật hàng khác

    UPDATE row_lock_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 200;

Vì B cập nhật record khác, thao tác có thể hoàn tất nếu không có xung đột khác.

### 13.3. Session B cập nhật cùng hàng

    UPDATE row_lock_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100;

B phải chờ khóa của A. Quay lại A:

    COMMIT;

Sau khi A commit, B có thể tiếp tục và cập nhật record.

So sánh với WRITE table lock: WRITE lock chặn truy cập bảng rộng hơn; row lock chỉ bảo vệ record và phạm vi index liên quan. Đây là lý do InnoDB có thể duy trì mức đồng thời cao hơn khi các transaction thao tác trên các hàng không xung đột.

## 14. Khóa theo hàng không đồng nghĩa luôn chỉ khóa một hàng

Một truy vấn có điều kiện:

    SELECT *
    FROM row_lock_demo
    WHERE product_id >= 100
    FOR UPDATE;

có thể khóa nhiều record và khoảng index tùy index, isolation level và kế hoạch thực thi. Nếu điều kiện không dùng index phù hợp, phạm vi scan có thể rộng.

Để giảm lock contention:

- Dùng primary key hoặc index phù hợp cho điều kiện khóa.
- Giữ transaction ngắn.
- Chỉ khóa những hàng cần thiết.
- Truy cập các hàng theo thứ tự nhất quán giữa các transaction để giảm deadlock.
- Không gọi API bên ngoài hoặc chờ người dùng trong khi giữ transaction.
- Commit/rollback ngay khi công việc dữ liệu hoàn tất.

Không thêm FOR UPDATE cho truy vấn chỉ đọc báo cáo. Một locking read không cần thiết có thể làm giảm khả năng đồng thời và tạo hàng chờ.

## 15. READ LOCAL và storage engine

READ LOCAL là biến thể của READ lock cho phép một số concurrent INSERT không xung đột trên storage engine hỗ trợ hành vi này, chẳng hạn MyISAM. Với InnoDB, READ LOCAL giống READ và không bật đồng thời ghi trong khi giữ table lock.

Trước khi dùng LOCK TABLES, kiểm tra storage engine:

    SELECT
        TABLE_NAME,
        ENGINE
    FROM information_schema.tables
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'lock_table_demo';

InnoDB có transaction, MVCC và row-level locking. MyISAM không hỗ trợ transaction theo cách InnoDB hỗ trợ; các thao tác ghi của MyISAM dựa nhiều hơn vào table-level locking. Vì vậy, cùng một câu LOCK TABLES có thể có tác động vận hành khác tùy engine.

Đừng chọn READ LOCAL hoặc LOCK TABLES chỉ dựa trên tên lock. Hãy kiểm tra engine, phiên bản và workload thực tế.

## 16. Quyền cần có

Để dùng LOCK TABLES, tài khoản cần quyền LOCK TABLES và quyền SELECT trên từng đối tượng được khóa. Các câu lệnh thực hiện trong khi giữ khóa vẫn cần quyền SELECT, INSERT, UPDATE hoặc DELETE tương ứng.

Ví dụ quản trị viên có thể cấp quyền cần thiết trong môi trường kiểm thử:

    GRANT LOCK TABLES, SELECT, UPDATE
    ON inventory_lab.*
    TO 'inventory_operator'@'%';

Không cấp quyền rộng hơn nhu cầu. LOCK TABLES có thể làm ảnh hưởng các session khác và nên chỉ cấp cho tài khoản vận hành hoặc tác vụ có lý do cụ thể. Kiểm tra quyền thực tế bằng SHOW GRANTS:

    SHOW GRANTS FOR CURRENT_USER();

Tên tài khoản và host trong GRANT phải khớp account đã tạo; ví dụ trên chỉ minh họa cú pháp.

## 17. Quan sát lock wait và deadlock

Khi một statement chờ, trước hết xác định session đang chờ và session giữ khóa.

Thông tin session:

    SHOW FULL PROCESSLIST;

Thông tin transaction InnoDB:

    SELECT *
    FROM information_schema.innodb_trx;

Với MySQL 8.0, Performance Schema có các bảng hữu ích:

    SELECT *
    FROM performance_schema.data_locks;

    SELECT *
    FROM performance_schema.data_lock_waits;

    SELECT *
    FROM performance_schema.metadata_locks;

Tên cột và quyền xem có thể phụ thuộc phiên bản/cấu hình. Dùng các bảng này để xác định lock type, object, thread và quan hệ blocker/waiter.

Để xem thông tin deadlock gần nhất trong InnoDB:

    SHOW ENGINE INNODB STATUS;

Phần LATEST DETECTED DEADLOCK mô tả transaction tham gia deadlock, statement liên quan và transaction được chọn làm victim. Khi deadlock xảy ra mà InnoDB phát hiện được chu trình, InnoDB tự chọn một transaction làm victim để rollback; ứng dụng cần xử lý lỗi và có thể retry toàn bộ transaction theo chính sách có giới hạn. Deadlock liên quan table lock ở MySQL layer và row lock có thể không được InnoDB phát hiện nếu internal table lock không được lấy.

### 17.1. Lock wait timeout và deadlock khác nhau

- Lock wait timeout: transaction chờ khóa quá thời gian cho phép. Tùy cấu hình và statement, lỗi có thể rollback statement hoặc transaction theo quy tắc InnoDB.
- Deadlock: hai hoặc nhiều transaction tạo chu trình chờ khóa; InnoDB phát hiện chu trình và chọn một transaction làm victim.
- Metadata lock wait: statement chờ khóa metadata của đối tượng; thường liên quan transaction hoặc DDL đang sử dụng bảng.
- Table lock wait: session chờ explicit table lock hoặc table-level lock khác.

Không xử lý mọi trường hợp bằng cách tăng timeout. Trước hết hãy xác định nguyên nhân, thời gian giữ khóa, index và thứ tự truy cập dữ liệu.

## 18. FLUSH TABLES WITH READ LOCK không giống LOCK TABLES READ

Một lệnh thường bị nhầm với LOCK TABLES là:

    FLUSH TABLES WITH READ LOCK;

Lệnh này lấy global read lock, ảnh hưởng rộng đến hoạt động ghi trên server và thường được dùng trong một số quy trình backup/snapshot phối hợp với binary log. Nó không giống khóa READ trên một bảng đơn lẻ.

Giải phóng global read lock bằng:

    UNLOCK TABLES;

Tuy cùng dùng UNLOCK TABLES, hai cơ chế có quy tắc transaction khác nhau. Đặc biệt, UNLOCK TABLES sau FLUSH TABLES WITH READ LOCK không có cùng implicit commit behavior như khi giải phóng table locks được lấy bằng LOCK TABLES.

Global read lock có ảnh hưởng lớn đến workload. Không chạy trên production nếu chưa hiểu quy trình backup, replication, thời gian giữ khóa và tác động đến ghi dữ liệu.

## 19. Khi nào nên dùng LOCK TABLES?

LOCK TABLES có thể hữu ích cho:

- Tác vụ quản trị cũ cần bảo vệ toàn bảng trong một khoảng ngắn.
- Quy trình đọc/ghi đặc biệt với storage engine dựa trên table locking.
- Một số tác vụ export hoặc maintenance cần phối hợp khóa bảng và đã được thiết kế rõ ràng.
- Công cụ vận hành cần đảm bảo không có session khác thay đổi bảng trong khi thực hiện một chuỗi thao tác có kiểm soát.

Với ứng dụng giao dịch InnoDB, ưu tiên:

- UPDATE có điều kiện nguyên tử thay vì SELECT rồi UPDATE không khóa.
- SELECT ... FOR UPDATE khi cần đọc rồi quyết định cập nhật trong cùng transaction.
- SELECT ... FOR SHARE khi cần bảo vệ dữ liệu đọc trước các thao tác xung đột.
- Unique constraint hoặc foreign key để bảo vệ invariant dữ liệu ở database.
- Optimistic concurrency bằng version column khi phù hợp.

Ví dụ giảm race condition mà không cần LOCK TABLES:

    UPDATE inventory_demo
    SET available_quantity = available_quantity - 1
    WHERE product_id = 100
      AND available_quantity > 0;

    SELECT ROW_COUNT();

Nếu ROW_COUNT() bằng 1, một đơn vị tồn kho đã được trừ. Nếu bằng 0, sản phẩm không tồn tại hoặc không đủ hàng; ứng dụng có thể kiểm tra nguyên nhân theo yêu cầu. Đây là cập nhật có điều kiện nguyên tử, tránh một bước SELECT không khóa rồi UPDATE có thể tranh chấp.

## 20. Những lỗi thường gặp

- Nghĩ LOCK TABLES bắt đầu một transaction.
- Chạy UPDATE rồi LOCK TABLES và mong ROLLBACK sau đó hoàn tác UPDATE.
- Nghĩ UNLOCK TABLES chỉ giải phóng khóa và không thể ảnh hưởng transaction.
- Dùng START TRANSACTION trong lúc đang giữ table lock rồi nghĩ khóa vẫn còn.
- Nhầm COMMIT/ROLLBACK với UNLOCK TABLES.
- Giữ table lock lâu trong connection pool và trả connection về pool khi chưa cleanup.
- Chỉ khóa một bảng nhưng câu lệnh còn truy cập bảng khác, alias khác hoặc bảng được trigger dùng.
- Dùng WRITE lock khi chỉ cần khóa một record.
- Nghĩ InnoDB row lock luôn tương đương đúng một hàng logic.
- Không tạo index phù hợp khiến locking read scan và khóa phạm vi rộng.
- Dùng SELECT ... FOR UPDATE cho truy vấn chỉ đọc.
- Nhầm intention lock với explicit table lock.
- Nhầm metadata lock với row lock và xử lý sai blocker.
- Dùng READ LOCAL như cơ chế concurrency cho InnoDB.
- Nhầm FLUSH TABLES WITH READ LOCK với LOCK TABLES READ.
- Tăng lock wait timeout mà không điều tra nguyên nhân.
- Không retry transaction sau deadlock theo cách có giới hạn và an toàn.

## 21. Checklist trước khi dùng LOCK TABLES

- Đã xác định lý do cần khóa ở mức bảng thay vì khóa record.
- Đã kiểm tra storage engine và phiên bản MySQL.
- Đã xác định rõ READ, READ LOCAL hay WRITE.
- Đã liệt kê tất cả bảng, alias và đối tượng được truy cập gián tiếp.
- Đã hiểu LOCK TABLES gây implicit commit trước khi lấy khóa.
- Đã kiểm tra không có DML chưa commit cần rollback.
- Đã có đường giải phóng bằng UNLOCK TABLES trong cả nhánh thành công và lỗi.
- Đã bảo đảm connection pool không tái sử dụng session còn giữ lock.
- Đã giữ thời gian khóa ngắn và có timeout/giám sát phù hợp.
- Đã phân biệt table lock, InnoDB row lock, intention lock và metadata lock.
- Đã cân nhắc SELECT ... FOR UPDATE/FOR SHARE hoặc UPDATE nguyên tử cho nghiệp vụ InnoDB.
- Đã kiểm tra index và phạm vi record có thể bị khóa.
- Đã biết cách quan sát blocker, waiter và deadlock.
- Đã kiểm tra tác động của FLUSH TABLES WITH READ LOCK nếu quy trình backup có sử dụng.
- Đã dùng SET autocommit = 0 trước LOCK TABLES nếu thật sự phải phối hợp table lock với InnoDB, và COMMIT trước UNLOCK TABLES.
- Đã thử trên sandbox với ít nhất hai session trước khi áp dụng production.

LOCK TABLES tạo khóa ở mức bảng theo session và có thể chặn rộng hơn nhiều so với khóa giao dịch của InnoDB. LOCK TABLES gây implicit commit trước khi lấy khóa; START TRANSACTION giải phóng table lock hiện có; UNLOCK TABLES có thể commit transaction nếu khóa được lấy bằng LOCK TABLES; còn ROLLBACK không tự nhả table lock. Nếu thật sự dùng LOCK TABLES với InnoDB, hãy tuân thủ trình tự SET autocommit = 0, LOCK TABLES, thao tác dữ liệu, COMMIT rồi UNLOCK TABLES. Với ứng dụng InnoDB thông thường, ưu tiên transaction ngắn, khóa record bằng SELECT ... FOR UPDATE/FOR SHARE hoặc dùng UPDATE có điều kiện nguyên tử. Chỉ dùng explicit table lock khi có nhu cầu vận hành rõ ràng, đã hiểu ranh giới commit, phạm vi khóa, cách giải phóng và tác động đến các session khác.
