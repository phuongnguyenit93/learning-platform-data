# Shared lock, exclusive lock và intention lock

Khi hai nhân viên cùng xử lý một đơn hàng hoặc hai giao dịch cùng cập nhật số lượng tồn kho, MySQL phải điều phối quyền truy cập để dữ liệu không bị ghi đè ngoài ý muốn. InnoDB thực hiện điều này bằng nhiều loại lock. Ba khái niệm nền tảng là shared lock (S), exclusive lock (X) và intention lock (IS/IX).

Shared lock cho phép nhiều transaction cùng đọc một bản ghi theo chế độ khóa, nhưng ngăn transaction khác sửa bản ghi đó. Exclusive lock dành quyền ghi độc quyền trên bản ghi và xung đột với cả shared lock lẫn exclusive lock khác. Intention lock được đặt ở cấp bảng để báo rằng transaction đang hoặc sẽ khóa các bản ghi bên trong bảng; nó giúp phối hợp khóa hàng với khóa bảng.

Hiểu đúng phạm vi và tính tương thích của từng lock giúp thiết kế transaction an toàn, giảm deadlock và điều tra tình trạng chờ khóa trong hệ thống MySQL.

## 1. Lock trong InnoDB giải quyết vấn đề gì?

Một transaction có thể đọc hoặc thay đổi dữ liệu trong khi transaction khác cũng đang truy cập cùng dữ liệu. Nếu không có cơ chế điều phối, có thể xảy ra:

- Hai giao dịch cùng trừ tồn kho và làm số lượng âm.
- Một giao dịch đọc trạng thái rồi quyết định cập nhật trong khi giao dịch khác đã thay đổi trạng thái.
- Một giao dịch đọc hàng để xử lý, nhưng hàng bị xóa trước khi giao dịch đầu hoàn tất.
- Các giao dịch ghi đè thay đổi của nhau hoặc vi phạm quy tắc nghiệp vụ.

InnoDB kết hợp MVCC (Multi-Version Concurrency Control) và locking. MVCC giúp nhiều consistent read đọc phiên bản phù hợp mà không phải khóa hàng theo shared lock. Lock được dùng khi cần bảo vệ dữ liệu trong thao tác ghi hoặc locking read.

Các lock S, X, IS và IX trong bài này thuộc cơ chế khóa của InnoDB. Chúng khác với metadata lock (MDL) dùng để bảo vệ cấu trúc bảng trong lúc chạy DDL và khác với mutex/latch nội bộ bảo vệ cấu trúc bộ nhớ của engine.

## 2. Shared lock (S lock)

Shared lock, thường ký hiệu S, là khóa chia sẻ trên bản ghi/index record. Nhiều transaction có thể cùng giữ S lock trên cùng một record. Khi một transaction giữ S lock, transaction khác không thể lấy X lock trên record đó cho đến khi các S lock được giải phóng.

Có thể hiểu:

- Nhiều transaction được cùng giữ S lock trên một record.
- S lock ngăn transaction khác sửa hoặc khóa độc quyền cùng record.
- Transaction đang giữ S lock vẫn có thể đọc giá trị đã khóa.
- S lock thường được dùng khi cần đọc một hàng và bảo đảm hàng đó không bị transaction khác cập nhật trước khi transaction hiện tại kết thúc.

### 2.1. Tạo shared lock bằng SELECT ... FOR SHARE

MySQL 8.0 hỗ trợ cú pháp:

    START TRANSACTION;

    SELECT id, status, total_amount
    FROM orders
    WHERE id = 1001
    FOR SHARE;

    -- Thực hiện các bước đọc/kiểm tra liên quan.

    COMMIT;

FOR SHARE yêu cầu shared lock trên các index record được đọc theo kế hoạch thực thi; phạm vi thực tế có thể rộng hơn các hàng cuối cùng xuất hiện trong kết quả nếu engine phải quét thêm record hoặc range. Lock được giữ đến khi transaction commit hoặc rollback. Một transaction khác có thể cũng chạy FOR SHARE trên cùng record; nhưng UPDATE hoặc SELECT ... FOR UPDATE phải chờ khi S lock còn tồn tại.

Cú pháp LOCK IN SHARE MODE cũ vẫn được hỗ trợ trong MySQL 8.0 nhưng đã deprecated; FOR SHARE là cú pháp được khuyến nghị cho locking read hiện đại.

### 2.2. Hai transaction cùng đọc bằng shared lock

Giả sử hai session A và B cùng chạy:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Cả A và B có thể lấy S lock trên cùng record. Không session nào phải chờ session kia chỉ vì cả hai cùng xin S lock. Nếu session C chạy:

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

Câu UPDATE cần X lock và phải chờ cho đến khi các S lock được giải phóng.

### 2.3. Khi nào nên dùng shared lock?

Dùng FOR SHARE khi transaction cần đọc một giá trị và dựa vào giá trị đó trong một quy trình nhiều bước, đồng thời cần ngăn transaction khác sửa record trước khi quy trình kết thúc.

Ví dụ, quy trình xác minh một cấu hình trước khi tạo bản ghi phụ thuộc có thể cần giữ trạng thái cấu hình ổn định trong transaction. Tuy nhiên, không nên dùng S lock cho mọi SELECT. Nếu chỉ cần đọc dữ liệu nhất quán, consistent read của InnoDB thường đủ và ít gây tranh chấp hơn.

## 3. Exclusive lock (X lock)

Exclusive lock, ký hiệu X, là khóa độc quyền trên record. Khi một transaction giữ X lock:

- Transaction khác không thể lấy S lock trên cùng record.
- Transaction khác không thể lấy X lock trên cùng record.
- Transaction đang giữ X lock có thể đọc và sửa record theo transaction của nó.
- X lock được giữ đến khi transaction commit hoặc rollback.

### 3.1. DML tự lấy exclusive lock

Các câu lệnh thay đổi dữ liệu như UPDATE, DELETE và INSERT cần khóa phù hợp để bảo vệ thay đổi. Ví dụ:

    START TRANSACTION;

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

    -- Các bước nghiệp vụ tiếp theo.

    COMMIT;

InnoDB lấy X lock trên các record/index record cần sửa. Transaction khác muốn lấy S hoặc X lock trên cùng record phải chờ.

### 3.2. SELECT ... FOR UPDATE

Nếu cần đọc dữ liệu rồi quyết định cập nhật, có thể lấy X lock ngay ở bước đọc:

    START TRANSACTION;

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Kiểm tra quantity trong ứng dụng hoặc stored routine.
    -- Cập nhật nếu đủ điều kiện.

    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 42;

    COMMIT;

FOR UPDATE là locking read yêu cầu exclusive lock trên các record được truy cập. Nó ngăn transaction khác sửa hoặc lấy shared lock trên các record đó trong khi transaction hiện tại đang giữ khóa.

Khi biết chắc transaction sẽ đọc rồi sửa cùng một record, FOR UPDATE thường phù hợp hơn việc lấy FOR SHARE rồi nâng cấp lên X lock. Nâng cấp lock từ S sang X ở nhiều transaction cùng lúc có thể tạo deadlock.

### 3.3. X lock không có nghĩa là khóa toàn bảng

Trong InnoDB, X lock thường khóa record/index record cần thiết, không tự động khóa toàn bộ bảng. Một UPDATE theo primary key có thể chỉ khóa một record, trong khi UPDATE theo điều kiện range có thể khóa nhiều record hoặc khoảng index tùy isolation level và execution plan.

Vì vậy, không thể chỉ nhìn câu lệnh UPDATE rồi kết luận phạm vi lock. Cần xét index được dùng, số record bị quét, điều kiện range và loại lock mà InnoDB đặt.

## 4. Tính tương thích giữa S và X trên cùng record

Ma trận dưới đây mô tả khả năng một lock mới được cấp khi transaction khác đã giữ lock trên cùng record:

| Lock đang được giữ | Yêu cầu S mới | Yêu cầu X mới |
|---|---:|---:|
| S | Cho phép | Chờ |
| X | Chờ | Chờ |

Diễn giải:

- S với S tương thích: nhiều transaction có thể cùng đọc có khóa.
- S với X không tương thích: X phải chờ S được giải phóng.
- X với S không tương thích: S phải chờ X được giải phóng.
- X với X không tương thích: chỉ một transaction được giữ X lock trên record tại một thời điểm.

Lock được giải phóng khi transaction kết thúc bằng COMMIT hoặc ROLLBACK. Không nên giả định lock biến mất ngay sau câu SELECT/UPDATE nếu transaction vẫn đang mở.

## 5. Intention lock là gì?

Intention lock là khóa ở cấp bảng cho biết transaction dự định hoặc đang giữ row lock ở bên trong bảng. InnoDB sử dụng hai loại chính:

- **IS (Intention Shared):** transaction dự định lấy hoặc đang giữ S lock trên record trong bảng.
- **IX (Intention Exclusive):** transaction dự định lấy hoặc đang giữ X lock trên record trong bảng.

Trước khi lấy S lock trên record, InnoDB đặt IS lock ở cấp bảng. Trước khi lấy X lock trên record, InnoDB đặt IX lock ở cấp bảng.

Intention lock không khóa toàn bộ hàng trong bảng. Nó là tín hiệu phối hợp giữa cơ chế row-level lock và các thao tác muốn lấy table-level lock.

### 5.1. Ví dụ IS

Transaction A:

    START TRANSACTION;

    SELECT *
    FROM orders
    WHERE id = 1001
    FOR SHARE;

InnoDB đặt IS ở cấp bảng orders và S lock trên record tương ứng. IS báo rằng transaction A đang dùng shared row lock bên trong bảng.

### 5.2. Ví dụ IX

Transaction B:

    START TRANSACTION;

    UPDATE orders
    SET status = 'PROCESSING'
    WHERE id = 1001;

InnoDB đặt IX ở cấp bảng orders và X lock trên record cần sửa. IX báo rằng transaction B đang dùng exclusive row lock bên trong bảng.

Nhiều transaction có thể cùng giữ IX trên một bảng nếu chúng khóa các record khác nhau. Điều này cho phép InnoDB duy trì concurrency ở cấp hàng thay vì buộc mọi thao tác ghi phải khóa độc quyền toàn bảng.

## 6. Ma trận tương thích của IS, IX, S và X ở cấp bảng

Ở cấp bảng, các chế độ intention phối hợp với table-level S/X lock như sau:

| Lock đang được giữ | Yêu cầu IS | Yêu cầu IX | Yêu cầu S | Yêu cầu X |
|---|---:|---:|---:|---:|
| IS | Cho phép | Cho phép | Cho phép | Chờ |
| IX | Cho phép | Cho phép | Chờ | Chờ |
| S | Cho phép | Chờ | Cho phép | Chờ |
| X | Chờ | Chờ | Chờ | Chờ |

Các điểm quan trọng:

- IS và IX tương thích với nhau. Nhiều transaction có thể cùng báo ý định khóa record.
- Table-level S lock tương thích với IS vì shared table lock có thể cùng tồn tại với shared row locks.
- Table-level S lock xung đột với IX vì IX báo có transaction đang cần exclusive row lock.
- Table-level X lock xung đột với mọi intention lock và table lock khác.

Ma trận này áp dụng cho các table-level lock modes của InnoDB. Nó không có nghĩa một câu SELECT thông thường sẽ lấy table-level S lock; consistent read thông thường không lấy S row lock.

## 7. Vì sao cần intention lock?

Hãy tưởng tượng transaction A đang giữ X lock trên một record trong bảng orders. Transaction B yêu cầu table-level S lock trên toàn bảng. Nếu không có intention lock, engine phải kiểm tra từng record để biết có X row lock nào đang tồn tại hay không.

Với IX, InnoDB đã có tín hiệu rằng transaction A đang giữ hoặc sẽ giữ X lock bên trong bảng. Yêu cầu table-level S của B xung đột với IX và phải chờ. Cơ chế này giúp kiểm tra tương thích ở cấp bảng hiệu quả hơn mà không phải quét mọi row lock.

Intention lock chủ yếu được engine tự động quản lý. Ứng dụng thường không cần tự phát hành câu lệnh để đặt IS hoặc IX.

## 8. Phân biệt intention lock với row lock và table lock

| Loại lock | Phạm vi | Ý nghĩa |
|---|---|---|
| S record lock | Record/index record | Cho phép nhiều transaction đọc có khóa, chặn X lock khác |
| X record lock | Record/index record | Độc quyền trên record, chặn S/X lock khác |
| IS intention lock | Bảng | Báo transaction có S row lock hoặc dự định lấy S row lock |
| IX intention lock | Bảng | Báo transaction có X row lock hoặc dự định lấy X row lock |
| Table-level S/X | Bảng | Khóa ở phạm vi bảng, phối hợp qua ma trận tương thích |
| Metadata lock (MDL) | Metadata object | Bảo vệ định nghĩa bảng trong lúc truy cập/DDL |

Không đồng nhất IS/IX với table-level S/X. IX không có nghĩa transaction đã khóa độc quyền toàn bộ bảng; nó chỉ báo ý định khóa độc quyền ở cấp record.

## 9. Consistent read và locking read

Một SELECT thông thường trên InnoDB thường là consistent nonlocking read. Nó đọc snapshot theo isolation level và không lấy S lock trên từng record chỉ vì câu lệnh đang đọc.

Ví dụ:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42;

Ở REPEATABLE READ, các consistent read trong cùng transaction thường dùng cùng read view được thiết lập từ lần consistent read đầu tiên. Ở READ COMMITTED, mỗi consistent read có thể tạo read view mới theo statement.

Ngược lại:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

và:

    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

là locking read. Chúng yêu cầu S hoặc X lock tương ứng trên record được truy cập. Locking read đọc phiên bản hiện hành phù hợp với locking semantics thay vì chỉ đọc snapshot cũ như consistent read.

Chọn consistent read khi chỉ cần đọc dữ liệu nhất quán. Chọn locking read khi transaction cần bảo vệ record khỏi thay đổi cạnh tranh trong một quy trình nhiều bước.

## 10. Locking read phải nằm trong transaction phù hợp

Locking read có ích khi khóa được giữ trong lúc ứng dụng thực hiện các bước liên quan. Ví dụ:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Kiểm tra số lượng và ghi nhận đơn hàng.

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42;

    COMMIT;

Nếu chạy locking read trong autocommit mode mà không mở transaction tường minh, transaction của statement kết thúc ngay khi câu SELECT kết thúc; lock không còn bảo vệ các câu lệnh chạy sau đó. Vì vậy, khi cần giữ lock qua nhiều câu lệnh, phải mở transaction và commit/rollback đúng lúc.

Giữ transaction càng ngắn càng tốt. Không gọi dịch vụ HTTP, chờ người dùng hoặc thực hiện công việc tốn thời gian trong khi vẫn giữ row lock.

## 11. Kịch bản tương tác giữa hai session

### 11.1. S và S có thể cùng tồn tại

Session A:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Session B:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

Cả hai có thể lấy S lock. Nếu session C chạy UPDATE trên record đó, C phải chờ.

### 11.2. X chặn cả S và X

Session A:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

Session B:

    START TRANSACTION;
    SELECT quantity
    FROM inventory
    WHERE product_id = 42
    FOR SHARE;

B phải chờ A commit hoặc rollback. Nếu B yêu cầu FOR UPDATE, B cũng phải chờ vì X và X xung đột.

### 11.3. Hai transaction cùng nâng cấp S thành X

Session A và B đều lấy FOR SHARE trên cùng record, sau đó cả hai muốn UPDATE. Mỗi transaction đang giữ S và chờ X; X lại không tương thích với S của transaction còn lại. InnoDB có thể phát hiện deadlock và rollback một transaction.

Nếu biết chắc cần sửa record, hãy lấy FOR UPDATE ngay từ đầu thay vì lấy FOR SHARE rồi nâng cấp. Điều này giảm nguy cơ lock conversion deadlock.

## 12. Deadlock và lock wait

### 12.1. Lock wait

Lock wait xảy ra khi transaction yêu cầu lock không tương thích với lock hiện có. Transaction yêu cầu phải chờ đến khi lock được giải phóng hoặc timeout.

Có thể gặp lỗi lock wait timeout khi transaction khác giữ khóa quá lâu. Ứng dụng nên rollback transaction theo chính sách rõ ràng, ghi log và retry có giới hạn nếu thao tác có thể retry an toàn.

### 12.2. Deadlock

Deadlock xảy ra khi các transaction chờ lẫn nhau theo một vòng phụ thuộc. Ví dụ:

1. A giữ X lock trên hàng 1.
2. B giữ X lock trên hàng 2.
3. A yêu cầu X lock trên hàng 2 và phải chờ B.
4. B yêu cầu X lock trên hàng 1 và phải chờ A.

InnoDB phát hiện vòng chờ và chọn một transaction làm deadlock victim để rollback. Ứng dụng cần retry toàn bộ transaction victim, không chỉ chạy lại statement cuối cùng.

### 12.3. Giảm deadlock

- Truy cập các bảng và record theo cùng thứ tự giữa các transaction.
- Giữ transaction ngắn.
- Dùng index phù hợp để giảm số record/range bị quét và khóa.
- Chỉ khóa các hàng thực sự cần thiết.
- Dùng FOR UPDATE ngay từ đầu khi chắc chắn sẽ sửa.
- Retry deadlock với backoff ngẫu nhiên và giới hạn số lần.
- Ghi lại transaction, câu SQL và khóa liên quan để tìm nguyên nhân gốc.

## 13. NOWAIT và SKIP LOCKED

MySQL 8.0.1 trở lên hỗ trợ tùy chọn cho locking read:

- NOWAIT: nếu record cần khóa đang bị transaction khác khóa, câu lệnh trả lỗi ngay thay vì chờ.
- SKIP LOCKED: bỏ qua các record đang bị khóa và trả các record khác có thể lấy khóa.

Ví dụ NOWAIT:

    START TRANSACTION;

    SELECT *
    FROM jobs
    WHERE id = 10
    FOR UPDATE NOWAIT;

Ví dụ SKIP LOCKED:

    START TRANSACTION;

    SELECT id
    FROM jobs
    WHERE status = 'READY'
    ORDER BY id
    LIMIT 10
    FOR UPDATE SKIP LOCKED;

SKIP LOCKED hữu ích cho nhiều worker cùng lấy việc từ queue, nhưng kết quả không phải một view đầy đủ nhất quán của tất cả hàng phù hợp: các hàng đang bị khóa bị bỏ qua. Ứng dụng phải có trạng thái claim, lease và cơ chế phục hồi job bị worker bỏ dở. Không dùng SKIP LOCKED nếu nghiệp vụ yêu cầu đọc đủ mọi hàng phù hợp.

## 14. Phạm vi lock phụ thuộc index và isolation level

InnoDB khóa index record, không chỉ khái niệm hàng ở tầng ứng dụng. Với truy vấn tìm đúng một primary key, phạm vi lock thường hẹp. Với điều kiện range, engine có thể khóa nhiều index record và khoảng giữa các record.

Ví dụ:

    START TRANSACTION;

    SELECT *
    FROM orders
    WHERE customer_id = 120
      AND created_at >= '2026-01-01'
    FOR UPDATE;

Nếu index phù hợp không tồn tại, MySQL có thể phải quét nhiều record hơn và lock footprint có thể rộng hơn dự kiến. Index bắt đầu bằng các cột lọc/nối phù hợp giúp giới hạn vùng truy cập.

Ở REPEATABLE READ, InnoDB thường dùng next-key lock cho nhiều locking search/range scan để ngăn phantom trong phạm vi được khóa. Next-key lock kết hợp record lock với gap lock trên khoảng index. Ở READ COMMITTED, gap locking thường được giảm cho locking search/index scan, ngoại trừ các trường hợp như kiểm tra foreign key và duplicate key. Chi tiết phụ thuộc câu lệnh, index và execution plan.

Không nhầm gap lock/next-key lock với S/X record lock thuần túy. Chúng là các dạng khóa phạm vi liên quan đến index gap, cần xem xét khi phân tích insert bị chặn hoặc locking range query.

## 15. Foreign key và unique check cũng có thể tạo lock

Khi insert/update hàng con, InnoDB cần kiểm tra hàng cha được tham chiếu có tồn tại hay không. Việc kiểm tra foreign key có thể yêu cầu lock trên record được tham chiếu để bảo đảm tính toàn vẹn trong lúc thao tác.

Khi insert hàng có unique index, engine phải kiểm tra duplicate. Kiểm tra này cũng có thể tương tác với lock và khiến transaction chờ một transaction khác đang tạo hoặc xóa giá trị xung đột.

Do đó, một câu INSERT đơn giản vẫn có thể chờ khóa dù ứng dụng không viết FOR UPDATE. Khi điều tra, xem cả foreign key, unique index và transaction cạnh tranh chứ không chỉ các locking read tường minh.

## 16. Quan sát lock bằng Performance Schema

MySQL 8.0 cung cấp các bảng Performance Schema để quan sát lock dữ liệu:

- performance_schema.data_locks: các lock đang được giữ hoặc yêu cầu.
- performance_schema.data_lock_waits: quan hệ giữa lock đang chờ và lock đang chặn.
- performance_schema.threads: ánh xạ thread với connection/processlist ID.

Xem lock:

    SELECT
        ENGINE_TRANSACTION_ID,
        THREAD_ID,
        OBJECT_SCHEMA,
        OBJECT_NAME,
        INDEX_NAME,
        LOCK_TYPE,
        LOCK_MODE,
        LOCK_STATUS,
        LOCK_DATA
    FROM performance_schema.data_locks;

Xem quan hệ chờ:

    SELECT
        waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
        waiting.OBJECT_SCHEMA,
        waiting.OBJECT_NAME,
        waiting.INDEX_NAME,
        waiting.LOCK_MODE AS waiting_lock_mode,
        blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
        blocking.LOCK_MODE AS blocking_lock_mode
    FROM performance_schema.data_lock_waits AS waits
    JOIN performance_schema.data_locks AS waiting
      ON waiting.ENGINE = waits.ENGINE
     AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
    JOIN performance_schema.data_locks AS blocking
      ON blocking.ENGINE = waits.ENGINE
     AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;

Các bảng này yêu cầu Performance Schema hoạt động và tài khoản có quyền xem dữ liệu cần thiết. LOCK_MODE có thể thể hiện các mode như S, X, IS, IX hoặc biến thể liên quan đến gap/record. Hãy đọc cùng OBJECT_NAME, INDEX_NAME, LOCK_TYPE và LOCK_DATA để hiểu phạm vi thực tế.

Có thể xem trạng thái transaction đang chạy:

    SELECT *
    FROM information_schema.innodb_trx;

Kết hợp transaction age, connection ID và truy vấn đang chạy để tìm session giữ lock lâu. Không kill connection chỉ dựa vào một dòng lock; cần xác định đúng transaction, chủ sở hữu nghiệp vụ và tác động rollback trước khi thao tác.

## 17. Ví dụ nghiệp vụ: trừ tồn kho an toàn

Giả sử bảng:

    CREATE TABLE inventory (
        product_id BIGINT UNSIGNED NOT NULL,
        available_quantity INT NOT NULL,
        PRIMARY KEY (product_id),
        CONSTRAINT chk_inventory_nonnegative
            CHECK (available_quantity >= 0)
    ) ENGINE=InnoDB;

CHECK constraint được MySQL thực thi từ phiên bản 8.0.16. Nếu chạy phiên bản cũ hơn, không được giả định điều kiện CHECK ở ví dụ sẽ bảo vệ dữ liệu; cần dùng phiên bản hỗ trợ hoặc cơ chế kiểm tra khác.

Có thể dùng UPDATE có điều kiện để trừ tồn:

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42
      AND available_quantity >= 2;

Sau câu lệnh, ứng dụng kiểm tra affected rows. Nếu bằng 1, đã trừ được số lượng yêu cầu. Nếu bằng 0, có thể sản phẩm không tồn tại hoặc không đủ tồn kho; cần xác định thêm theo yêu cầu nghiệp vụ.

Nếu cần đọc số lượng trước để tính toán nhiều bước, dùng transaction và FOR UPDATE:

    START TRANSACTION;

    SELECT available_quantity
    FROM inventory
    WHERE product_id = 42
    FOR UPDATE;

    -- Chỉ tiếp tục khi số lượng đủ.

    UPDATE inventory
    SET available_quantity = available_quantity - 2
    WHERE product_id = 42;

    COMMIT;

Hai cách có mục tiêu hơi khác nhau. UPDATE có điều kiện thường ngắn và giảm khoảng thời gian giữ lock. FOR UPDATE phù hợp khi cần đọc và ra quyết định dựa trên giá trị được khóa trong nhiều bước. Không nên đọc bằng SELECT thường, kiểm tra trong ứng dụng rồi UPDATE vô điều kiện vì giữa hai câu lệnh có thể có transaction khác thay đổi tồn kho.

## 18. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Shared lock chặn mọi transaction khác | Shared lock tương thích với shared lock khác trên cùng record |
| Exclusive lock chỉ chặn ghi | X lock xung đột cả S và X lock khác trên cùng record |
| IX là khóa độc quyền toàn bảng | IX chỉ báo ý định lấy X row lock bên trong bảng |
| IS/IX ngăn các transaction khác khóa hàng | IS/IX thường tương thích với intention lock khác; chúng phối hợp với table-level lock |
| SELECT thông thường luôn lấy S lock | InnoDB thường dùng consistent nonlocking read cho SELECT thông thường |
| UPDATE luôn khóa toàn bảng | Phạm vi lock phụ thuộc index, điều kiện và execution plan |
| Locking read tự giữ lock qua nhiều request | Lock tồn tại theo transaction/connection và được giải phóng khi transaction kết thúc |
| COMMIT không ảnh hưởng row lock | COMMIT/ROLLBACK giải phóng lock của transaction |
| FOR SHARE và FOR UPDATE giống SELECT thường | Chúng là locking read, có thể tạo S/X lock và chặn transaction khác |
| Foreign key bảo đảm cây không có chu trình | Foreign key kiểm tra tham chiếu tồn tại, không kiểm tra quan hệ không vòng |

## 19. Checklist khi thiết kế transaction và điều tra lock

- Chỉ cần consistent read hay cần locking read?
- Nếu cần sửa, có thể dùng FOR UPDATE ngay từ đầu không?
- Transaction có được mở tường minh và kết thúc sớm không?
- Các transaction có truy cập bảng/record theo cùng thứ tự không?
- Index có giới hạn số record và range phải quét không?
- Có nhầm IS/IX với table-level S/X không?
- Có transaction nào giữ lock quá lâu hoặc chờ dịch vụ bên ngoài không?
- Có gap/next-key lock do range scan và isolation level không?
- Foreign key hoặc unique check có thể là nguồn gây chờ không?
- NOWAIT/SKIP LOCKED có phù hợp ngữ nghĩa nghiệp vụ không?
- Có theo dõi data_locks, data_lock_waits và innodb_trx khi điều tra không?
- Ứng dụng có rollback transaction rõ ràng và retry deadlock có giới hạn không?

## Kết luận

Shared lock (S) cho phép nhiều transaction cùng đọc có khóa trên một record nhưng chặn X lock. Exclusive lock (X) độc quyền trên record và xung đột với cả S/X khác. Intention lock IS/IX được đặt ở cấp bảng để báo transaction sẽ khóa record bên trong; chúng giúp InnoDB phối hợp row lock với table-level lock mà không biến mọi thao tác thành khóa toàn bảng. SELECT thông thường thường là consistent read không khóa; FOR SHARE và FOR UPDATE là locking read và cần transaction được quản lý đúng. Phạm vi lock còn phụ thuộc index, isolation level, range scan, foreign key và unique check. Nắm được các quy tắc này giúp giảm tranh chấp, tránh deadlock và chẩn đoán concurrency trong MySQL chính xác hơn.
