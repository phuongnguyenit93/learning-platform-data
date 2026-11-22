# Deadlock khi đọc ghi cùng bảng

Trong Spring Batch, một Job có thể đọc các bản ghi từ một bảng rồi cập nhật chính bảng đó trong cùng Step. Ví dụ, Job chọn các giao dịch có trạng thái READY, xử lý chúng và đổi trạng thái thành PROCESSED. Khi chỉ có một worker, luồng này có thể chạy ổn định. Nhưng khi nhiều JobExecution, partition hoặc transaction khác cùng truy cập bảng, database có thể xuất hiện lock wait hoặc deadlock.

**Deadlock** xảy ra khi hai hoặc nhiều transaction giữ các lock mà transaction còn lại cần, tạo thành một vòng chờ không thể tự giải quyết. Database phát hiện vòng chờ và hủy một transaction làm deadlock victim. Đây là cơ chế bảo vệ tính nhất quán của database; Spring Batch cần rollback chunk tương ứng và có thể retry nếu lỗi được phân loại là tạm thời.

Không phải mọi tình huống đọc và ghi cùng bảng đều tạo deadlock. Một câu SELECT thông thường trên database dùng MVCC có thể không chặn UPDATE. Rủi ro phụ thuộc database engine, isolation level, loại truy vấn đọc, index, thứ tự khóa, transaction duration và số worker chạy đồng thời. Ngoài deadlock, việc cập nhật cột dùng làm điều kiện đọc còn có thể làm paging bỏ sót bản ghi dù không có deadlock.

## 1. Bối cảnh đọc và ghi cùng bảng

Giả sử bảng work_item chứa các công việc cần xử lý:

~~~sql
CREATE TABLE work_item (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    payload TEXT,
    processed_at TIMESTAMP
);
~~~

Reader lấy các bản ghi đang chờ:

~~~sql
SELECT id, status, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id;
~~~

Writer cập nhật trạng thái sau khi xử lý:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

Một Step có thể dùng reader và writer như sau:

~~~text
work_item (status = READY)
       |
       v
    ItemReader
       |
       v
   ItemProcessor
       |
       v
    ItemWriter
       |
       v
UPDATE work_item
SET status = PROCESSED
~~~

Thiết kế này hợp lệ trong nhiều hệ thống. Vấn đề xuất hiện khi một transaction giữ lock trên các row hoặc index entry trong lúc transaction khác cần cùng tài nguyên theo thứ tự khác, hoặc reader dùng locking read và giữ lock lâu trong khi chunk đang xử lý.

## 2. Deadlock khác lock wait như thế nào?

**Lock wait** xảy ra khi một transaction phải đợi lock do transaction khác đang giữ. Khi transaction giữ lock commit hoặc rollback, transaction đang đợi có thể tiếp tục.

**Deadlock** là vòng chờ. Ví dụ:

~~~text
Transaction A giữ lock row 1
Transaction B giữ lock row 2

Transaction A cần row 2 -> chờ B
Transaction B cần row 1 -> chờ A

       A waits for B
       B waits for A
             |
             v
          DEADLOCK
~~~

Database không thể chờ vô hạn trong tình huống này. Nó chọn một transaction làm victim, rollback transaction đó và trả lỗi cho ứng dụng. Transaction còn lại tiếp tục sau khi lock được giải phóng.

| Hiện tượng | Đặc điểm | Hướng xử lý |
|---|---|---|
| Lock wait | Một transaction đang giữ lock, transaction khác chờ | Giảm thời gian giữ lock, xem lại transaction và index |
| Deadlock | Các transaction tạo vòng chờ lock | Phân tích deadlock graph, chuẩn hóa thứ tự truy cập, retry có giới hạn |
| Lock timeout | Transaction chờ quá thời gian cấu hình | Xác định blocker và điều chỉnh timeout/transaction |
| Pagination bỏ sót | Tập kết quả thay đổi khi writer cập nhật điều kiện lọc | Ổn định tập input hoặc dùng cách đọc/claim phù hợp |

Deadlock thường là lỗi tạm thời ở cấp transaction, nhưng nguyên nhân thiết kế có thể lặp lại ở mỗi lần chạy. Chỉ tăng retry limit mà không xử lý lock order hoặc transaction duration có thể làm Job chậm hơn và tăng tải database.

## 3. Vì sao đọc và ghi cùng bảng có thể gây deadlock?

Có một số tình huống phổ biến:

1. Hai worker đọc các tập row giao nhau rồi cập nhật theo thứ tự khác nhau.
2. Reader dùng SELECT FOR UPDATE hoặc locking hint và giữ lock trong khi processor thực hiện công việc lâu.
3. Một transaction đọc/khóa row A rồi writer cập nhật row B, trong khi transaction khác khóa B rồi cần A.
4. Writer cập nhật bảng chính, trigger hoặc foreign key khiến database phải khóa thêm bảng/index theo thứ tự khác transaction khác.
5. Hai JobExecution cùng xử lý các bản ghi trùng phạm vi.
6. Partition không độc lập nên nhiều worker cùng cập nhật một business key.

Một câu SELECT không khóa thông thường không nhất thiết gây deadlock. Trên database dùng MVCC, consistent read thường lấy snapshot mà không giữ row lock chặn writer. Nhưng locking read, isolation level cao, index/range lock hoặc engine dùng locking read cho SELECT có thể tạo xung đột. Cần kiểm tra hành vi của database thực tế.

## 4. Deadlock do hai transaction cập nhật row theo thứ tự khác nhau

Ví dụ bảng có hai row:

~~~text
id = 10
id = 20
~~~

Transaction A xử lý item theo thứ tự 10 rồi 20:

~~~sql
UPDATE work_item SET status = 'DONE' WHERE id = 10;
UPDATE work_item SET status = 'DONE' WHERE id = 20;
~~~

Transaction B xử lý theo thứ tự 20 rồi 10:

~~~sql
UPDATE work_item SET status = 'DONE' WHERE id = 20;
UPDATE work_item SET status = 'DONE' WHERE id = 10;
~~~

Một interleaving có thể xảy ra:

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| 1 | Khóa row 10 | |
| 2 | | Khóa row 20 |
| 3 | Cần row 20, phải chờ B | |
| 4 | | Cần row 10, phải chờ A |
| 5 | Database phát hiện vòng chờ và rollback một transaction | |

Để giảm rủi ro, mọi transaction nên truy cập các row theo cùng thứ tự khóa, chẳng hạn tăng dần theo primary key. Nếu mỗi item chỉ cập nhật một row, vẫn cần kiểm tra trigger, cascade, index và transaction khác có thể tạo thêm lock dependency.

Sắp xếp item theo ID trong reader có thể giúp, nhưng chỉ khi mọi luồng ghi liên quan tuân theo cùng thứ tự. Một thứ tự đọc ổn định không đủ nếu trigger hoặc service khác khóa row theo thứ tự ngược lại.

## 5. Deadlock do locking read

Một reader có thể dùng locking query để giữ row trong lúc xử lý:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id
FOR UPDATE;
~~~

FOR UPDATE là cú pháp phổ biến ở PostgreSQL, Oracle và một số database khác; cú pháp/hành vi có khác biệt theo engine. Query này yêu cầu khóa các row được chọn để transaction khác không thể cập nhật chúng theo cách xung đột cho đến khi transaction kết thúc.

Nếu processor thực hiện gọi API, tính toán nặng hoặc chờ dịch vụ bên ngoài trước khi writer hoàn tất, transaction có thể giữ lock lâu. Worker khác có thể cần các row đó hoặc các row liên quan và tạo vòng chờ.

Không dùng locking read chỉ để “tránh xử lý trùng” nếu chưa xác định semantics cần thiết. Có thể dùng cơ chế claim/lease, partitioning hoặc optimistic locking phù hợp hơn. Nếu thật sự cần khóa row, giữ transaction ngắn và xác định rõ ai có quyền xử lý row.

## 6. Reader và writer có thể dùng connection/transaction khác nhau

Không phải mọi reader đều tương tác với transaction chunk theo cùng cách:

- JdbcCursorItemReader mở cursor và có thể dùng connection riêng theo cấu hình. Có tùy chọn chia sẻ extended connection trong một số trường hợp, nhưng cần cấu hình ExtendedConnectionDataSourceProxy đúng cách.
- JdbcPagingItemReader thực hiện các query theo trang và giữ trạng thái paging/checkpoint; mỗi query có thể có transaction/connection semantics khác cursor.
- Một custom reader có thể dùng JdbcTemplate, repository hoặc connection tự quản lý.
- Writer thường dùng connection được transaction manager quản lý nếu DataSource và transaction manager được cấu hình tương thích.

Do đó, không nên suy luận rằng SELECT và UPDATE chắc chắn chạy trên cùng connection hoặc cùng transaction chỉ vì chúng nằm trong một Step. Hãy xác minh reader implementation, DataSource, transaction manager, connection sharing và isolation level.

Nếu reader và writer dùng cùng DataSource nhưng reader giữ cursor trên connection riêng, cursor có thể sống qua nhiều chunk transaction. Điều này ảnh hưởng đến snapshot, lock duration và khả năng nhìn thấy thay đổi. Nếu bật shared extended connection, semantics lại khác. Kiểm tra tài liệu phiên bản Spring Batch và database driver đang dùng.

## 7. Transaction của chunk và thời gian giữ lock

Trong chunk-oriented Step, Spring Batch quản lý transaction theo chunk. Khi một chunk xử lý nhiều item, transaction thường bao quanh phần xử lý chunk và commit sau khi writer hoàn tất cùng các cập nhật metadata tương ứng.

Luồng khái quát:

~~~text
Begin chunk transaction
       |
       v
Read items
       |
       v
Process items
       |
       v
Write chunk
       |
       v
Update stream/checkpoint
       |
       v
Commit
~~~

Nếu reader thực hiện locking read trong transaction này, lock có thể được giữ trong cả thời gian processor chạy. Chunk lớn hoặc processor chậm làm transaction dài hơn, tăng thời gian các transaction khác phải chờ.

Các nguyên nhân làm transaction kéo dài:

- Chunk size quá lớn.
- Processor gọi REST/SOAP hoặc chờ message broker.
- Truy vấn N+1 trong processor.
- Writer ghi nhiều bảng hoặc gọi stored procedure nặng.
- Database thiếu index cho điều kiện lọc hoặc join.
- Connection pool quá nhỏ khiến các transaction giữ connection trong thời gian dài.

Giảm transaction duration thường giúp giảm lock contention. Tuy nhiên, chunk nhỏ hơn làm tăng số lần commit và overhead. Cần đo với workload thật thay vì chọn chunk size chỉ dựa trên số lượng item.

## 8. Isolation level và hành vi đọc

Isolation level quyết định mức độ transaction nhìn thấy thay đổi của transaction khác và loại lock/snapshot database sử dụng. Hành vi cụ thể phụ thuộc engine:

| Isolation | Ý nghĩa khái quát | Điểm cần chú ý |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit ở engine hỗ trợ | Dirty read; không phù hợp cho nhiều batch nghiệp vụ |
| READ COMMITTED | Mỗi statement thấy dữ liệu đã commit theo semantics engine | Có thể đọc snapshot mới ở mỗi query; không bảo đảm cùng một tập dữ liệu xuyên Step |
| REPEATABLE READ | Bảo vệ tính lặp lại của read theo engine | Có thể tăng lock hoặc snapshot retention |
| SERIALIZABLE | Yêu cầu kết quả tương đương thực thi tuần tự | Có thể tăng blocking, serialization failure hoặc deadlock |

Một số database dùng MVCC để SELECT thông thường không khóa row mà writer cần. Ví dụ, PostgreSQL consistent reads dưới các isolation phổ biến thường không chặn UPDATE theo cách của locking read; MySQL InnoDB cũng phân biệt consistent read với locking read. SQL Server có thể dùng locking READ COMMITTED hoặc row-versioning khi bật READ_COMMITTED_SNAPSHOT. Không áp dụng một mô tả chung cho mọi database.

Không tự hạ isolation level chỉ để hết deadlock. Trước hết, xác định tính nhất quán mà Job cần: snapshot toàn bộ file, đọc dữ liệu đã commit tại từng statement hay claim row độc quyền. Sau đó chọn isolation và locking strategy tương ứng.

## 9. Phân biệt deadlock với pagination bỏ sót bản ghi

Một lỗi thường bị nhầm với deadlock xảy ra khi reader lọc theo status và writer cập nhật chính status đó.

Giả sử truy vấn dùng offset pagination:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id
OFFSET :offset ROWS FETCH NEXT :pageSize ROWS ONLY;
~~~

Ban đầu có 6 row READY và page size là 3:

~~~text
Trang 1: id 1, 2, 3
Trang 2: id 4, 5, 6
~~~

Sau khi trang 1 được đọc và writer đổi status của 1, 2, 3 thành PROCESSED, tập READY chỉ còn 4, 5, 6. Nếu trang kế tiếp vẫn dùng OFFSET 3, database bỏ qua ba row đầu của tập kết quả mới và có thể trả về rỗng. Các row 4, 5, 6 bị bỏ sót dù không có deadlock.

Đây là vấn đề tập kết quả thay đổi khi phân trang, không phải lock cycle. Có thể tránh bằng cách:

- Đọc tập ID đầu vào vào staging/snapshot trước khi cập nhật status.
- Dùng keyset pagination với sort key duy nhất và ổn định.
- Dùng claim strategy có trạng thái rõ ràng.
- Không thay đổi predicate làm tập dữ liệu trang biến đổi theo cách reader không dự đoán được.

JdbcPagingItemReader thường dùng sort key để tiếp tục từ vị trí cuối trang thay vì giả định mọi implementation đều dùng OFFSET. Tuy vậy, nếu query predicate thay đổi do writer cập nhật cùng bảng, cần kiểm tra semantics paging cụ thể và test trường hợp restart. Không đánh đồng lỗi pagination với deadlock.

## 10. Keyset paging và sort key ổn định

Keyset paging lấy các row sau khóa cuối cùng đã đọc, ví dụ:

~~~sql
SELECT id, status, payload
FROM work_item
WHERE status = 'READY'
  AND id > :lastId
ORDER BY id
FETCH FIRST :pageSize ROWS ONLY;
~~~

Sort key nên:

- Có giá trị không null.
- Ổn định trong suốt quá trình Job chạy.
- Duy nhất hoặc có tie-breaker duy nhất.
- Có index phù hợp với predicate và order.

Với sort key ghép:

~~~sql
WHERE (created_at, id) > (:lastCreatedAt, :lastId)
ORDER BY created_at, id
~~~

Cú pháp tuple comparison khác nhau theo database; có thể viết thành điều kiện OR tương đương.

Keyset paging giảm vấn đề dịch chuyển offset khi tập kết quả thay đổi. Tuy nhiên, nếu writer cập nhật cột status khiến row không còn thỏa predicate, hoặc có row mới được thêm với key nhỏ hơn checkpoint, reader vẫn cần một chính sách snapshot/eligibility rõ ràng.

## 11. Đọc snapshot rồi ghi trạng thái ở bước riêng

Một cách đơn giản để giảm xung đột giữa đọc và ghi cùng bảng là tách việc xác định tập input khỏi việc cập nhật bảng nguồn:

~~~text
Step 1: Snapshot IDs cần xử lý
   work_item (READY)
        |
        v
   staging_batch_item

Step 2: Process các ID trong staging
   staging_batch_item
        |
        v
   Processor
        |
        v
   Writer cập nhật work_item

Step 3: Đối soát batch
   Tổng hợp COMPLETED / FAILED
~~~

Ví dụ staging table:

~~~sql
CREATE TABLE batch_work_item (
    batch_id VARCHAR(80) NOT NULL,
    item_id BIGINT NOT NULL,
    state VARCHAR(20) NOT NULL,
    PRIMARY KEY (batch_id, item_id)
);
~~~

Step chuẩn bị chèn ID đủ điều kiện vào batch_work_item. Các Step sau đọc staging theo batch_id, trong khi writer cập nhật work_item. Tập input đã được cố định, nên việc thay đổi status trên bảng gốc không làm thay đổi danh sách item cần xử lý.

Cần có quy tắc để tránh hai Job cùng snapshot một item. Có thể claim row khi tạo staging, dùng unique constraint hoặc một transaction claim có locking strategy rõ ràng. Staging cũng cần cleanup/retention và recovery khi Job thất bại.

## 12. Claim row thay vì chỉ SELECT rồi UPDATE

Nếu nhiều worker cùng lấy công việc từ một bảng, mô hình “SELECT READY rồi sau đó UPDATE PROCESSED” có thể khiến hai worker cùng đọc một row trước khi một bên cập nhật. Cần một cơ chế claim có tính nguyên tử.

Một số database hỗ trợ SKIP LOCKED hoặc locking hint tương tự để worker lấy các row chưa bị worker khác khóa. Ví dụ PostgreSQL:

~~~sql
WITH picked AS (
    SELECT id
    FROM work_item
    WHERE status = 'READY'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE work_item w
SET status = 'IN_PROGRESS',
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE w.id = picked.id
RETURNING w.id, w.payload;
~~~

Đây là cú pháp PostgreSQL, không phải SQL portable. MySQL, Oracle và SQL Server có cú pháp/locking hint riêng. SKIP LOCKED giúp worker không chờ row đang bị worker khác khóa, nhưng không loại bỏ mọi deadlock và có thể gây starvation nếu một row liên tục bị giữ lock.

Một mô hình claim có thể:

1. Chọn và cập nhật row READY thành IN_PROGRESS trong transaction ngắn.
2. Commit claim để worker khác không lấy cùng row.
3. Xử lý item theo claim token/worker ID.
4. Cập nhật COMPLETED hoặc FAILED.
5. Có lease/timeout để thu hồi claim bị bỏ dở khi worker chết.

Nếu claim và xử lý nằm trong cùng transaction dài, lock vẫn được giữ trong suốt quá trình xử lý. Muốn giải phóng lock sớm, phải commit claim trước và có cơ chế lease/recovery để xử lý worker chết hoặc mất kết nối.

## 13. Chia partition để giảm giao nhau

Partitioning có thể giảm deadlock nếu mỗi worker nhận một phạm vi dữ liệu không chồng lấn:

~~~text
Manager Step
    |
    +--> Worker 0: id 1..10000
    |
    +--> Worker 1: id 10001..20000
    |
    +--> Worker 2: id 20001..30000
~~~

Khi mỗi worker đọc và cập nhật row thuộc phạm vi riêng, khả năng hai worker tranh chấp cùng row giảm. Nhưng partition chỉ hiệu quả nếu:

- Range không chồng lấn.
- Writer không cập nhật các row ngoài range.
- Trigger/foreign key không tạo xung đột trên cùng row tổng hợp.
- Các bảng liên quan được khóa theo thứ tự nhất quán.
- Job khác không đồng thời xử lý cùng business key.

Nếu partition theo customer nhưng mọi worker cùng cập nhật một row tổng hợp toàn hệ thống, row tổng hợp đó vẫn có thể trở thành điểm nóng. Có thể ghi dữ liệu chi tiết song song rồi tổng hợp trong Step riêng.

## 14. Giảm transaction duration

Một trong những biện pháp hiệu quả nhất là giảm thời gian transaction giữ lock:

- Chọn chunk size vừa phải và benchmark.
- Không gọi network chậm bên trong transaction nếu có thể tách ra.
- Tránh truy vấn phụ lặp lại trong processor.
- Tạo index cho predicate và join phù hợp.
- Chỉ cập nhật các cột cần thiết.
- Không giữ cursor/locking read lâu hơn yêu cầu.
- Tránh transaction lồng nhau hoặc propagation không chủ ý.
- Đảm bảo connection được trả về pool sau khi Step/transaction kết thúc.

Ví dụ, nếu processor gọi dịch vụ định giá mất 2 giây cho mỗi item và chunk có 500 item, transaction có thể giữ tài nguyên rất lâu. Có thể tách bước enrich/lookup ra ngoài transaction ghi, dùng cache/snapshot, hoặc xử lý trước rồi mới thực hiện transaction cập nhật ngắn.

Không phải mọi công việc đều có thể tách transaction mà vẫn giữ semantics. Nếu dữ liệu có thể thay đổi giữa lúc đọc và lúc ghi, cần kiểm tra version hoặc điều kiện trạng thái khi update.

## 15. Cập nhật có điều kiện và optimistic locking

Một writer có thể cập nhật theo ID và trạng thái kỳ vọng:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    version = version + 1,
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_PROGRESS'
  AND version = :expectedVersion;
~~~

Nếu update count bằng 0, row có thể đã bị worker khác cập nhật hoặc version không còn khớp. Đây là tín hiệu conflict cần xử lý, không nhất thiết là deadlock.

Optimistic locking phù hợp khi xung đột hiếm và không muốn giữ lock từ lúc đọc đến lúc ghi. Cần xác định rõ hành vi khi version conflict: retry đọc lại, chuyển trạng thái conflict, hoặc fail item.

Không bỏ qua update count bằng 0 nếu item bắt buộc phải được ghi. Dùng điều kiện update và kiểm tra số row ảnh hưởng giúp phát hiện race thay vì âm thầm ghi đè dữ liệu mới hơn.

## 16. Index ảnh hưởng đến lock footprint

Thiếu index có thể khiến database quét nhiều row/page để tìm dữ liệu, kéo dài query và có thể khóa phạm vi lớn hơn tùy engine/isolation. Index không tự loại bỏ deadlock, nhưng thường giúp giảm số row cần đọc và thời gian giữ lock.

Ví dụ truy vấn:

~~~sql
SELECT id, payload
FROM work_item
WHERE status = 'READY'
ORDER BY id;
~~~

Một index phù hợp có thể bắt đầu bằng status và tiếp theo là id:

~~~sql
CREATE INDEX ix_work_item_status_id
    ON work_item(status, id);
~~~

Index chính xác cần dựa trên selectivity, query plan và database. Khi UPDATE status, database cũng phải cập nhật index chứa status, vì vậy index bổ sung quá nhiều có thể tăng chi phí ghi và lock. Xem execution plan và đo thực tế trước khi thêm index.

Các join, trigger và foreign key cũng có thể truy cập thêm bảng/index. Deadlock graph thường cho thấy resource thực tế đang tranh chấp, không nhất thiết chỉ là row trong bảng reader ban đầu.

## 17. Chuẩn hóa thứ tự truy cập tài nguyên

Nếu một chunk cập nhật nhiều bảng, mọi luồng xử lý nên truy cập bảng và row theo cùng thứ tự. Ví dụ:

~~~text
Order -> Account -> Ledger
~~~

Không để một transaction cập nhật Account rồi Order trong khi transaction khác cập nhật Order rồi Account nếu cả hai có thể chờ nhau.

Một số quy tắc:

- Sắp xếp danh sách ID trước khi cập nhật hàng loạt.
- Giữ thứ tự cập nhật bảng nhất quán trong mọi service/trigger.
- Không giữ lock trên một bảng trong khi gọi code không liên quan rồi mới cập nhật bảng khác.
- Xem xét cascade và trigger khi phân tích thứ tự khóa.
- Nếu dùng stored procedure, kiểm tra thứ tự truy cập bên trong procedure.

Chuẩn hóa lock order là biện pháp phòng ngừa quan trọng, nhưng database vẫn có thể deadlock do index page, range lock hoặc các transaction khác. Cần kết hợp retry có giới hạn và quan sát deadlock.

## 18. Retry deadlock trong Spring Batch

Database thường chọn một transaction làm deadlock victim và trả lỗi cho ứng dụng. Nếu lỗi được phân loại là transient, Spring Batch có thể retry chunk/item theo cấu hình fault tolerance.

Ví dụ:

~~~java
return new StepBuilder("processWorkItemsStep", jobRepository)
        .<WorkItem, WorkItem>chunk(100, transactionManager)
        .reader(workItemReader)
        .processor(workItemProcessor)
        .writer(workItemWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

DeadlockLoserDataAccessException là kiểu exception thường gặp trong một số cấu hình Spring JDBC cũ. Exception được translate có thể khác theo phiên bản Spring Framework, database driver và vendor error code. Hãy kiểm tra root cause và exception translation thực tế trước khi cấu hình retry; không bắt mọi DataAccessException nếu lỗi đó không tạm thời.

Có thể bổ sung backoff để tránh các worker retry đồng loạt ngay lập tức:

~~~java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.backOffPolicy(new ExponentialBackOffPolicy())
~~~

API backoff và cách cấu hình cụ thể tùy phiên bản Spring Batch. Có thể cấu hình initial interval, multiplier và maximum interval phù hợp với thời gian transaction và tải database.

Retry chỉ xử lý lần deadlock cụ thể. Nếu tất cả worker liên tục khóa cùng tài nguyên theo cùng một pattern, retry sẽ làm tăng tải và thời gian Job mà không giải quyết nguyên nhân gốc.

## 19. Chunk rollback và tính idempotent

Khi deadlock victim bị rollback, toàn bộ transaction của chunk tương ứng có thể bị hoàn tác. Spring Batch có thể thực hiện lại phần xử lý theo retry policy.

Do đó, processor và writer cần an toàn khi được gọi lại:

- Không gửi email hoặc message không idempotent trực tiếp trong processor.
- Không gọi API tạo giao dịch bên ngoài mà không có idempotency key.
- Không tăng bộ đếm nghiệp vụ trong memory rồi coi đó là số item đã commit.
- Dùng unique constraint/business key để chống insert trùng.
- Đưa side effect ra outbox nếu cần phát event sau khi database commit.

Nếu writer cập nhật cùng database trong transaction chunk, rollback có thể hoàn tác update. Nhưng side effect tới hệ thống ngoài database không tự rollback. Khi retry, side effect đó có thể bị thực hiện hai lần.

Với update theo trạng thái, dùng điều kiện expected status/version để phát hiện item đã được xử lý bởi worker khác. Quy tắc retry phải phân biệt deadlock tạm thời với conflict nghiệp vụ.

## 20. Phân biệt retry deadlock với skip

Deadlock thường là lỗi transaction tạm thời và phù hợp với retry có giới hạn hơn là skip item. Skip một item chỉ vì database tạm thời không cấp lock có thể làm mất dữ liệu hợp lệ.

| Lỗi | Hành vi thường phù hợp |
|---|---|
| Deadlock victim | Retry transaction/chunk có giới hạn và backoff |
| Lock timeout | Phân tích blocker; retry nếu lỗi tạm thời và thao tác an toàn |
| Optimistic version conflict | Đọc lại hoặc xử lý conflict theo nghiệp vụ |
| Vi phạm dữ liệu cố định | Fail hoặc skip theo policy nghiệp vụ |
| SQL syntax/configuration error | Fail fast |
| Database unavailable | Retry theo chính sách hạ tầng, sau đó fail nếu vượt ngưỡng |

Nếu retry hết giới hạn, Step có thể thất bại để vận hành điều tra. Không nên tăng skipLimit để biến deadlock thành dữ liệu bị bỏ qua.

## 21. Chẩn đoán deadlock từ database

Khi deadlock xảy ra, cần lấy thông tin từ database thay vì chỉ xem stack trace của Spring Batch.

Các dữ liệu cần thu thập:

- Database engine và version.
- Isolation level của transaction.
- SQL statement của từng transaction.
- Table/index/row/page/key resource bị khóa.
- Transaction nào giữ lock và transaction nào chờ.
- Lock mode và thứ tự yêu cầu lock.
- Execution plan của query đọc/ghi.
- JobExecution ID, StepExecution ID, partition và chunk liên quan.
- Thời điểm bắt đầu transaction và thời điểm deadlock.

Deadlock graph hoặc deadlock report của database thường cho biết victim, owner, waiter và resource. Đây là nguồn quan trọng để xác định vòng chờ thực tế.

Ví dụ cách quan sát tùy engine:

- SQL Server có deadlock graph trong Extended Events hoặc system health session.
- PostgreSQL ghi deadlock details trong server log khi cấu hình log_lock_waits/deadlock logging phù hợp; pg_stat_activity và pg_locks hỗ trợ xem lock hiện tại.
- MySQL InnoDB cung cấp thông tin từ SHOW ENGINE INNODB STATUS và Performance Schema.
- Oracle có trace/event và view quản trị để phân tích session wait/lock.

Tên lệnh và quyền truy cập phụ thuộc database/version. Không chạy truy vấn quản trị tùy tiện trên production nếu chưa hiểu tác động; ưu tiên log/monitoring đã được cấu hình.

## 22. Log từ Spring Batch và ứng dụng

Log ứng dụng cần liên kết được lỗi database với execution cụ thể:

- Job name và JobExecution ID.
- Step name và StepExecution ID.
- Partition/worker identifier nếu có.
- Chunk hoặc business key liên quan.
- Exception type, SQLState và vendor error code.
- Retry attempt.
- Thời gian transaction/chunk.

Không log toàn bộ payload nếu chứa thông tin nhạy cảm. Business key và correlation ID thường đủ để liên kết với deadlock report.

Spring Batch metadata cung cấp read/write/skip counts và trạng thái StepExecution. Các bộ đếm này giúp khoanh vùng chunk/Step nhưng không thay thế deadlock graph của database.

## 23. Ví dụ cấu hình reader/writer cùng bảng

Ví dụ đơn giản dùng JdbcPagingItemReader để đọc theo ID và JdbcBatchItemWriter để cập nhật trạng thái:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<WorkItem> workItemReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<WorkItem>()
            .name("workItemReader")
            .dataSource(dataSource)
            .selectClause("select id, status, payload")
            .fromClause("from work_item")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", "READY"))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .pageSize(100)
            .rowMapper((rs, rowNum) -> new WorkItem(
                    rs.getLong("id"),
                    rs.getString("status"),
                    rs.getString("payload")))
            .saveState(true)
            .build();
}
~~~

Writer:

~~~java
@Bean
JdbcBatchItemWriter<WorkItem> workItemWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<WorkItem>()
            .dataSource(dataSource)
            .sql("""
                    UPDATE work_item
                    SET status = :newStatus,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                      AND status = :expectedStatus
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new BeanPropertySqlParameterSource(item))
            .assertUpdates(true)
            .build();
}
~~~

Model WorkItem trong ví dụ cần có các property id, expectedStatus và newStatus, hoặc provider phải tự tạo các tham số đó từ model thực tế. Đoạn code tập trung minh họa query và điều kiện update; cần điều chỉnh DTO/provider theo ứng dụng.

Đọc và cập nhật cùng bảng theo cách này cần được kiểm thử với dữ liệu đồng thời. sortKeys dùng khóa duy nhất giúp reader tiếp tục theo thứ tự ổn định. Nhưng khi writer đổi status, cần kiểm tra query provider, checkpoint và predicate để bảo đảm tập input không bị thay đổi theo cách làm bỏ sót record.

Nếu nhiều worker cùng chạy Step, cần phân vùng ID không chồng lấn hoặc dùng claim strategy. Chỉ thêm @StepScope không bảo đảm mỗi thread trong cùng Step có reader riêng.

## 24. Một thiết kế claim theo batch

Khi nhiều worker cùng lấy công việc, một thiết kế có thể dùng batch ID và claim token:

~~~sql
UPDATE work_item
SET status = 'IN_PROGRESS',
    batch_id = :batchId,
    claimed_by = :workerId,
    claimed_at = CURRENT_TIMESTAMP
WHERE id IN (
    SELECT id
    FROM work_item
    WHERE status = 'READY'
    ORDER BY id
    FETCH FIRST :batchSize ROWS ONLY
);
~~~

Đây chỉ là dạng SQL minh họa; syntax và tính nguyên tử của subquery/locking phụ thuộc database. Với concurrency cao, cần một câu lệnh claim an toàn theo engine, có khóa hoặc SKIP LOCKED/locking hint thích hợp, và kiểm tra update count.

Sau khi claim, worker đọc:

~~~sql
SELECT id, payload
FROM work_item
WHERE batch_id = :batchId
  AND claimed_by = :workerId
  AND status = 'IN_PROGRESS'
ORDER BY id;
~~~

Khi xử lý xong:

~~~sql
UPDATE work_item
SET status = 'PROCESSED',
    processed_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND batch_id = :batchId
  AND claimed_by = :workerId
  AND status = 'IN_PROGRESS';
~~~

Claim token giúp ngăn worker khác cập nhật nhầm item. Cần có lease expiration và quy trình thu hồi claim nếu worker chết. Nếu không có lease, row có thể mắc kẹt ở IN_PROGRESS mãi mãi.

## 25. Khi nào nên tách bảng hoặc tách Step?

Nếu đọc và cập nhật cùng bảng liên tục gây lock contention, có thể thay đổi kiến trúc:

- Tạo staging table chứa ID cần xử lý.
- Tách Step snapshot input và Step cập nhật trạng thái.
- Ghi kết quả vào bảng output riêng rồi merge ở Step cuối.
- Dùng queue hoặc bảng claim để phân phối work.
- Dùng read replica/snapshot nếu độ trễ dữ liệu chấp nhận được.
- Chuyển tác vụ tổng hợp sang Step chạy sau khi worker hoàn tất.

Đọc từ read replica có thể giảm cạnh tranh với writer trên primary, nhưng dữ liệu replica có độ trễ và không phù hợp nếu Job cần đọc ngay các thay đổi mới nhất hoặc phải claim row độc quyền. Không dùng replica như giải pháp thay thế cho transaction/claim semantics.

Tách bảng cũng có chi phí: thêm storage, cleanup, đối soát và xử lý dữ liệu dở dang. Chỉ áp dụng khi lợi ích về concurrency, audit và khả năng restart phù hợp yêu cầu hệ thống.

## 26. Kiểm thử deadlock và lock contention

Không nên chỉ test một lần chạy đơn luồng. Hãy tạo integration test với hai hoặc nhiều transaction đồng thời trên database engine thực tế.

Các kịch bản nên kiểm tra:

1. Hai worker cập nhật các row không giao nhau: không có deadlock ngoài dự kiến.
2. Hai worker cập nhật cùng row theo thứ tự ngược: xác nhận deadlock có thể xảy ra và retry hoạt động.
3. Locking reader giữ row trong lúc writer chạy: đo lock wait và xác nhận transaction kết thúc đúng.
4. Reader và writer dùng cùng bảng với predicate status thay đổi: xác nhận không bỏ sót item.
5. Partition range không chồng lấn: đối chiếu tổng business key.
6. Claim đồng thời: một item chỉ được một worker nhận.
7. Retry sau deadlock: không tạo duplicate hoặc side effect lặp.
8. Restart sau chunk rollback: checkpoint và trạng thái database nhất quán.
9. Transaction timeout: lỗi được phân loại đúng, không nhầm với deadlock.
10. Trigger/foreign key: deadlock graph không có resource ngoài dự kiến.

Dùng barrier/latch để đồng bộ thời điểm hai transaction bắt đầu, không dựa vào Thread.sleep() để hy vọng tạo ra race. Chạy test trên database/driver tương thích production vì H2 có locking và isolation semantics khác nhiều engine.

## 27. Checklist điều tra khi Job gặp deadlock

Khi Step báo deadlock, có thể lần lượt xác định:

1. Exception gốc là deadlock, lock timeout hay connection failure?
2. Database deadlock report cho biết transaction và resource nào?
3. Reader có dùng locking read hoặc isolation cao không?
4. Reader và writer dùng connection/transaction nào?
5. Có nhiều JobExecution/partition cùng đọc phạm vi không?
6. Các transaction có cập nhật row theo cùng thứ tự không?
7. Trigger, foreign key hoặc index nào tạo thêm lock?
8. Chunk và processor giữ transaction bao lâu?
9. Query plan có dùng index phù hợp không?
10. Retry có giới hạn và thao tác có idempotent không?
11. Có lỗi pagination/record bị bỏ sót ngoài deadlock không?
12. Restart có tiếp tục cùng input snapshot và checkpoint không?

Mục tiêu là tìm vòng chờ và điều kiện tạo ra nó, sau đó thay đổi thứ tự truy cập, phạm vi transaction, cách claim hoặc phân vùng dữ liệu. Không kết luận nguyên nhân chỉ từ tên Step hoặc việc reader/writer cùng dùng một bảng.

## 28. Các lỗi thường gặp

**Cho rằng đọc và ghi cùng bảng luôn gây deadlock:** SELECT thông thường trên MVCC có thể không chặn writer. Xác định locking behavior thực tế của database.

**Nhầm lock wait với deadlock:** một transaction chờ lock chưa chắc có vòng chờ. Dùng deadlock graph và lock monitoring.

**Dùng SELECT FOR UPDATE cho mọi reader:** giữ lock lâu có thể làm tăng contention. Chỉ dùng khi cần semantics claim/locking rõ ràng.

**Để processor chạy lâu trong transaction:** network call hoặc tính toán nặng làm lock tồn tại lâu hơn. Tách công việc hoặc giảm transaction duration khi có thể.

**Hai worker cập nhật row theo thứ tự khác nhau:** tạo vòng chờ. Chuẩn hóa thứ tự lock và partition dữ liệu không chồng lấn.

**Dùng offset pagination khi writer đổi predicate:** tập kết quả co lại có thể làm bỏ sót record. Đây là lỗi paging, không phải deadlock.

**Cho rằng @StepScope làm reader riêng cho từng thread:** scope tạo instance theo StepExecution, không phải theo từng thread trong Step.

**Tăng retry vô hạn:** deadlock lặp lại làm Job chậm và tăng tải database. Dùng retry limit, backoff và xử lý nguyên nhân gốc.

**Skip deadlock như lỗi dữ liệu:** item hợp lệ có thể bị mất. Deadlock thường cần retry transaction.

**Không kiểm tra trigger và foreign key:** deadlock có thể nằm ở bảng/index khác với bảng được reader truy vấn.

**Dùng read replica để claim dữ liệu:** replica có thể trễ và không cung cấp locking semantics cần thiết.

**Không kiểm tra restart sau rollback:** retry có thể xử lý lại item; cần idempotency và checkpoint nhất quán.

## Kết luận

Deadlock khi đọc và ghi cùng bảng trong Spring Batch không xuất phát đơn giản từ việc hai thao tác cùng chạm một bảng. Nó xảy ra khi các transaction tạo vòng chờ lock, thường do locking read, phạm vi dữ liệu giao nhau, thứ tự cập nhật khác nhau, transaction kéo dài hoặc trigger/index bổ sung. Hãy lấy deadlock graph của database, xác minh isolation và connection semantics của reader, chuẩn hóa thứ tự truy cập, chia partition không chồng lấn hoặc dùng claim/staging khi cần. Giảm transaction duration và dùng retry có giới hạn cùng backoff để xử lý deadlock tạm thời; bảo đảm processor/writer idempotent vì chunk có thể rollback và được thử lại. Đồng thời phân biệt deadlock với lock wait và lỗi pagination khi writer làm thay đổi predicate đọc. Kiểm thử concurrency, rollback và restart trên đúng database engine để xác nhận không mất hoặc ghi trùng item.
