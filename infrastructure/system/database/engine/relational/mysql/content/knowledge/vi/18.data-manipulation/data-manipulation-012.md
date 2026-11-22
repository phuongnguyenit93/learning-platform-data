# Chia lô theo khóa ổn định và tránh giao dịch quá lớn

Một bảng lịch sử đơn hàng có thể chứa hàng chục triệu dòng. Khi cần chuyển trạng thái dữ liệu cũ, xóa log hết hạn hoặc chuẩn hóa một cột, chạy một câu UPDATE/DELETE cho toàn bộ bảng có thể tạo transaction rất lớn, giữ lock lâu, sinh nhiều undo/redo, tăng tải I/O và khiến replica tụt phía sau. Nếu tiến trình bị ngắt giữa chừng, việc khởi động lại cũng khó xác định phần nào đã hoàn tất.

Giải pháp thường dùng là chia công việc thành các batch nhỏ theo một khóa ổn định. Mỗi batch xử lý một khoảng khóa hoặc một tập ID xác định, commit độc lập rồi lưu checkpoint để lần chạy sau tiếp tục. Cách này giảm thời gian giữ lock và giới hạn lượng công việc phải retry. Đổi lại, toàn bộ job không còn là một transaction nguyên tử duy nhất; cần thiết kế tính idempotent, checkpoint và đối soát để xử lý lỗi giữa các batch.

## 1. Vì sao không nên xử lý hàng triệu dòng trong một transaction?

Với InnoDB, transaction lớn có thể gây nhiều áp lực:

- **Lock tồn tại lâu:** các transaction khác phải chờ khi đụng đến hàng hoặc khoảng index đang bị khóa.
- **Undo log tăng:** InnoDB giữ phiên bản cũ để rollback và phục vụ consistent read; transaction dài có thể làm purge không dọn được lịch sử cũ.
- **Redo và binary log lớn:** tạo nhiều I/O, tăng dung lượng log và công việc replication.
- **Rollback tốn thời gian:** nếu lỗi ở cuối transaction, server có thể phải hoàn tác lượng thay đổi rất lớn.
- **Tăng xác suất deadlock và lock wait:** nhiều luồng cùng cập nhật dữ liệu trên phạm vi lớn dễ tranh chấp.
- **Khó phục hồi tiến trình:** nếu client mất kết nối hoặc job dừng, phải xác định lại trạng thái đã commit.
- **Tác động vận hành:** replica lag, buffer pool churn, thời gian backup và bảo trì có thể tăng.

Ví dụ, câu lệnh sau có thể cập nhật toàn bộ lịch sử đơn hàng:

    UPDATE orders
    SET archived = 1
    WHERE created_at < '2024-01-01';

Nếu điều kiện khớp hàng triệu dòng, câu lệnh có thể chạy lâu và giữ transaction lớn. Chia batch giúp giới hạn số hàng mỗi lần commit:

    UPDATE orders
    SET archived = 1
    WHERE created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

Đây là ví dụ đơn giản về giới hạn số hàng. Để tiếp tục chính xác qua nhiều lần chạy, cần một chiến lược cursor/checkpoint ổn định. Chỉ lặp câu lệnh LIMIT mà không ghi nhận tiến độ có thể quét lại dữ liệu, xử lý lặp hoặc bỏ sót khi tập hàng thay đổi.

## 2. Khóa ổn định là gì?

Khóa dùng để chia batch nên có các thuộc tính:

1. **Duy nhất:** mỗi hàng có một giá trị khóa riêng, thường là primary key.
2. **Ổn định:** giá trị không thay đổi trong vòng đời hàng.
3. **Có thứ tự:** có thể sắp xếp nhất quán để xác định hàng tiếp theo.
4. **Có index:** việc tìm hàng sau checkpoint không phải quét lại toàn bảng.
5. **Phù hợp phạm vi công việc:** khóa có thể kết hợp với điều kiện nghiệp vụ để xác định đúng tập dữ liệu.

Primary key số tăng như id thường là lựa chọn thuận tiện. Nếu bảng dùng khóa ghép, có thể dùng tuple khóa duy nhất, ví dụ (tenant_id, event_id) hoặc (created_at, id). Cần bảo đảm thứ tự so sánh và điều kiện tiếp trang bao gồm đủ các thành phần để không trùng hoặc bỏ sót.

Không nên dùng các cột dễ thay đổi như status, updated_at hoặc tên hiển thị làm cursor chính. Nếu giá trị cursor thay đổi trong lúc job chạy, hàng có thể di chuyển về phía trước hoặc phía sau vị trí đã quét.

## 3. Keyset pagination thay cho OFFSET

### 3.1. Vấn đề của OFFSET

Phân trang kiểu OFFSET:

    SELECT id
    FROM orders
    ORDER BY id
    LIMIT 1000 OFFSET 500000;

MySQL vẫn phải đi qua các hàng trước offset rồi mới trả phần tiếp theo. Offset càng lớn, chi phí đọc và bỏ qua càng tăng. Khi dữ liệu được insert/delete đồng thời, vị trí tương đối của hàng thay đổi; trang sau có thể lặp hoặc bỏ sót hàng.

### 3.2. Dùng khóa cuối cùng đã xử lý

Keyset pagination nhớ giá trị khóa cuối cùng của batch trước:

    SELECT id
    FROM orders
    WHERE id > 500000
    ORDER BY id
    LIMIT 1000;

Nếu batch trả các ID từ 500001 đến 501000, checkpoint mới là 501000. Batch tiếp theo bắt đầu bằng id > 501000. Điều kiện so sánh trên khóa có index giúp MySQL tìm điểm bắt đầu thay vì bỏ qua hàng trăm nghìn hàng.

Mẫu tổng quát:

    SELECT id
    FROM orders
    WHERE id > :last_id
    ORDER BY id
    LIMIT :batch_size;

Các ký hiệu như :last_id, :high_id và :batch_size trong ví dụ là tham số do ứng dụng bind, không phải cú pháp placeholder đặt tên nguyên bản của prepared statement MySQL. Với JDBC, dùng dấu ? theo thứ tự tham số; thư viện phía client có thể hỗ trợ cú pháp đặt tên riêng.

Sau khi xử lý thành công, đặt last_id bằng ID lớn nhất đã xử lý trong batch. Không cập nhật checkpoint đến một ID chưa được xử lý hoặc trước khi phần việc tương ứng đã commit.

### 3.3. Vì sao cần ORDER BY duy nhất?

Nếu chỉ sắp xếp theo cột không duy nhất, nhiều hàng có thể cùng giá trị ở ranh giới batch. Ví dụ nhiều đơn hàng cùng created_at. Khi đó cần thêm khóa duy nhất làm tie-breaker:

    SELECT id, created_at
    FROM orders
    WHERE created_at > :last_created_at
       OR (created_at = :last_created_at AND id > :last_id)
    ORDER BY created_at, id
    LIMIT 1000;

Cursor là cặp (last_created_at, last_id). Điều kiện tiếp trang phải khớp thứ tự sắp xếp: so sánh thời gian trước, rồi ID khi thời gian bằng nhau. Index phù hợp thường là:

    CREATE INDEX idx_orders_created_id
    ON orders (created_at, id);

Nếu created_at có thể thay đổi, nó không phải cursor ổn định. Ưu tiên primary key bất biến; chỉ dùng khóa ghép khi mọi thành phần được bảo đảm không đổi trong lúc job chạy.

## 4. Chia batch bằng khoảng khóa

Một cách phổ biến là xác định last_id, chọn các ID kế tiếp rồi xử lý khoảng từ ID cũ đến ID cuối của batch.

### 4.1. Xác định high-water mark

Khi bắt đầu job, có thể lấy khóa lớn nhất hiện tại:

    SELECT COALESCE(MAX(id), 0) AS high_id
    FROM orders;

Giữ high_id làm giới hạn trên của lần chạy. Các truy vấn batch sau chỉ xét id <= high_id:

    SELECT id
    FROM orders
    WHERE id > :last_id
      AND id <= :high_id
    ORDER BY id
    LIMIT 1000;

High-water mark giúp giới hạn phạm vi và ngăn phần lớn hàng mới có ID lớn hơn làm job kéo dài vô tận. Tuy nhiên, nó không phải snapshot hoàn chỉnh của membership. Một transaction khác có thể đã cấp một AUTO_INCREMENT ID nhỏ hơn high_id nhưng chưa commit khi job đọc high-water mark; transaction đó commit sau khi cursor đã đi qua ID của nó. Vì vậy, nếu cần bảo đảm không bỏ sót hàng xuất hiện muộn, phải có thêm cơ chế như worklist cố định, cửa sổ ghi được kiểm soát hoặc lượt reconciliation sau job.

### 4.2. Tìm biên batch

Ví dụ lấy tối đa 1000 ID thỏa điều kiện:

    SELECT MAX(batch_ids.id) AS chunk_end
    FROM (
        SELECT id
        FROM orders
        WHERE id > :last_id
          AND id <= :high_id
          AND created_at < '2024-01-01'
        ORDER BY id
        LIMIT 1000
    ) AS batch_ids;

Nếu chunk_end khác NULL, có thể xử lý các hàng trong khoảng:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND created_at < '2024-01-01'
      AND archived = 0;

Vì chunk_end là ID cuối của 1000 hàng đủ điều kiện đầu tiên, khoảng khóa này chứa tối đa 1000 hàng đủ điều kiện tại thời điểm chọn batch. Các ID có thể có khoảng trống; điều đó không ảnh hưởng tính đúng đắn của cursor.

Nếu có cập nhật đồng thời làm điều kiện eligibility thay đổi giữa bước chọn và bước UPDATE, số hàng thực tế có thể thấp hơn. Với thao tác cần xử lý đúng chính xác tập ID đã chọn, hãy lưu danh sách ID của batch vào temporary/work table hoặc khóa các hàng cần xử lý trong cùng transaction.

### 4.3. Không dùng MAX(id) toàn bảng làm checkpoint mới

MAX(id) toàn bảng là high-water mark ban đầu, không phải ID cuối đã xử lý. Nếu batch chỉ xử lý 1000 hàng nhưng checkpoint nhảy đến MAX(id), tất cả hàng ở giữa sẽ bị bỏ qua. Checkpoint phải là khóa cuối của batch đã hoàn tất, hoặc một biên range mà job đã quét hết.

## 5. Ví dụ cập nhật dữ liệu theo batch

Giả sử cần chuyển các đơn hàng cũ sang trạng thái ARCHIVED. Bảng có primary key id và index phù hợp cho điều kiện lọc.

    CREATE INDEX idx_orders_archive_scan
    ON orders (archived, id);

Có thể chọn ID theo batch:

    SELECT id
    FROM orders
    WHERE archived = 0
      AND id > :last_id
      AND id <= :high_id
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

Ứng dụng ghi nhận ID cuối batch là chunk_end, sau đó cập nhật:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0
      AND created_at < '2024-01-01';

Cuối cùng commit và lưu checkpoint. Index (archived, id) có thể hỗ trợ lọc archived rồi đi theo thứ tự ID; tuy nhiên điều kiện created_at chưa nằm trong index nên MySQL có thể phải kiểm tra thêm. Nếu truy vấn rất lớn, cần cân nhắc index theo workload thực tế, ví dụ (archived, created_at, id) hoặc (created_at, id). Index tốt nhất phụ thuộc độ chọn lọc và thứ tự truy vấn; không tạo tất cả các biến thể một cách máy móc.

### 5.1. Khi cần xử lý đúng danh sách ID đã chọn

Với thao tác phức tạp có join hoặc điều kiện dễ thay đổi, lưu ID vào temporary table trong cùng session:

    CREATE TEMPORARY TABLE batch_order_ids (
        id BIGINT UNSIGNED NOT NULL PRIMARY KEY
    ) ENGINE=MEMORY;

    INSERT INTO batch_order_ids (id)
    SELECT id
    FROM orders
    WHERE id > :last_id
      AND id <= :high_id
      AND archived = 0
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

    UPDATE orders AS o
    JOIN batch_order_ids AS b ON b.id = o.id
    SET o.archived = 1
    WHERE o.archived = 0;

Temporary table giúp cố định tập ID của batch. Với batch lớn hoặc cần lưu tiến độ qua reconnect, dùng work table InnoDB thay cho temporary table. Temporary table biến mất khi session kết thúc; bảng MEMORY cũng có giới hạn RAM và không phù hợp cho mọi kích thước.

## 6. Chia batch DELETE theo khóa ổn định

Xóa dữ liệu cũ cũng nên dùng khóa có thứ tự:

    DELETE FROM audit_events
    WHERE id > :last_id
      AND id <= :chunk_end
      AND created_at < '2023-01-01';

Nếu chỉ dùng DELETE ... LIMIT 1000 lặp lại, MySQL có thể xóa từng nhóm nhưng ứng dụng cần bảo đảm truy vấn chọn đúng thứ tự và có cách biết đã kết thúc. Mẫu keyset giúp tiến độ có thể quan sát và tiếp tục sau lỗi.

Có thể dùng:

    DELETE FROM audit_events
    WHERE created_at < '2023-01-01'
    ORDER BY id
    LIMIT 1000;

để xóa từng lô đơn giản. Nhưng nếu cần resume chính xác, hãy lấy danh sách ID/biên khóa, xóa batch đó, commit rồi ghi checkpoint. Không dùng OFFSET trên tập dữ liệu đang bị xóa vì sau mỗi batch, vị trí hàng dịch chuyển và có thể bỏ sót.

### 6.1. Xử lý foreign key và bảng con

Nếu hàng cha được tham chiếu bởi bảng con, DELETE có thể bị chặn bởi RESTRICT hoặc xóa dây chuyền qua ON DELETE CASCADE. Một batch 1000 parent có thể kéo theo nhiều nghìn hoặc hàng triệu child rows. Cần tính cả lượng cascade, không chỉ số hàng trong bảng cha.

Với quan hệ lớn, có thể xóa child theo khóa ngoại trước rồi mới xóa parent, mỗi giai đoạn có checkpoint riêng. Nếu dùng cascade, kiểm thử số lượng tác động và thời gian trên bản sao dữ liệu. Không tắt foreign_key_checks chỉ để làm DELETE chạy qua.

## 7. Checkpoint để tiếp tục sau khi job dừng

Một job dài cần lưu trạng thái tiến độ bên ngoài vòng lặp ứng dụng. Ví dụ:

    CREATE TABLE batch_job_progress (
        job_name VARCHAR(100) NOT NULL,
        last_id BIGINT UNSIGNED NOT NULL DEFAULT 0,
        high_id BIGINT UNSIGNED NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (job_name)
    ) ENGINE=InnoDB;

Mỗi job có một hàng checkpoint. last_id là khóa cuối cùng đã xử lý thành công; high_id là giới hạn trên được chọn lúc bắt đầu; status cho biết job đang chạy hay hoàn tất.

### 7.1. Cập nhật dữ liệu và checkpoint trong cùng transaction

Nếu bảng dữ liệu và bảng checkpoint cùng nằm trong MySQL/InnoDB, hãy cập nhật cả hai trong cùng transaction:

    START TRANSACTION;

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0
      AND created_at < '2024-01-01';

    UPDATE batch_job_progress
    SET last_id = :chunk_end
    WHERE job_name = 'archive-old-orders';

    COMMIT;

Nếu transaction rollback, cả thay đổi dữ liệu và checkpoint đều rollback. Nếu commit thành công nhưng client mất kết nối trước khi nhận phản hồi, lần chạy lại đọc checkpoint đã commit và tiếp tục sau chunk_end.

Điều kiện WHERE job_name cần khớp đúng một hàng. Ứng dụng nên kiểm tra số hàng checkpoint được cập nhật và xử lý trường hợp job chưa được khởi tạo hoặc bị worker khác chiếm quyền.

### 7.2. Khóa hàng checkpoint để tránh hai worker cùng chạy

Nếu có khả năng hai tiến trình khởi động cùng một job, đọc checkpoint bằng FOR UPDATE trong transaction:

    START TRANSACTION;

    SELECT last_id, high_id, status
    FROM batch_job_progress
    WHERE job_name = 'archive-old-orders'
    FOR UPDATE;

    -- Chọn và xử lý một batch, cập nhật last_id.

    COMMIT;

Khóa hàng progress giúp serialize các worker cùng job nếu mọi worker tuân thủ giao thức này. Nếu batch selection và DML nằm ngoài transaction hoặc worker không khóa cùng hàng điều phối, hai worker vẫn có thể chọn trùng phạm vi.

Với job chạy lâu, không giữ một transaction duy nhất xuyên suốt tất cả batch. Mỗi batch bắt đầu transaction mới, khóa checkpoint, xử lý batch, cập nhật checkpoint rồi commit.

### 7.3. Checkpoint ngoài database

Nếu checkpoint nằm trong Redis, file hoặc hệ thống điều phối bên ngoài, không thể commit nguyên tử cùng transaction MySQL. Thứ tự an toàn thường là:

1. Commit batch trong MySQL.
2. Ghi checkpoint ngoài sau khi commit thành công.

Nếu tiến trình dừng giữa hai bước, batch có thể chạy lại. Vì vậy thao tác phải idempotent hoặc có ledger/unique key để nhận biết công việc đã hoàn thành. Ghi checkpoint ngoài trước khi commit có nguy cơ đánh dấu tiến độ trong khi dữ liệu chưa được commit, dẫn đến bỏ sót vĩnh viễn.

## 8. Idempotency và retry batch

Batch job có thể gặp deadlock, lock wait timeout, mất kết nối hoặc lỗi tạm thời. Retry là cần thiết nhưng chỉ an toàn nếu lặp lại cùng batch không gây tác động sai.

Ví dụ cập nhật đặt trạng thái cố định:

    UPDATE orders
    SET archived = 1
    WHERE id > :last_id
      AND id <= :chunk_end
      AND archived = 0;

Chạy lại thường không làm thay đổi kết quả cuối vì hàng đã archived = 1 không còn thỏa điều kiện. Đây là thao tác gần idempotent theo trạng thái đích.

Ngược lại:

    UPDATE account_balances
    SET balance = balance - 100
    WHERE id IN (...);

nếu retry sau khi commit nhưng client chưa nhận được phản hồi, số dư có thể bị trừ hai lần. Với thao tác cộng/trừ, phát sinh thanh toán hoặc gửi thông báo, cần idempotency key, ledger ghi nhận sự kiện hoặc cơ chế xác minh kết quả trước khi retry.

### 8.1. Deadlock và lock wait timeout

Nếu batch bị deadlock, InnoDB chọn một transaction làm victim và rollback transaction đó. Ứng dụng nên retry toàn bộ transaction batch sau một khoảng backoff ngẫu nhiên, giới hạn số lần retry. Không chỉ chạy lại câu UPDATE cuối nếu transaction gồm nhiều bước liên quan.

Với lock wait timeout, mặc định có thể chỉ statement bị lỗi được rollback tùy cấu hình innodb_rollback_on_timeout; ứng dụng nên chủ động rollback toàn transaction trước khi retry để đưa connection về trạng thái rõ ràng.

Không retry vô hạn. Ghi log batch key range, số lần thử, lỗi, thời gian chờ và kết quả cuối cùng.

## 9. Dữ liệu thay đổi đồng thời trong lúc chia batch

Stable key giúp xác định thứ tự, nhưng không tự đóng băng tập dữ liệu.

### 9.1. Hàng mới được insert sau khi job bắt đầu

Nếu ID mới luôn lớn hơn high_id, giới hạn id <= high_id loại chúng khỏi lượt chạy hiện tại. Có thể xử lý chúng ở lượt sau.

Tuy nhiên, AUTO_INCREMENT ID có thể được cấp trước khi transaction commit. Một transaction có thể giữ ID thấp hơn high-water mark, commit muộn sau khi cursor đã đi qua ID đó. Vì thế, high-water mark không thay thế snapshot hoặc worklist cố định.

### 9.2. Điều kiện lọc thay đổi

Giả sử job chọn status = 'PENDING'. Một hàng có ID nhỏ hơn last_id đang là DONE, sau đó một luồng khác đổi nó thành PENDING. Cursor sẽ không quay lại ID đó trong lượt hiện tại. Nếu cần xử lý mọi hàng thỏa điều kiện tại một thời điểm xác định, phải xác định membership bằng snapshot/worklist hoặc tạm kiểm soát writer.

### 9.3. Các chiến lược kiểm soát membership

- **Worklist cố định:** tạo danh sách ID cần xử lý tại thời điểm bắt đầu, sau đó chia worklist thành batch. Có thể dùng bảng staging với job_id, target_id, status.
- **Cửa sổ dữ liệu bất biến:** chọn theo cutoff đã thống nhất và bảo đảm ứng dụng không sửa thuộc tính quyết định membership trong cửa sổ đó.
- **Tạm dừng writer/cutover:** phù hợp migration cần một tập dữ liệu chính xác và có thể chấp nhận cửa sổ bảo trì.
- **Reconciliation pass:** sau lượt chính, quét lại các khoảng đã xử lý để tìm hàng đến muộn hoặc mới đủ điều kiện.
- **Queue/claim model:** worker claim từng hàng hoặc nhóm hàng bằng trạng thái/lease, có timeout và cơ chế phục hồi claim bị bỏ dở.

Chọn chiến lược theo yêu cầu nhất quán. Một job archive có thể chấp nhận lượt reconciliation; migration khóa chính hoặc chuyển đổi dữ liệu tài chính có thể cần worklist và đối soát nghiêm ngặt hơn.

## 10. Worklist và staging table

Khi cần biết chính xác hàng nào thuộc job, tạo worklist:

    CREATE TABLE batch_job_items (
        job_name VARCHAR(100) NOT NULL,
        target_id BIGINT UNSIGNED NOT NULL,
        item_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        processed_at DATETIME NULL,
        PRIMARY KEY (job_name, target_id),
        KEY idx_job_status_id (job_name, item_status, target_id)
    ) ENGINE=InnoDB;

Nạp tập ID ban đầu:

    INSERT INTO batch_job_items (job_name, target_id)
    SELECT
        'archive-old-orders',
        id
    FROM orders
    WHERE created_at < '2024-01-01'
      AND archived = 0;

Sau đó chọn một batch:

    SELECT target_id
    FROM batch_job_items
    WHERE job_name = 'archive-old-orders'
      AND item_status = 'PENDING'
    ORDER BY target_id
    LIMIT 1000;

Ứng dụng lấy danh sách ID, cập nhật dữ liệu đích và đánh dấu item đã xử lý trong cùng transaction:

    START TRANSACTION;

    UPDATE orders
    SET archived = 1
    WHERE id IN (/* IDs của batch */)
      AND archived = 0;

    UPDATE batch_job_items
    SET item_status = 'DONE',
        processed_at = CURRENT_TIMESTAMP
    WHERE job_name = 'archive-old-orders'
      AND target_id IN (/* cùng IDs */)
      AND item_status = 'PENDING';

    COMMIT;

Worklist cho phép resume theo trạng thái item thay vì một cursor đơn. Nó tốn dung lượng và thêm I/O, nhưng hữu ích khi membership phức tạp, các ID không liên tiếp hoặc nhiều worker xử lý song song. Cần khóa/claim item để tránh hai worker cùng lấy một batch; có thể dùng SELECT ... FOR UPDATE SKIP LOCKED trên MySQL 8.0, nhưng phải thiết kế trạng thái claim và lease để phục hồi worker chết.

SKIP LOCKED bỏ qua hàng đang bị khóa, nên không được tăng cursor toàn cục vượt qua hàng bị skip rồi coi job đã hoàn tất. Với worklist, chỉ đánh dấu DONE khi batch thực sự xử lý; hàng bị skip vẫn phải ở trạng thái chờ để worker khác xử lý.

## 11. Giao dịch nhỏ vẫn phải có thứ tự khóa nhất quán

Chia batch làm giảm phạm vi lock mỗi transaction, nhưng không loại bỏ deadlock. Nếu một transaction cập nhật nhiều bảng hoặc nhiều hàng, nên truy cập theo cùng thứ tự ở mọi worker.

Ví dụ worker A cập nhật orders rồi order_items, worker B cập nhật order_items rồi orders; hai transaction có thể giữ lock chéo nhau. Chuẩn hóa thứ tự truy cập và giữ transaction ngắn giúp giảm rủi ro.

Với batch theo ID, xử lý tăng dần theo primary key thường tạo thứ tự truy cập ổn định:

    START TRANSACTION;

    SELECT id
    FROM orders
    WHERE id > :last_id
    ORDER BY id
    LIMIT 500
    FOR UPDATE;

Sau khi lấy khóa, thực hiện DML rồi COMMIT trong cùng transaction. Locking read chỉ giữ khóa trong transaction; nếu autocommit bật và không mở transaction tường minh, khóa có thể được giải phóng ngay khi câu SELECT kết thúc. Cần cân nhắc isolation level, index và phạm vi range lock của InnoDB; câu lệnh locking read có thể khóa thêm khoảng index tùy kế hoạch và isolation level.

## 12. Chọn kích thước batch

Không có batch size tối ưu chung. Các yếu tố ảnh hưởng:

- Kích thước hàng và số index phải cập nhật.
- Số hàng bị trigger hoặc foreign key cascade tác động.
- Thời gian giữ lock và thời gian commit.
- IOPS, CPU, buffer pool và tải OLTP đồng thời.
- Dung lượng binary log và tốc độ replica apply.
- Độ lớn packet nếu gửi danh sách ID hoặc multi-row statement.
- Tỷ lệ deadlock, lock wait timeout và số lần retry.

Bắt đầu với batch nhỏ, đo rồi tăng dần. Có thể điều chỉnh dựa trên thời gian xử lý mục tiêu, ví dụ mỗi batch nên hoàn thành trong vài trăm mili giây đến vài giây tùy hệ thống. Nếu batch liên tục mất nhiều giây, lock wait tăng hoặc replica lag phình lên, giảm kích thước hoặc giảm tốc độ giữa các batch.

### 12.1. Adaptive throttling

Job có thể điều chỉnh batch size hoặc sleep giữa các batch theo chỉ số:

- Thời gian trung bình của batch gần nhất.
- Lock wait/deadlock.
- CPU và I/O của server.
- Replication lag.
- Tải request nghiệp vụ.

Ví dụ logic:

    if (replicaLag > lagThreshold || lockWaits > waitThreshold) {
        batchSize = max(minBatchSize, batchSize / 2);
        pauseBetweenBatches();
    } else if (batchDuration < targetDuration) {
        batchSize = min(maxBatchSize, batchSize + step);
    }

Đây là pseudocode điều khiển ở ứng dụng, không phải cú pháp SQL. Đặt giới hạn min/max và tránh tăng giảm quá nhanh gây dao động.

## 13. Theo dõi tiến độ và xác minh kết quả

Một batch job vận hành tốt cần ghi nhận:

| Chỉ số | Mục đích |
|---|---|
| Job name và run ID | Phân biệt các lần chạy |
| Last key / high key | Biết phạm vi đã xử lý |
| Batch size và affected rows | Phát hiện batch rỗng hoặc bất thường |
| Batch duration | Đo hiệu năng và điều chỉnh tốc độ |
| Retry/deadlock count | Phát hiện tranh chấp |
| Error code và message | Chẩn đoán lỗi |
| Replica lag | Theo dõi tác động replication |
| Started/finished time | Ước lượng tiến độ và thời gian còn lại |
| Reconciliation count | Xác nhận hàng đến muộn hoặc bị bỏ sót |

Sau job, đối soát số hàng theo cùng điều kiện nghiệp vụ:

    SELECT COUNT(*) AS remaining_rows
    FROM orders
    WHERE archived = 0
      AND created_at < '2024-01-01';

Nếu kết quả phải bằng 0, điều tra mọi hàng còn lại trước khi kết luận job thành công. Có thể kiểm tra theo range, so sánh checksum hoặc đối chiếu tổng số hàng nguồn/đích. Không chỉ dựa vào checkpoint cuối cùng: checkpoint chứng minh cursor đã đi qua một phạm vi, không chứng minh mọi hàng trong phạm vi đạt đúng trạng thái nếu có lỗi logic hoặc concurrent mutation.

## 14. Dùng EXPLAIN để kiểm tra truy vấn batch

Điều kiện keyset cần index phù hợp. Kiểm tra truy vấn chọn ID:

    EXPLAIN
    SELECT id
    FROM orders
    WHERE archived = 0
      AND id > 500000
      AND id <= 900000
      AND created_at < '2024-01-01'
    ORDER BY id
    LIMIT 1000;

Quan sát:

- key: index được chọn.
- type: kiểu truy cập, ví dụ range, ref hoặc ALL.
- rows: số hàng ước lượng cần đọc.
- filtered: tỷ lệ hàng còn lại sau lọc.
- Extra: thông tin về lọc, sort hoặc covering index.

Nếu optimizer phải quét quá nhiều hàng vì điều kiện lọc không có index phù hợp, batch vẫn có thể chậm dù chỉ cập nhật 1000 hàng. Đôi khi SELECT ID là phần tốn chi phí lớn nhất của job.

Không thêm index chỉ để phục vụ một lần chạy mà chưa tính chi phí lưu trữ và ghi. Index mới trên bảng lớn cũng cần thời gian build và có thể gây tải/metadata lock; lên kế hoạch riêng nếu cần.

## 15. Những trường hợp cần tránh

- Không chạy một transaction khổng lồ chỉ để đơn giản hóa code.
- Không dùng OFFSET lớn trên tập dữ liệu đang thay đổi.
- Không dùng khóa có thể thay đổi làm cursor.
- Không tăng checkpoint trước khi dữ liệu batch commit.
- Không ghi checkpoint ngoài trước khi commit dữ liệu.
- Không giả định MAX(id) là snapshot đầy đủ của mọi transaction đang chạy.
- Không retry thao tác cộng/trừ hoặc gửi sự kiện nếu chưa có idempotency.
- Không dùng SKIP LOCKED rồi bỏ qua vĩnh viễn các hàng bị khóa.
- Không xóa parent mà bỏ qua child/cascade.
- Không tăng batch size khi replica lag hoặc lock wait đang tăng.
- Không coi affected_rows = 0 luôn là lỗi; hàng có thể đã được xử lý trước đó hoặc không còn thỏa predicate.
- Không coi checkpoint hoàn tất là bằng chứng thay cho reconciliation.

## 16. Quy trình triển khai batch job

1. **Xác định tập dữ liệu:** điều kiện nghiệp vụ, khóa duy nhất, khả năng thay đổi và cách xử lý hàng đến muộn.
2. **Chọn cursor:** ưu tiên primary key bất biến; nếu dùng khóa ghép, xác định thứ tự và predicate tiếp trang chính xác.
3. **Xác định high-water mark hoặc worklist:** chọn theo yêu cầu membership và mức độ ghi đồng thời.
4. **Tạo checkpoint:** lưu last key, giới hạn trên, trạng thái job và run ID.
5. **Chọn batch size ban đầu:** đo trên staging hoặc bản sao dữ liệu đại diện.
6. **Chạy từng transaction:** chọn batch, thực hiện DML, cập nhật checkpoint cùng transaction rồi commit.
7. **Retry có giới hạn:** rollback toàn transaction khi lỗi, backoff và chỉ retry thao tác idempotent.
8. **Throttle theo tải:** theo dõi batch duration, lock wait, deadlock và replication lag.
9. **Resume sau gián đoạn:** đọc checkpoint đã commit, xác nhận job/run ownership rồi tiếp tục.
10. **Reconcile:** quét lại các hàng còn đủ điều kiện, xử lý hàng đến muộn và đối chiếu kết quả.
11. **Đóng job:** chỉ đặt trạng thái COMPLETED khi điều kiện nghiệp vụ và đối soát đạt.

## 17. Checklist chia lô an toàn

- Khóa cursor có duy nhất, bất biến, có thứ tự và có index không?
- ORDER BY có tie-breaker duy nhất không?
- Predicate tiếp trang có khớp thứ tự cursor không?
- Có dùng OFFSET lớn không?
- High-water mark có bị hiểu nhầm là snapshot không?
- Có transaction chưa commit nào có thể xuất hiện muộn với key nhỏ hơn cursor không?
- Điều kiện eligibility có thể thay đổi trong lúc job chạy không?
- Có cần worklist cố định hoặc reconciliation pass không?
- Batch DML và checkpoint có commit nguyên tử cùng nhau không?
- Nếu checkpoint ngoài database, thao tác có idempotent để retry không?
- Hai worker có thể cùng xử lý một job/range không? Đã có cơ chế lock/claim chưa?
- Batch size có giới hạn thời gian giữ lock và tác động cascade không?
- Có theo dõi deadlock, lock wait, undo/redo, binlog và replica lag không?
- Có kế hoạch retry, resume và xử lý hàng lỗi riêng không?
- Đã đối soát dữ liệu còn lại sau khi job kết thúc chưa?

## Kết luận

Chia lô theo khóa ổn định giúp job cập nhật hoặc xóa dữ liệu lớn có thể tiếp tục sau lỗi, giới hạn thời gian giữ lock và giảm quy mô mỗi transaction. Ưu tiên keyset pagination theo primary key bất biến, dùng checkpoint chỉ sau khi batch commit và giữ cập nhật dữ liệu/checkpoint trong cùng transaction khi có thể. High-water mark không tự tạo snapshot; dữ liệu commit muộn hoặc điều kiện lọc thay đổi vẫn có thể bị bỏ sót, nên cần worklist, kiểm soát writer hoặc reconciliation theo yêu cầu. Kết hợp batch size phù hợp, retry idempotent, theo dõi replication và đối soát cuối job để vận hành thay đổi dữ liệu lớn an toàn.
