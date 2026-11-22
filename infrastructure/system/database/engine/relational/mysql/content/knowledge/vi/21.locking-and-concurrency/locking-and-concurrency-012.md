# Metadata lock, giao dịch chưa kết thúc và DDL bị treo

Một DBA chạy `ALTER TABLE orders` để thêm cột mới, nhưng câu lệnh đứng ở trạng thái chờ metadata lock. Kiểm tra process list lại thấy không có câu UPDATE lớn nào đang chạy. Thủ phạm có thể là một transaction đã SELECT bảng `orders`, hoàn tất câu SELECT từ lâu nhưng chưa COMMIT hoặc ROLLBACK. Connection đó có thể đang ở trạng thái `Sleep`, song vẫn giữ metadata lock (MDL) trên bảng.

Metadata lock bảo vệ metadata của database object, chẳng hạn tên bảng, định nghĩa cột và cấu trúc bảng, trong lúc câu lệnh sử dụng object đó. MySQL dùng MDL để tránh việc DDL thay đổi cấu trúc khi transaction khác vẫn đang dùng bảng. Vì vậy, một transaction chưa kết thúc có thể chặn DDL dù hiện tại không còn câu SQL chạy trên connection đó.

Bài này giải thích vòng đời MDL, mối liên hệ với transaction dài, cách nhận diện blocker và waiter, tác động dây chuyền khi DDL xếp hàng, cùng quy trình xử lý an toàn trong production.

## 1. Metadata lock là gì?

Metadata lock (MDL) là cơ chế khóa ở tầng metadata của MySQL Server. Nó bảo vệ các đối tượng như database, table, schema object và một số object khác khỏi thay đổi cấu trúc không tương thích trong lúc đang được sử dụng.

Ví dụ:

- `SELECT` cần metadata lock để bảng không bị đổi định nghĩa giữa lúc câu lệnh đang dùng bảng.
- `INSERT`, `UPDATE`, `DELETE` cần metadata lock phù hợp khi truy cập bảng.
- `ALTER TABLE`, `DROP TABLE`, `RENAME TABLE` cần quyền metadata lock mạnh hơn để thay đổi cấu trúc hoặc tên bảng.
- Transaction có thể giữ metadata lock trên bảng đã truy cập đến khi transaction kết thúc.

MDL khác với InnoDB row lock:

| Cơ chế | Bảo vệ điều gì? | Ví dụ tình huống |
|---|---|---|
| Metadata lock (MDL) | Metadata/định nghĩa object | ALTER TABLE chờ transaction đang dùng bảng |
| Record lock (S/X) | Record/index record | UPDATE cùng một hàng phải chờ |
| Gap/next-key lock | Khoảng trong index và record liên quan | Ngăn insert phantom trong locking range scan |
| Table intention lock (IS/IX) | Báo ý định khóa record trong bảng | Phối hợp row lock với table-level lock |
| Internal latch/mutex | Cấu trúc bộ nhớ nội bộ của server/engine | Đồng bộ hoạt động nội bộ trong thời gian ngắn |

Một câu lệnh có thể đồng thời liên quan đến nhiều cơ chế. Ví dụ UPDATE có thể lấy MDL trên bảng và X lock trên record. Nếu ALTER TABLE đang chờ MDL, tăng `innodb_lock_wait_timeout` không giải quyết đúng nguyên nhân vì đây là hai loại lock khác nhau.

## 2. Vì sao SELECT thông thường cũng có thể chặn DDL?

SELECT thông thường trên InnoDB thường là consistent nonlocking read: nó không lấy S record lock trên từng hàng. Tuy nhiên, câu SELECT vẫn cần metadata lock để bảo đảm định nghĩa bảng ổn định trong lúc sử dụng.

Khi chạy trong autocommit mode, transaction của statement thường kết thúc sau khi SELECT hoàn tất và MDL theo transaction được giải phóng. Nhưng nếu SELECT nằm trong transaction tường minh, MDL trên bảng đã truy cập có thể được giữ đến COMMIT hoặc ROLLBACK.

Ví dụ session A:

    START TRANSACTION;

    SELECT id, status
    FROM orders
    WHERE id = 1001;

    -- Câu SELECT đã kết thúc.
    -- Transaction vẫn mở, chưa COMMIT/ROLLBACK.

Session B:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

Session B có thể phải chờ MDL vì session A vẫn giữ metadata lock trên `orders`. Không cần có row lock đang chặn DDL; việc transaction A chưa kết thúc đã đủ để giữ MDL.

Đây là nguyên nhân phổ biến của tình huống “DDL bị treo nhưng không thấy truy vấn dài”.

## 3. Transaction chưa kết thúc và trạng thái Sleep

Một connection có thể không chạy câu SQL nào nhưng vẫn có transaction đang mở. Trong `SHOW PROCESSLIST`, connection đó có thể hiển thị `Command = Sleep`.

Ví dụ ứng dụng:

1. Mượn connection từ pool.
2. Gửi `START TRANSACTION`.
3. Đọc bảng `orders`.
4. Xử lý dữ liệu ở tầng ứng dụng.
5. Gặp lỗi logic hoặc quên gọi COMMIT/ROLLBACK.
6. Trả connection về pool hoặc để connection nằm idle.

Nếu connection chưa thực sự đóng transaction, MDL vẫn có thể tồn tại. Việc `PROCESSLIST_INFO` là NULL hoặc `Command` là Sleep không chứng minh connection đã giải phóng lock.

### 3.1. Dấu hiệu của idle transaction

- `SHOW FULL PROCESSLIST` cho thấy connection ở trạng thái Sleep trong thời gian dài.
- `information_schema.innodb_trx` có transaction với `trx_started` cũ.
- `trx_query` có thể là NULL vì hiện không có statement đang chạy.
- `trx_mysql_thread_id` ánh xạ đến connection ID trong process list.
- `performance_schema.metadata_locks` cho thấy lock trạng thái GRANTED thuộc thread đó.

Không phải mọi connection Sleep đều giữ transaction. Cần đối chiếu `innodb_trx` và metadata lock thay vì chỉ nhìn thời gian Sleep.

## 4. Các chế độ metadata lock thường gặp

MDL có nhiều lock mode để biểu diễn mức độ truy cập object. Các mode thường gặp trong điều tra bảng gồm:

| Mode | Ý nghĩa khái quát |
|---|---|
| `SHARED_READ` | Quyền đọc metadata khi truy cập bảng, thường gặp với SELECT |
| `SHARED_WRITE` | Quyền dùng bảng cho thao tác ghi như DML |
| `SHARED_UPGRADABLE` | Lock ban đầu cho một số thao tác DDL cần nâng cấp ở giai đoạn sau |
| `SHARED_NO_WRITE` | Chế độ chia sẻ hạn chế ghi trong một số thao tác |
| `SHARED_NO_READ_WRITE` | Chế độ chia sẻ hạn chế cả đọc và ghi trong một số thao tác |
| `EXCLUSIVE` | Quyền độc quyền metadata, thường cần cho thay đổi cấu trúc |

Tên mode là thông tin chẩn đoán, không nên suy ra toàn bộ tính tương thích chỉ từ tên. Tính tương thích phụ thuộc loại object, lock mode và giai đoạn câu lệnh. Trong thực tế, điều cần tìm là:

- Lock nào đang ở `GRANTED` và giữ bởi transaction/session nào?
- Lock nào ở `PENDING` và đang chờ?
- Cả hai lock đang nhắm đến cùng object nào?
- Câu lệnh nào và transaction nào tạo ra quan hệ chờ?

`performance_schema.metadata_locks` cung cấp trạng thái lock; `sys.schema_table_lock_waits` giúp trình bày quan hệ waiter/blocker dễ đọc hơn.

## 5. Vì sao DDL cần metadata lock mạnh?

DDL như `ALTER TABLE`, `DROP TABLE` hoặc `RENAME TABLE` thay đổi metadata mà các câu lệnh khác đang sử dụng. MySQL phải bảo đảm không có transaction khác tiếp tục dùng định nghĩa cũ theo cách gây lỗi hoặc không nhất quán.

Ví dụ:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

Trước khi thay đổi định nghĩa bảng, server cần lấy metadata lock tương thích với các lock hiện có. Nếu một transaction đang giữ MDL không tương thích, DDL phải chờ.

Các lệnh thường có thể cần MDL mạnh:

- `ALTER TABLE`
- `DROP TABLE`
- `RENAME TABLE`
- `TRUNCATE TABLE`
- Một số thao tác tạo/xóa index hoặc thay đổi constraint

Mức lock và thời điểm lấy lock cụ thể tùy loại DDL, object và thuật toán thực thi.

## 6. Online DDL không có nghĩa là không cần MDL

InnoDB hỗ trợ nhiều thuật toán DDL:

- `ALGORITHM=INSTANT`: thay đổi metadata tức thời cho các thao tác được hỗ trợ.
- `ALGORITHM=INPLACE`: thực hiện thay đổi tại chỗ theo khả năng của thao tác; có thể vẫn rebuild hoặc scan dữ liệu tùy trường hợp.
- `ALGORITHM=COPY`: tạo bản sao cấu trúc/dữ liệu rồi chuyển đổi.

Một số thao tác còn hỗ trợ `LOCK=NONE`, cho phép DML đồng thời trong giai đoạn chính của DDL. Tuy nhiên:

- Không phải mọi thay đổi đều hỗ trợ INSTANT, INPLACE hoặc LOCK=NONE.
- Online DDL vẫn cần metadata lock ở các giai đoạn nhất định, đặc biệt khi bắt đầu hoặc hoàn tất chuyển đổi metadata.
- DDL có thể chờ transaction cũ kết thúc trước khi lấy được MDL cần thiết.
- Một DDL đã bắt đầu có thể vẫn cần thời gian để hoàn thành việc build index hoặc xử lý dữ liệu.

Ví dụ yêu cầu thuật toán rõ ràng:

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30),
    ALGORITHM=INSTANT;

Nếu thao tác không hỗ trợ INSTANT trên phiên bản/schema hiện tại, câu lệnh có thể báo lỗi thay vì tự động chuyển sang thuật toán khác. Việc chỉ định thuật toán giúp tránh một fallback bất ngờ có chi phí lớn.

Ví dụ với thao tác hỗ trợ online DML:

    ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;

Chỉ dùng cú pháp này khi thao tác cụ thể và phiên bản MySQL hỗ trợ. LOCK=NONE không có nghĩa MDL biến mất; nó chỉ mô tả mức độ cho phép concurrent DML trong giai đoạn được hỗ trợ.

## 7. DDL chờ có thể tạo hàng đợi truy vấn

Một tình huống vận hành nguy hiểm:

1. Transaction A giữ MDL trên `orders` vì chưa kết thúc.
2. DDL B yêu cầu `EXCLUSIVE` MDL trên `orders` và chuyển sang PENDING.
3. Các câu lệnh mới từ C, D, E tiếp tục truy cập `orders`.
4. Một số request mới có thể phải xếp hàng phía sau yêu cầu DDL đang chờ, tùy thứ tự và ưu tiên lock.
5. Connection và thread tích tụ, làm tăng latency hoặc tạo cảm giác cả ứng dụng bị treo.

Do đó, một ALTER TABLE chưa chạy được vẫn có thể gây ảnh hưởng đến traffic. Không nên chỉ nhìn DDL đang chờ mà kết luận tác động chỉ giới hạn ở một session.

Khi phát hiện DDL ở trạng thái chờ lâu, cần xác định blocker sớm. Nếu DDL chưa thể chạy trong cửa sổ hiện tại, cân nhắc hủy statement đang chờ để tránh hàng đợi tiếp tục phình ra, sau đó lên lịch lại khi transaction blocker đã được xử lý.

## 8. Quan sát metadata lock bằng Performance Schema

MySQL cung cấp bảng `performance_schema.metadata_locks` để quan sát MDL đang được giữ hoặc yêu cầu.

### 8.1. Xem metadata lock của một bảng

Ví dụ kiểm tra bảng `orders` trong database hiện tại:

    SELECT
        ml.OBJECT_TYPE,
        ml.OBJECT_SCHEMA,
        ml.OBJECT_NAME,
        ml.COLUMN_NAME,
        ml.LOCK_TYPE,
        ml.LOCK_DURATION,
        ml.LOCK_STATUS,
        ml.OWNER_THREAD_ID,
        t.PROCESSLIST_ID AS connection_id,
        t.PROCESSLIST_USER,
        t.PROCESSLIST_HOST,
        t.PROCESSLIST_COMMAND,
        t.PROCESSLIST_TIME,
        t.PROCESSLIST_STATE,
        t.PROCESSLIST_INFO
    FROM performance_schema.metadata_locks AS ml
    LEFT JOIN performance_schema.threads AS t
        ON t.THREAD_ID = ml.OWNER_THREAD_ID
    WHERE ml.OBJECT_SCHEMA = DATABASE()
      AND ml.OBJECT_NAME = 'orders'
    ORDER BY
        ml.LOCK_STATUS,
        t.PROCESSLIST_TIME DESC;

Các cột quan trọng:

| Cột | Cách đọc |
|---|---|
| `OBJECT_TYPE` | Loại object đang bị khóa |
| `OBJECT_SCHEMA`, `OBJECT_NAME` | Database và object |
| `LOCK_TYPE` | Metadata lock mode |
| `LOCK_DURATION` | Thời gian sống của lock, ví dụ TRANSACTION, STATEMENT hoặc EXPLICIT |
| `LOCK_STATUS` | `GRANTED` là đã cấp; `PENDING` là đang chờ |
| `OWNER_THREAD_ID` | Thread sở hữu yêu cầu lock |
| `PROCESSLIST_ID` | Connection ID để đối chiếu process list |
| `PROCESSLIST_INFO` | Statement hiện tại nếu connection đang chạy statement |

Một lock GRANTED có thể thuộc transaction đang idle; PROCESSLIST_INFO lúc đó có thể NULL. Một lock PENDING thường giúp nhận diện câu DDL đang chờ.

### 8.2. Tìm mọi metadata lock đang chờ

    SELECT
        OBJECT_TYPE,
        OBJECT_SCHEMA,
        OBJECT_NAME,
        LOCK_TYPE,
        LOCK_DURATION,
        OWNER_THREAD_ID
    FROM performance_schema.metadata_locks
    WHERE LOCK_STATUS = 'PENDING';

Nếu không có hàng PENDING tại thời điểm truy vấn, có thể DDL đã được cấp lock, đã kết thúc hoặc wait vừa được giải quyết. Đây là ảnh chụp trạng thái tại thời điểm chạy, không phải lịch sử lock.

### 8.3. Dùng sys.schema_table_lock_waits

MySQL có view trong sys schema giúp ghép thông tin waiter và blocker:

    SELECT *
    FROM sys.schema_table_lock_waits
    WHERE object_schema = DATABASE()
      AND object_name = 'orders';

View này thường cung cấp connection ID, account, câu lệnh đang chờ, câu lệnh/blocking connection và các cột SQL gợi ý thao tác kill. Các cột cụ thể phụ thuộc phiên bản sys schema.

Đây thường là điểm bắt đầu nhanh khi điều tra DDL bị treo. Vẫn cần xác minh blocker và tác động nghiệp vụ trước khi chạy bất kỳ câu lệnh KILL nào.

## 9. Kết hợp metadata_locks với process list và InnoDB transaction

### 9.1. Xem connection đang hoạt động

    SHOW FULL PROCESSLIST;

Chú ý:

- `Id`: connection ID.
- `User`, `Host`: danh tính và nguồn kết nối.
- `db`: database mặc định.
- `Command`: Query, Sleep hoặc trạng thái khác.
- `Time`: thời gian ở trạng thái command hiện tại.
- `State`: trạng thái đang chờ hoặc thực hiện.
- `Info`: câu SQL hiện tại, nếu có.

SHOW FULL PROCESSLIST không tự cho biết đầy đủ transaction nào đang giữ MDL. Hãy kết hợp với `metadata_locks` và `innodb_trx`.

### 9.2. Tìm transaction InnoDB lâu nhất

    SELECT
        trx_id,
        trx_state,
        trx_started,
        TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
        trx_mysql_thread_id AS connection_id,
        trx_query,
        trx_tables_locked,
        trx_rows_locked,
        trx_rows_modified
    FROM information_schema.innodb_trx
    ORDER BY trx_started;

Các dấu hiệu cần chú ý:

- Transaction bắt đầu từ lâu.
- `trx_query` là NULL nhưng transaction vẫn tồn tại.
- `trx_mysql_thread_id` ánh xạ đến connection đang Sleep.
- Số hàng hoặc bảng bị khóa lớn bất thường.

Không phải mọi MDL blocker đều phải xuất hiện như một transaction InnoDB đang hoạt động trong `innodb_trx`; MDL còn liên quan đến các statement và object khác. Vì vậy, `metadata_locks` vẫn là nguồn quan sát trực tiếp cho MDL.

### 9.3. Ánh xạ thread sang connection

`OWNER_THREAD_ID` trong Performance Schema không phải connection ID. Dùng `performance_schema.threads` để ánh xạ:

    SELECT
        THREAD_ID,
        PROCESSLIST_ID,
        PROCESSLIST_USER,
        PROCESSLIST_HOST,
        PROCESSLIST_COMMAND,
        PROCESSLIST_TIME,
        PROCESSLIST_STATE,
        PROCESSLIST_INFO
    FROM performance_schema.threads
    WHERE PROCESSLIST_ID IS NOT NULL;

Khi cần kill connection, dùng `PROCESSLIST_ID`/connection ID phù hợp, không nhầm với `THREAD_ID` hoặc `ENGINE_TRANSACTION_ID`.

## 10. Quy trình chẩn đoán DDL bị treo

Giả sử câu lệnh `ALTER TABLE orders` không hoàn tất:

**Bước 1 — Xác nhận DDL đang chờ.**

    SHOW FULL PROCESSLIST;

Tìm connection có `State` liên quan đến metadata lock hoặc câu ALTER đang chạy lâu.

**Bước 2 — Xác định object và lock đang PENDING.**

    SELECT *
    FROM performance_schema.metadata_locks
    WHERE LOCK_STATUS = 'PENDING';

Kiểm tra đúng schema/table, mode và owner thread của lock đang chờ.

**Bước 3 — Tìm lock GRANTED trên cùng object.**

Lọc `metadata_locks` theo cùng `OBJECT_TYPE`, `OBJECT_SCHEMA`, `OBJECT_NAME`, sau đó tìm lock đã GRANTED và thread sở hữu. Dùng ma trận tương thích theo mode để xác định các lock có thể chặn yêu cầu DDL.

**Bước 4 — Ánh xạ blocker về connection.**

Join `OWNER_THREAD_ID` với `performance_schema.threads`; lấy `PROCESSLIST_ID`, user, host, command và thời gian.

**Bước 5 — Kiểm tra transaction.**

Đối chiếu connection ID với `information_schema.innodb_trx`. Nếu transaction bắt đầu lâu, câu hiện tại NULL và process list là Sleep, đó có thể là idle transaction giữ MDL.

**Bước 6 — Xác minh chủ sở hữu.**

Trao đổi với ứng dụng/job đang dùng connection đó hoặc kiểm tra log/request trace để biết transaction đang làm gì. Không suy luận chỉ từ user/host vì một pool có thể phục vụ nhiều request.

**Bước 7 — Chọn cách giải phóng.**

Ưu tiên để ứng dụng COMMIT/ROLLBACK đúng quy trình. Nếu transaction bị bỏ quên và cần giải phóng khẩn cấp, đánh giá tác động trước khi kết thúc connection.

**Bước 8 — Xử lý DDL đang chờ và kiểm tra hàng đợi.**

Nếu DDL không nên tiếp tục ở thời điểm đó, hủy statement chờ bằng đúng connection ID sau khi xác minh. Sau đó kiểm tra các request đã được giải phóng và lên lịch chạy DDL lại.

## 11. KILL QUERY và KILL CONNECTION khác nhau thế nào?

MySQL có hai thao tác thường gặp:

    KILL QUERY 12345;

    KILL CONNECTION 12345;

- `KILL QUERY` dừng statement hiện tại của connection nhưng giữ connection tồn tại.
- `KILL CONNECTION` kết thúc connection; transaction đang mở của connection đó sẽ bị rollback khi server xử lý việc đóng session.

Điểm quan trọng với idle transaction:

- Nếu connection đang Sleep và không có statement chạy, KILL QUERY không giải quyết việc transaction đang mở giữ MDL.
- Để giải phóng transaction-scoped MDL của session bị bỏ quên, transaction phải COMMIT/ROLLBACK hoặc connection phải kết thúc.
- KILL CONNECTION có thể gây rollback lớn, mất công việc chưa commit và khiến ứng dụng nhận lỗi kết nối.

Không chạy câu KILL chỉ vì thấy một connection có thời gian Sleep dài. Xác nhận connection ID, transaction age, object đang bị khóa, chủ sở hữu và tác động nghiệp vụ trước.

Nếu chính DDL đang chờ làm hàng đợi truy vấn phình lên và chưa thể chạy, KILL QUERY trên connection của DDL có thể hủy yêu cầu đang chờ mà vẫn giữ connection. Sau đó xử lý blocker và lên lịch lại DDL.

## 12. DDL implicit commit và ranh giới transaction

Nhiều câu DDL như `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE` gây implicit commit. Điều đó có nghĩa transaction đang mở trong session chạy DDL có thể được commit trước khi DDL thực thi; không thể bọc ALTER TABLE trong transaction rồi kỳ vọng ROLLBACK hoàn tác cấu trúc sau đó.

Ví dụ:

    START TRANSACTION;

    UPDATE orders
    SET status = 'ARCHIVED'
    WHERE id = 1001;

    ALTER TABLE orders
    ADD COLUMN source VARCHAR(30);

    ROLLBACK;

Không nên giả định ROLLBACK cuối cùng sẽ hoàn tác cả UPDATE và ALTER. DDL có implicit commit theo quy tắc của MySQL; hãy tách thay đổi dữ liệu và schema thành các bước triển khai có ranh giới rõ ràng.

MySQL 8.0 hỗ trợ atomic DDL cho nhiều thao tác được hỗ trợ: thay đổi metadata và dữ liệu từ một DDL có thể được phục hồi nguyên tử khi server crash. Atomic DDL không có nghĩa DDL tham gia transaction người dùng hoặc có thể rollback bằng câu ROLLBACK.

## 13. Timeout liên quan đến metadata lock

MySQL có biến `lock_wait_timeout` để giới hạn thời gian chờ metadata lock. Có thể kiểm tra:

    SELECT
        @@SESSION.lock_wait_timeout,
        @@GLOBAL.lock_wait_timeout;

Đặt giới hạn riêng cho session chạy DDL:

    SET SESSION lock_wait_timeout = 30;

Nếu không lấy được MDL trong thời gian cấu hình, statement có thể trả lỗi timeout thay vì chờ vô hạn hoặc quá lâu. Giá trị cụ thể nên được chọn theo cửa sổ triển khai và mức độ chấp nhận chờ của hệ thống.

Phân biệt với:

    SELECT @@SESSION.innodb_lock_wait_timeout;

`innodb_lock_wait_timeout` kiểm soát thời gian chờ InnoDB row lock; `lock_wait_timeout` kiểm soát metadata lock wait. Thay đổi biến sai loại sẽ không giải quyết đúng nguồn chờ.

Timeout chỉ giới hạn thời gian chờ của session yêu cầu lock. Nó không tự giải phóng transaction blocker và không sửa nguyên nhân khiến blocker giữ MDL.

## 14. Phòng tránh transaction dài giữ MDL

### 14.1. Luôn kết thúc transaction

Mọi luồng ứng dụng cần bảo đảm COMMIT hoặc ROLLBACK trong mọi nhánh thành công/lỗi. Với JDBC, dùng transaction boundary rõ ràng và `try/finally` để không trả connection về pool khi transaction chưa kết thúc.

Ví dụ logic:

    connection.setAutoCommit(false);
    try {
        // Thực hiện các câu SQL cần transaction.
        connection.commit();
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        // Chỉ trả connection về pool sau khi transaction đã được dọn.
    }

Đây là pseudocode minh họa. Trong code thật, cần xử lý cả lỗi khi rollback và khôi phục trạng thái connection theo contract của pool/driver.

### 14.2. Không giữ transaction trong lúc chờ bên ngoài

Tránh:

1. Mở transaction.
2. SELECT bảng.
3. Gọi HTTP service hoặc chờ người dùng.
4. Xử lý file lớn.
5. Sau vài phút mới COMMIT.

Các bước ngoài database kéo dài thời gian giữ MDL và có thể giữ thêm row lock, undo history hoặc connection pool slot. Hãy thu thập dữ liệu cần thiết, kết thúc transaction sớm, rồi thực hiện công việc ngoài database nếu nghiệp vụ cho phép.

### 14.3. Theo dõi idle-in-transaction

Thiết lập cảnh báo cho transaction vượt tuổi tối đa theo workload. Theo dõi:

- Transaction age.
- Connection Sleep nhưng vẫn có transaction.
- Số lượng bảng/row lock đang giữ.
- Metadata lock GRANTED tồn tại lâu.
- DDL lock PENDING.
- Connection pool trả connection về khi chưa reset transaction.

Không đặt ngưỡng duy nhất cho mọi workload; một transaction báo cáo dài có thể hợp lệ nhưng cần được thiết kế để không chặn DDL hoặc OLTP quan trọng.

## 15. Lập kế hoạch chạy DDL an toàn

Trước khi chạy migration:

1. Xác định bảng, loại thay đổi và thuật toán DDL có hỗ trợ.
2. Kiểm tra transaction lâu và metadata lock đang tồn tại.
3. Chọn cửa sổ ít tải hoặc triển khai theo chiến lược online phù hợp.
4. Đặt `lock_wait_timeout` hợp lý cho session migration.
5. Theo dõi process list, metadata locks và replication trong lúc chạy.
6. Nếu DDL chờ lâu, tìm blocker thay vì liên tục mở thêm session chạy lại cùng ALTER.
7. Nếu phải hủy, xác nhận trạng thái DDL và schema trước khi thử lại.
8. Sau khi hoàn tất, xác minh schema và kiểm tra ứng dụng.

Không nên khởi chạy nhiều ALTER TABLE giống nhau đồng thời trên cùng bảng. Nhiều yêu cầu MDL chờ có thể làm hàng đợi phức tạp hơn và gây thêm tải.

## 16. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| SELECT thường không khóa nên không thể chặn DDL | SELECT vẫn lấy MDL; transaction tường minh có thể giữ lock sau khi statement kết thúc |
| Connection Sleep không giữ lock | Idle transaction có thể giữ MDL và row lock |
| DDL bị treo chắc chắn do InnoDB row lock | DDL có thể đang chờ metadata lock, là cơ chế khác |
| Online DDL không cần lock | Online/INSTANT DDL vẫn cần MDL ở các giai đoạn nhất định |
| LOCK=NONE nghĩa là không có lock nào | Nó nói về concurrent DML được hỗ trợ, không loại bỏ MDL |
| Tăng innodb_lock_wait_timeout sẽ sửa DDL wait | Metadata lock wait dùng lock_wait_timeout |
| KILL QUERY luôn giải phóng transaction | Nó chỉ dừng statement hiện tại; transaction idle có thể vẫn mở |
| ROLLBACK hoàn tác ALTER TABLE | DDL thường gây implicit commit và không thuộc transaction rollback của người dùng |
| PROCESSLIST_INFO = NULL nghĩa là connection không giữ gì | Connection Sleep có thể vẫn sở hữu transaction và MDL |
| Atomic DDL nghĩa là DDL transactional với ứng dụng | Atomic DDL bảo đảm phục hồi DDL khi crash, không biến DDL thành thao tác rollback được |

## 17. Checklist điều tra metadata lock và DDL bị treo

- DDL đang chờ trên object nào, schema nào?
- Có lock PENDING trong `performance_schema.metadata_locks` không?
- Thread nào sở hữu lock PENDING và connection ID tương ứng là gì?
- Những lock GRANTED nào trên cùng object không tương thích với yêu cầu đang chờ?
- Blocker có phải connection Sleep nhưng vẫn có transaction trong `innodb_trx` không?
- Transaction bắt đầu từ khi nào, đã truy cập bảng nào và thuộc ứng dụng/job nào?
- Có DDL khác đang chờ trước đó khiến request mới xếp hàng không?
- Có thể yêu cầu ứng dụng COMMIT/ROLLBACK an toàn không?
- Nếu phải KILL, đã hiểu khác biệt giữa KILL QUERY và KILL CONNECTION chưa?
- DDL có hỗ trợ ALGORITHM/LOCK đã chọn trên phiên bản hiện tại không?
- `lock_wait_timeout` có được cấu hình phù hợp cho migration session không?
- Sau khi giải phóng blocker, hàng đợi đã thông và DDL hoàn tất chưa?

## Kết luận

Metadata lock bảo vệ định nghĩa object trong lúc MySQL sử dụng hoặc thay đổi bảng. Một SELECT thông thường không cần S record lock nhưng vẫn lấy MDL; nếu nó chạy trong transaction chưa kết thúc, MDL có thể tồn tại sau khi câu SELECT hoàn tất và chặn ALTER TABLE. Connection Sleep vì thế vẫn có thể là blocker. Hãy tìm lock PENDING/GRANTED trong `performance_schema.metadata_locks`, dùng `sys.schema_table_lock_waits`, process list và `innodb_trx` để ánh xạ waiter/blocker. Phân biệt `lock_wait_timeout` với `innodb_lock_wait_timeout`, hiểu rằng online DDL vẫn cần MDL, và chỉ kết thúc connection sau khi đánh giá tác động rollback. Quản lý transaction ngắn, giải phóng connection đúng cách và lập kế hoạch DDL theo trạng thái lock giúp tránh tình trạng migration treo và hàng đợi truy vấn dây chuyền.
