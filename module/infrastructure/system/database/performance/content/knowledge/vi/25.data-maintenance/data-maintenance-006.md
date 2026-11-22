# Lưu trữ dữ liệu cũ, chính sách giữ dữ liệu và xóa theo lô

Dữ liệu trong cơ sở dữ liệu thường có vòng đời dài hơn thời gian nó được dùng thường xuyên. Đơn hàng đã hoàn tất, sự kiện ứng dụng, log nghiệp vụ, lịch sử thiết bị và dữ liệu đo đạc có thể tiếp tục tích lũy nhiều năm. Nếu giữ toàn bộ dữ liệu cũ trong các bảng phục vụ truy vấn trực tuyến, kích thước bảng và index tăng, cache bị pha loãng, truy vấn phải đọc nhiều trang hơn, backup lâu hơn và các thao tác bảo trì tốn nhiều tài nguyên.

Lưu trữ dữ liệu cũ (archiving), chính sách giữ dữ liệu (retention policy) và xóa theo lô (batch deletion/purge) giúp kiểm soát vòng đời dữ liệu. Một quy trình tốt xác định dữ liệu nào phải giữ, giữ trong bao lâu, khi nào chuyển sang tầng lưu trữ khác, khi nào được xóa và cách thực hiện mà không làm nghẽn workload trực tuyến. Quy trình cũng phải có khả năng tiếp tục sau lỗi, tránh xóa nhầm dữ liệu mới và chứng minh được số bản ghi đã lưu trữ hoặc xóa.

Trong phạm vi DATABASE_PERFORMANCE, bài học này tập trung vào cách thiết kế vòng đời dữ liệu, lựa chọn archive hay delete, chia công việc thành batch có giới hạn, tận dụng partition để loại bỏ dữ liệu hết hạn, xử lý khóa ngoại và transaction log, đồng thời đo tác động lên I/O, replication và truy vấn trực tuyến.

## 1. Vì sao cần chính sách giữ dữ liệu?

Khi dữ liệu tăng liên tục, chi phí không chỉ nằm ở dung lượng bảng. Các cấu trúc phụ trợ cũng tăng theo:

- Index lớn hơn, tốn bộ nhớ cache và I/O khi tìm kiếm hoặc cập nhật.
- Statistics phải đại diện cho tập dữ liệu lớn và có thể không mô tả tốt phân bố theo thời gian.
- Backup, restore, replication và kiểm tra toàn vẹn cần xử lý nhiều dữ liệu hơn.
- VACUUM, purge, checkpoint, log backup hoặc các tác vụ bảo trì phải xử lý nhiều thay đổi hơn.
- Truy vấn lịch sử có thể cạnh tranh I/O và CPU với giao dịch trực tuyến.
- Xóa hàng loạt có thể tạo lượng lớn WAL/redo/undo/transaction log, lock và replication lag.

Retention policy giới hạn lượng dữ liệu còn nằm trong từng tầng lưu trữ và xác định thời điểm dữ liệu được chuyển hoặc xóa. Nếu dữ liệu cũ vẫn cần để tra cứu, báo cáo hoặc kiểm toán, có thể chuyển sang archive hoặc tầng lưu trữ rẻ hơn. Nếu không còn mục đích hợp lệ để giữ, dữ liệu có thể được purge theo quy trình đã phê duyệt.

### Dữ liệu cũ không đồng nghĩa dữ liệu không còn giá trị

Một bản ghi có thể đã cũ đối với giao dịch trực tuyến nhưng vẫn cần cho:

- Kiểm toán và đối soát.
- Tranh chấp, bảo hành hoặc hỗ trợ khách hàng.
- Báo cáo theo kỳ.
- Yêu cầu pháp lý hoặc hợp đồng.
- Phân tích xu hướng dài hạn.
- Khôi phục hoặc điều tra sự cố.

Vì vậy, quyết định lưu trữ/xóa phải dựa trên mục đích sử dụng, thời hạn bắt buộc, quyền truy cập và yêu cầu khôi phục. Không chọn cutoff chỉ dựa trên việc bảng đã lớn.

## 2. Xây dựng retention policy

Một chính sách giữ dữ liệu cần xác định ít nhất:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Phạm vi dữ liệu | Bảng, tenant, loại sự kiện hoặc trạng thái nào thuộc chính sách? |
| Mốc thời gian | Tính tuổi theo created_at, occurred_at, closed_at hay một mốc khác? |
| Thời hạn | Giữ bao lâu trong DB trực tuyến, archive và backup? |
| Ngoại lệ | Có legal hold, tranh chấp, điều tra hoặc khách hàng đặc biệt không? |
| Đích archive | Bảng archive, database riêng, object storage hay data lake? |
| Quyền truy cập | Ai được đọc, xuất hoặc xóa dữ liệu đã lưu trữ? |
| Quy trình purge | Job nào thực hiện, theo lịch nào và với giới hạn tải nào? |
| Bằng chứng | Lưu manifest, số hàng, checksum, thời điểm và kết quả xác minh ra sao? |
| Khôi phục | Cần phục hồi một bản ghi, một khoảng thời gian hay toàn bộ archive? |

### Chọn đúng cột thời gian

Không phải mọi cột timestamp đều biểu diễn cùng một mốc:

- created_at: thời điểm bản ghi được tạo trong hệ thống.
- occurred_at: thời điểm sự kiện thực tế xảy ra.
- updated_at: lần cập nhật gần nhất.
- closed_at: thời điểm nghiệp vụ hoàn tất.
- ingested_at: thời điểm dữ liệu được nhận vào pipeline.

Ví dụ, log được gửi chậm có thể có occurred_at cách đây 90 ngày nhưng ingested_at chỉ mới vài phút. Nếu retention dựa trên ingested_at, log cũ có thể bị giữ lâu hơn dự kiến; nếu dựa trên occurred_at, dữ liệu đến muộn có thể bị purge ngay sau khi nhập. Chính sách phải chọn cột phù hợp với ý nghĩa nghiệp vụ.

### Múi giờ và ranh giới cutoff

Nên lưu timestamp theo một quy ước thống nhất, thường là UTC hoặc kiểu dữ liệu có semantics múi giờ rõ ràng. Cutoff nên được tính bằng thời điểm tuyệt đối, không dựa vào giờ địa phương của từng worker.

Ví dụ, nếu giữ dữ liệu 365 ngày:

```sql
-- :cutoff_utc được ứng dụng/job tính một lần cho cả lượt chạy
SELECT COUNT(*)
FROM events
WHERE occurred_at < :cutoff_utc;
```

Tính cutoff một lần rồi truyền vào mọi batch giúp ranh giới không trôi trong lúc job chạy. Nếu mỗi batch tự gọi CURRENT_TIMESTAMP trừ 365 ngày, các batch chạy qua thời điểm đổi ngày có thể dùng cutoff khác nhau.

### Legal hold và ngoại lệ

Một bản ghi đang bị giữ để điều tra hoặc theo yêu cầu pháp lý không được purge chỉ vì đã vượt retention period thông thường. Có thể biểu diễn trạng thái hold bằng bảng liên kết riêng hoặc cột hold_until/hold_reason, tùy mô hình. Predicate purge phải loại các bản ghi đang bị hold và phải kiểm tra lại trạng thái hold ngay trước khi xóa.

Không nên chỉ dựa vào cờ ở tầng ứng dụng nếu có nhiều đường ghi. Quy tắc bảo vệ cần được áp dụng nhất quán trong job, stored procedure và quyền truy cập. Việc gỡ legal hold phải có người có thẩm quyền, dấu vết audit và lý do.

## 3. Phân biệt archive, soft delete và hard delete

Ba thao tác này có mục tiêu khác nhau:

| Cách xử lý | Hành vi | Phù hợp khi |
|---|---|---|
| Archive | Chuyển bản ghi sang tầng/bảng lưu trữ khác | Dữ liệu vẫn cần tra cứu nhưng ít truy cập |
| Soft delete | Đánh dấu bản ghi không còn hoạt động | Cần khôi phục hoặc giữ tham chiếu trong ứng dụng |
| Hard delete/purge | Xóa bản ghi khỏi cấu trúc dữ liệu trực tuyến | Hết mục đích giữ hoặc đã có bản archive hợp lệ |

Soft delete thường không làm bảng nhỏ đi. Bản ghi vẫn chiếm dung lượng và có thể tiếp tục nằm trong index. Nếu mọi truy vấn phải lọc deleted_at IS NULL, index và statistics cần được thiết kế theo workload. Soft delete là trạng thái nghiệp vụ, không phải biện pháp giải phóng storage.

Archive cũng không tự động làm dữ liệu nguồn biến mất. Nếu chỉ sao chép sang bảng archive mà không purge nguồn, tổng dung lượng còn tăng. Quy trình cần xác định rõ thời điểm xác minh archive xong và thời điểm được phép xóa nguồn.

### Archive trước hay xóa trước?

Nếu dữ liệu phải được giữ, trình tự an toàn thường là:

1. Chọn tập bản ghi đủ điều kiện.
2. Ghi bản archive bền vững.
3. Xác minh số lượng và nội dung.
4. Ghi manifest/checkpoint.
5. Chỉ sau khi xác minh thành công mới xóa nguồn theo batch.
6. Đối chiếu kết quả và lưu bằng chứng.

Nếu xóa nguồn trước khi archive bền vững, một lỗi giữa hai bước có thể làm mất dữ liệu. Nếu archive và nguồn nằm ở hai hệ thống khác nhau, không có transaction phân tán nguyên tử mặc định; cần thiết kế idempotency và quy trình phục hồi.

## 4. Chọn cách tổ chức dữ liệu theo vòng đời

Có nhiều cách lưu dữ liệu cũ:

- Cùng bảng với dữ liệu nóng, nhưng partition theo thời gian.
- Bảng archive trong cùng database.
- Database hoặc cluster archive riêng.
- Object storage chứa file/columnar format kèm metadata và manifest.
- Data warehouse/lake phục vụ phân tích.
- Backup hoặc snapshot dài hạn khi yêu cầu chỉ là khôi phục toàn hệ thống.

Lựa chọn phụ thuộc vào tần suất truy cập, độ trễ chấp nhận được, chi phí, khả năng tìm kiếm, yêu cầu xóa và khả năng khôi phục.

### Bảng archive trong cùng database

Ưu điểm là dễ join, quyền truy cập và transaction copy/delete có thể nằm trong cùng database. Nhược điểm là archive vẫn chiếm storage, catalog, backup và có thể ảnh hưởng cache hoặc bảo trì nếu cùng cluster.

### Database archive riêng

Tách workload lịch sử khỏi OLTP chính, cho phép backup, retention và cấu hình tài nguyên riêng. Đổi lại, cần quản lý đồng bộ schema, quyền, kết nối, khả năng tra cứu liên database và phục hồi khi một bên lỗi.

### Object storage hoặc data lake

Phù hợp với dữ liệu ít cập nhật, truy cập theo lô và khối lượng lớn. Có thể lưu Parquet/CSV/JSON nén, nhưng phải có schema version, partition path, encryption, checksum, manifest và chính sách truy cập. Truy vấn từng bản ghi có thể chậm hơn DB; dữ liệu cần được nạp hoặc lập chỉ mục nếu yêu cầu tra cứu tương tác.

### Backup không thay thế archive

Backup nhằm khôi phục trạng thái hệ thống khi có sự cố. Archive nhằm giữ và truy cập một tập dữ liệu đã hết vòng đời trực tuyến. Backup có thể chứa dữ liệu đã xóa cho đến khi hết retention backup; điều đó không có nghĩa dữ liệu đã được archive theo cách có thể truy vấn từng bản ghi.

Nếu yêu cầu xóa dữ liệu theo quyền riêng tư, cần tính cả backup, bản sao, replica, export, cache và archive. Xóa một hàng trong bảng chính không đồng nghĩa mọi bản sao đã biến mất ngay lập tức.

## 5. Vì sao phải xóa theo lô?

Một câu DELETE lớn có thể ảnh hưởng toàn hệ thống:

```sql
DELETE FROM events
WHERE occurred_at < :cutoff_utc;
```

Nếu predicate khớp hàng triệu bản ghi, DB phải tìm hàng, kiểm tra ràng buộc, xóa mục index, ghi log và xử lý trigger/cascade. Transaction lớn có thể:

- Giữ khóa lâu và chặn giao dịch trực tuyến.
- Tạo transaction log/WAL/redo lớn.
- Tăng undo hoặc version cleanup.
- Làm replica chậm áp dụng log.
- Tạo I/O burst và tăng latency.
- Làm rollback tốn thời gian nếu lỗi.
- Gây autovacuum/purge hoặc checkpoint workload tăng sau đó.

Batch deletion chia tập dữ liệu thành nhiều transaction nhỏ. Mỗi batch chọn một số hàng, xóa, commit rồi mới tiếp tục. Cách này giới hạn lượng khóa và log mỗi transaction, tạo checkpoint tự nhiên và cho phép điều tiết tốc độ.

Batch không làm tổng công việc biến mất. Nó phân phối công việc theo thời gian để giảm tác động đỉnh lên workload khác.

## 6. Chọn tập dữ liệu ổn định cho mỗi batch

Một batch cần có tiêu chí chọn hàng ổn định và có thể tiếp tục sau lỗi. Tránh dùng OFFSET lớn:

```sql
-- Không phù hợp cho purge lớn
SELECT event_id
FROM events
WHERE occurred_at < :cutoff_utc
ORDER BY event_id
OFFSET 500000
LIMIT 1000;
```

OFFSET lớn thường phải đọc/bỏ qua nhiều hàng trước khi trả batch, khiến các batch sau càng tốn chi phí. Khi dữ liệu bị xóa trong lúc phân trang, vị trí offset còn có thể dịch chuyển, gây bỏ sót hoặc lặp hàng.

### Keyset batching

Keyset pagination tiếp tục từ khóa cuối đã xử lý:

```sql
SELECT event_id
FROM events
WHERE occurred_at < :cutoff_utc
  AND event_id > :last_event_id
ORDER BY event_id
LIMIT 1000;
```

Ví dụ này giả định event_id là khóa tăng đơn điệu và thứ tự đó phù hợp với tập dữ liệu. Nếu khóa không phản ánh thời gian hoặc không duy nhất, hãy dùng cặp khóa ổn định, ví dụ (occurred_at, event_id):

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at < :cutoff_utc
  AND (
      occurred_at > :last_time
      OR (occurred_at = :last_time AND event_id > :last_id)
  )
ORDER BY occurred_at, event_id
LIMIT 1000;
```

Index nên hỗ trợ predicate và thứ tự này, chẳng hạn index trên (occurred_at, event_id). Keyset giảm chi phí bỏ qua hàng và giúp job tiếp tục từ checkpoint rõ ràng.

### High-water mark

Khi bắt đầu một lượt purge, có thể ghi lại một upper bound (high-water mark) để giới hạn tập dữ liệu của lượt đó. Ví dụ, chọn max(event_id) tại thời điểm bắt đầu rồi chỉ xử lý khóa đến giá trị đó. Điều này ngăn các bản ghi mới được chèn trong lúc job chạy liên tục mở rộng phạm vi.

High-water mark chỉ phù hợp nếu khóa có thứ tự và không có bản ghi cũ được insert muộn với khóa lớn hơn cutoff nhưng timestamp cũ. Nếu dữ liệu đến muộn, cần một lượt sweep sau hoặc watermark theo event time/ingestion time. Không giả định khóa tăng dần đồng nghĩa dữ liệu đến đúng thứ tự thời gian.

## 7. Chỉ mục hỗ trợ retention và purge

Predicate retention thường lọc theo thời gian:

```sql
DELETE FROM events
WHERE occurred_at < :cutoff_utc;
```

Nếu bảng có index phù hợp, DB có thể tìm tập hàng cũ mà không quét toàn bảng. Một index phổ biến:

```sql
CREATE INDEX ix_events_occurred_event
ON events (occurred_at, event_id);
```

Index này có thể hỗ trợ lọc theo occurred_at và thứ tự ổn định theo event_id. Tuy nhiên, index cũng làm tăng chi phí insert/update và chiếm storage. Hãy xác nhận bằng execution plan và số hàng thực tế.

### Index không phải lúc nào cũng giúp

Nếu phần lớn bảng đã hết hạn, planner có thể chọn sequential scan vì đọc tuần tự rẻ hơn nhiều lần random access. Nếu chỉ một phần nhỏ hàng cũ cần xóa, index có thể hữu ích. Hãy đo:

- Tỷ lệ hàng đủ điều kiện so với tổng bảng.
- Số trang đọc và buffer hit.
- Số hàng ước lượng so với số hàng thực tế.
- Thời gian tìm khóa và thời gian xóa/index maintenance.
- I/O và log phát sinh.

### Index cho khóa ngoại

Khi xóa hàng cha, DB phải kiểm tra có hàng con tham chiếu hay không. Một số DBMS không tự động tạo index ở phía cột khóa ngoại. Nếu thiếu index, mỗi batch xóa cha có thể quét bảng con lớn, gây I/O và lock kéo dài.

Ví dụ:

```sql
CREATE INDEX ix_order_items_order_id
ON order_items (order_id);
```

Trước khi purge bảng cha, kiểm tra tất cả foreign key trỏ đến bảng đó và index ở bảng con. Index phù hợp giúp tìm hàng con nhanh hơn, nhưng cascade vẫn có thể xóa rất nhiều hàng và tạo lượng log lớn.

## 8. Batch DELETE trong PostgreSQL

PostgreSQL không có cú pháp DELETE ... LIMIT trực tiếp. Có thể chọn khóa theo CTE rồi xóa qua JOIN. Ví dụ:

```sql
WITH batch AS (
    SELECT event_id
    FROM events
    WHERE occurred_at < :cutoff_utc
    ORDER BY occurred_at, event_id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM events AS e
USING batch AS b
WHERE e.event_id = b.event_id
RETURNING e.event_id;
```

CTE chọn tối đa 1.000 hàng cũ và khóa chúng. DELETE dùng đúng tập khóa đã chọn. SKIP LOCKED cho phép nhiều worker lấy các hàng khác nhau mà không chờ những hàng đang bị worker khác khóa. RETURNING cung cấp danh sách khóa đã xóa để ghi nhận tiến độ.

Lưu ý:

- Đây là mẫu PostgreSQL; cú pháp và khả năng dùng SKIP LOCKED phụ thuộc phiên bản.
- ORDER BY tạo thứ tự chọn batch, nhưng không phải cam kết thứ tự vật lý của DELETE.
- Cần index hỗ trợ (occurred_at, event_id).
- Nếu có trigger hoặc foreign key cascade, số công việc thực tế có thể lớn hơn số hàng cha được trả về.
- Nếu worker khác đang khóa các hàng cũ, SKIP LOCKED có thể bỏ qua chúng. Job phải tiếp tục quét lại để xử lý các hàng còn lại sau khi lock được giải phóng.
- Khi không lấy được hàng nào, cần phân biệt “không còn hàng đủ điều kiện” với “mọi hàng còn lại đang bị khóa” nếu workload có cạnh tranh.

Mỗi lần chạy statement ở autocommit có thể là một transaction batch. Nếu cần ghi checkpoint cùng việc xóa, đặt DELETE và checkpoint trong cùng transaction.

## 9. Batch DELETE trong MySQL InnoDB

MySQL hỗ trợ ORDER BY và LIMIT trong DELETE đơn bảng:

```sql
DELETE FROM events
WHERE occurred_at < ?
ORDER BY occurred_at, event_id
LIMIT 1000;
```

Lệnh trên xóa tối đa 1.000 hàng đủ điều kiện theo thứ tự đã chọn. Ứng dụng có thể commit từng lệnh nếu autocommit hoặc transaction được quản lý theo batch.

Nếu nhiều worker cần chia hàng, có thể dùng transaction để SELECT khóa chính với FOR UPDATE SKIP LOCKED (phiên bản/engine hỗ trợ), sau đó DELETE theo tập ID đã lấy:

```sql
START TRANSACTION;

SELECT event_id
FROM events
WHERE occurred_at < ?
ORDER BY occurred_at, event_id
LIMIT 1000
FOR UPDATE SKIP LOCKED;

-- Ứng dụng truyền tập ID vừa chọn vào DELETE trong cùng transaction.
DELETE FROM events
WHERE event_id IN (...);

COMMIT;
```

Phần IN (...) là placeholder minh họa; ứng dụng phải bind tham số hoặc dùng bảng tạm/staging phù hợp, không ghép chuỗi đầu vào. SELECT và DELETE phải ở cùng transaction/connection để giữ khóa đã lấy.

InnoDB có thể giữ record lock và gap/next-key lock tùy isolation, index và predicate. Hãy kiểm tra EXPLAIN, lock wait và deadlock. SKIP LOCKED bỏ qua hàng đang khóa nên job cần vòng sweep để xử lý những hàng bị bỏ qua.

## 10. Batch DELETE trong SQL Server

SQL Server có thể chọn một batch trong CTE rồi DELETE qua CTE:

```sql
;WITH batch AS (
    SELECT TOP (@batch_size) *
    FROM dbo.Events WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE OccurredAt < @cutoff_utc
    ORDER BY OccurredAt, EventId
)
DELETE FROM batch;
```

UPDLOCK yêu cầu khóa cập nhật khi chọn hàng, READPAST có thể bỏ qua hàng đang bị khóa bởi transaction khác, còn ROWLOCK gợi ý dùng khóa hàng. ROWLOCK là hint, không phải bảo đảm tuyệt đối; READPAST có giới hạn khi dùng với row-versioning isolation và có thể cần READCOMMITTEDLOCK theo cấu hình. Hãy xác minh đúng isolation level và phiên bản SQL Server.

Một batch nên chạy trong transaction ngắn. Có thể lặp lệnh cho đến khi không còn hàng bị xóa, ghi số hàng bằng @@ROWCOUNT ngay sau DELETE:

```sql
DECLARE @deleted int = 1;

WHILE @deleted > 0
BEGIN
    ;WITH batch AS (
        SELECT TOP (1000) *
        FROM dbo.Events WITH (UPDLOCK, READPAST, ROWLOCK)
        WHERE OccurredAt < @cutoff_utc
        ORDER BY OccurredAt, EventId
    )
    DELETE FROM batch;

    SET @deleted = @@ROWCOUNT;
    -- Có thể WAITFOR DELAY giữa các batch theo chính sách điều tiết.
END;
```

Ví dụ cần được điều chỉnh để mỗi batch commit riêng nếu mục tiêu là giới hạn transaction log và thời gian khóa. Nếu toàn bộ vòng WHILE nằm trong một transaction ngoài, việc lặp không giải phóng khóa hoặc log cho đến khi transaction ngoài commit.

## 11. Batch DELETE trong Oracle

Oracle có thể dùng cursor với FOR UPDATE SKIP LOCKED và PL/SQL bulk processing để nhiều worker lấy các hàng chưa bị worker khác khóa. Ý tưởng là mở cursor chọn ROWID theo cutoff, fetch theo lô, xóa các ROWID đã lấy bằng FORALL, rồi commit sau mỗi batch.

Mẫu PL/SQL minh họa:

```sql
DECLARE
    CURSOR c_old IS
        SELECT ROWID
        FROM events
        WHERE occurred_at < :cutoff_utc
        ORDER BY occurred_at, event_id
        FOR UPDATE SKIP LOCKED;

    TYPE rowid_tab IS TABLE OF ROWID;
    l_rowids rowid_tab;
BEGIN
    LOOP
        OPEN c_old;
        FETCH c_old BULK COLLECT INTO l_rowids LIMIT 1000;
        CLOSE c_old;
        EXIT WHEN l_rowids.COUNT = 0;

        FORALL i IN 1 .. l_rowids.COUNT
            DELETE FROM events
            WHERE ROWID = l_rowids(i);

        COMMIT;
    END LOOP;
END;
/
```

Cursor được mở lại cho mỗi batch để tránh tiếp tục fetch từ một cursor FOR UPDATE sau COMMIT. Các hàng đã fetch được khóa trong transaction hiện tại; đóng cursor không thay thế COMMIT. Đây là mẫu định hướng, cần kiểm tra cú pháp, bind variable và hành vi cursor/lock theo phiên bản Oracle đang dùng. Không dùng ROWID làm checkpoint bền vững qua di chuyển hàng hoặc tái tổ chức bảng; lưu khóa nghiệp vụ/primary key cho tiến độ.

Một cách khác là chọn khóa theo lô trong transaction, xóa đúng tập đã lấy rồi commit. Cần xác minh SKIP LOCKED, bulk collect và FORALL phù hợp với phiên bản, quyền và hình dạng truy vấn.

## 12. Chọn batch size và điều tiết tốc độ

Batch size quyết định số hàng được xóa trong một transaction. Batch quá lớn tạo lock/log burst; batch quá nhỏ làm tăng số lần commit, round trip và overhead điều phối.

Không có batch size tối ưu chung. Hãy bắt đầu bằng giá trị nhỏ, đo tác động rồi tăng/giảm theo workload.

Các yếu tố ảnh hưởng:

- Kích thước hàng và số index cần cập nhật.
- Số foreign key, trigger và cascade.
- Tốc độ ghi log và checkpoint.
- Replication throughput và lag.
- I/O latency và buffer cache.
- Số worker chạy đồng thời.
- Mức độ cạnh tranh với truy vấn trực tuyến.
- Thời hạn hoàn thành purge.

### Điều chỉnh theo tín hiệu hệ thống

Job có thể tăng batch khi:

- Lock wait thấp.
- Transaction log còn headroom.
- Replica bắt kịp.
- p95/p99 của workload trực tuyến ổn định.
- I/O queue và CPU còn dư.

Giảm batch hoặc tạm dừng khi:

- Replication lag vượt ngưỡng.
- Transaction log gần đầy hoặc log backup không theo kịp.
- Lock timeout/deadlock tăng.
- p95/p99 của API tăng.
- I/O latency hoặc queue depth tăng mạnh.
- Backup, checkpoint hoặc bảo trì khác đang chạy.

### Throttle và khoảng nghỉ

Một job có thể nghỉ ngắn giữa các batch để nhường tài nguyên. Khoảng nghỉ cố định đơn giản nhưng không phản ứng với tải. Cơ chế adaptive throttling có thể dựa trên replica lag, log utilization, I/O latency hoặc p95 API.

Giới hạn tốc độ cần có ngưỡng tối thiểu/tối đa và hysteresis để tránh dao động. Không để một metric đơn lẻ điều khiển tốc độ nếu metric đó không phản ánh đúng nút thắt.

## 13. Transaction boundary và checkpoint

Mỗi batch nên là một đơn vị commit độc lập khi nghiệp vụ cho phép. Sau commit, job ghi checkpoint để biết đã xử lý đến đâu.

Một checkpoint có thể gồm:

- job_id và policy_version.
- cutoff_utc cố định.
- high_water_mark nếu sử dụng.
- last_processed_key hoặc batch sequence.
- số hàng đã archive/xóa.
- thời điểm bắt đầu/kết thúc batch.
- trạng thái RUNNING, PAUSED, COMPLETED hoặc FAILED.
- thông tin lỗi và số lần retry.

### Ghi checkpoint cùng transaction

Nếu checkpoint được ghi trong cùng database, có thể commit thay đổi dữ liệu và checkpoint trong cùng transaction:

```sql
BEGIN;

-- Chọn và xóa một batch đủ điều kiện.
-- Ghi tiến độ/checkpoint tương ứng.

UPDATE maintenance_jobs
SET last_key = :last_key,
    deleted_rows = deleted_rows + :batch_count,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id;

COMMIT;
```

Nếu transaction rollback, cả xóa và checkpoint cùng rollback. Nếu checkpoint được ghi trước khi xóa commit, job có thể đánh dấu đã xử lý nhưng dữ liệu vẫn còn. Nếu ghi sau commit ở transaction khác, lỗi giữa hai bước có thể làm job chạy lại một batch; vì vậy thao tác phải idempotent và checkpoint phải cho phép xác định trạng thái thật.

### Tiến độ không nhất thiết là một khóa đơn

Với dữ liệu đến muộn hoặc nhiều worker chạy song song, một last_key toàn cục có thể không đủ. Có thể dùng bảng batch manifest với các khoảng khóa hoặc partition, trạng thái claim/lease và thời hạn lease. Worker nhận một khoảng, xử lý xong rồi đánh dấu hoàn tất. Lease giúp worker khác tiếp tục khi worker trước chết.

Không đánh dấu một khoảng hoàn tất khi còn hàng bị SKIP LOCKED hoặc lỗi chưa xử lý. Có thể cần trạng thái PENDING_RECHECK để chạy sweep cuối.

## 14. Archive an toàn trước khi purge nguồn

Archive cần bảo đảm bản lưu đầy đủ và có thể khôi phục. Quy trình tối thiểu:

1. Chọn batch theo cutoff và khóa ổn định.
2. Sao chép các cột cần giữ sang archive với khóa nguồn và metadata.
3. Xử lý conflict theo idempotency key hoặc unique constraint.
4. Xác minh số hàng và dữ liệu quan trọng.
5. Ghi manifest/checkpoint.
6. Xóa nguồn theo đúng tập khóa đã archive.
7. Đối chiếu nguồn và archive sau batch.

### Archive cùng database

Nếu bảng archive và nguồn nằm trong cùng DB, có thể INSERT ... SELECT rồi DELETE trong một transaction:

```sql
BEGIN;

INSERT INTO events_archive (
    event_id, tenant_id, occurred_at, payload, archived_at
)
SELECT
    event_id, tenant_id, occurred_at, payload, CURRENT_TIMESTAMP
FROM events
WHERE occurred_at < :cutoff_utc
  AND event_id > :last_event_id
ORDER BY event_id
LIMIT 1000;

-- Sau khi xác định đúng tập ID đã sao chép,
-- xóa nguồn trong cùng transaction.

COMMIT;
```

Đoạn trên là ý tưởng; LIMIT trong INSERT ... SELECT và cách lấy chính xác tập khóa vừa archive khác nhau giữa DBMS. Trong triển khai thực tế, nên chọn ID batch trước trong CTE hoặc bảng tạm, INSERT từ đúng tập ID đó, rồi DELETE cùng tập trong cùng transaction. Không chạy hai predicate độc lập có thể chọn hai tập khác nhau.

### Archive sang object storage hoặc database khác

Không thể dựa vào transaction DB cục bộ để atomically commit cả object storage và database. Một quy trình có thể:

1. Claim batch và ghi manifest trạng thái EXPORTING.
2. Đọc dữ liệu theo snapshot/khóa ổn định.
3. Ghi file/object với tên duy nhất theo job và batch.
4. Tính checksum, số hàng và xác minh object đọc lại được.
5. Đánh dấu manifest ARCHIVED.
6. Chỉ sau đó mới purge nguồn.

Nếu worker chết sau khi ghi object nhưng trước khi cập nhật manifest, lần chạy lại cần nhận ra object đã tồn tại và xác minh nó thay vì tạo bản sao không kiểm soát. Nếu manifest đã ARCHIVED nhưng nguồn chưa xóa, purge có thể tiếp tục an toàn.

### Manifest archive

Manifest nên lưu:

- archive_id, job_id và policy version.
- Nguồn database/table/partition.
- Khoảng khóa hoặc cutoff.
- Số hàng và dung lượng byte.
- Schema version/format version.
- Object URI hoặc vị trí archive.
- Checksum/hash và thuật toán.
- Encryption/key reference.
- Thời điểm tạo, xác minh và người/quy trình thực hiện.
- Trạng thái export, verified, purged hoặc failed.

Không ghi payload nhạy cảm vào log manifest nếu không cần. Manifest cần đủ để kiểm tra và khôi phục nhưng phải tuân theo chính sách quyền truy cập.

## 15. Kiểm tra tính toàn vẹn của archive

Đếm số hàng là bước đầu, không phải bằng chứng đầy đủ rằng dữ liệu giống nhau.

Các cách xác minh:

- So sánh count theo batch và theo partition.
- So sánh min/max key và khoảng thời gian.
- So sánh checksum theo từng nhóm khóa.
- Kiểm tra các cột bắt buộc, NULL và encoding.
- Đọc thử một mẫu bản ghi từ archive.
- Khôi phục thử vào môi trường tạm và chạy truy vấn kiểm tra.
- Đối chiếu tổng tiền, số lượng hoặc invariant nghiệp vụ.

Với dữ liệu lớn, checksum toàn bộ một bảng có thể tốn nhiều I/O. Chia checksum theo partition hoặc key range để phát hiện vùng sai và chạy lại có mục tiêu. Hash cần canonicalize dữ liệu trước khi tính: cùng thứ tự cột, encoding, format timestamp, biểu diễn NULL và thứ tự hàng.

### Không purge khi xác minh chưa đạt

Nếu count/checksum không khớp, dừng purge batch liên quan. Ghi lỗi, giữ nguồn và cho phép export lại. Không chuyển trạng thái ARCHIVED chỉ vì file đã được upload thành công; cần xác nhận file hoàn chỉnh, có thể đọc và phù hợp manifest.

### Khôi phục phải được thử

Archive không hữu ích nếu không thể khôi phục. Định kỳ thử:

- Giải mã bằng key còn hiệu lực.
- Đọc schema version.
- Nạp một batch vào môi trường thử.
- Kiểm tra count/checksum và truy vấn nghiệp vụ.
- Đo thời gian phục hồi.

RTO/RPO của archive có thể khác database trực tuyến; cần xác định trước với người dùng dữ liệu.

## 16. Partitioning để loại bỏ dữ liệu hết hạn

Nếu bảng rất lớn và dữ liệu có vòng đời theo thời gian, partitioning có thể giảm chi phí purge. Ví dụ, chia bảng events theo tháng hoặc ngày:

```text
events
  ├── events_2026_01
  ├── events_2026_02
  ├── events_2026_03
  └── events_2026_04
```

Khi toàn bộ partition đã vượt retention, có thể detach/drop partition thay vì DELETE từng hàng. Thao tác metadata thường nhanh hơn rất nhiều so với xóa hàng và cập nhật từng index entry.

### Thiết kế partition key

Partition key nên phản ánh:

- Cột thời gian dùng trong retention predicate.
- Phân bố truy vấn và pruning.
- Độ lớn dữ liệu mỗi partition.
- Khả năng quản lý index và constraint.
- Tần suất tạo partition mới.
- Yêu cầu uniqueness và foreign key.

Partition quá nhỏ tạo nhiều object và tăng chi phí catalog/plan; partition quá lớn làm archive/purge tốn thời gian và giảm khả năng pruning. Độ dài kỳ (ngày, tuần, tháng) phải dựa trên tốc độ tăng dữ liệu và yêu cầu vận hành.

### PostgreSQL

PostgreSQL hỗ trợ partitioned table theo RANGE/LIST/HASH. Có thể DETACH PARTITION rồi archive hoặc DROP partition khi hết hạn:

```sql
ALTER TABLE events
DETACH PARTITION events_2025_01;

-- Sau khi archive và xác minh, có thể:
DROP TABLE events_2025_01;
```

Các biến thể DETACH PARTITION có khác biệt về khóa và mức độ đồng bộ theo phiên bản. Partitioned table yêu cầu khóa/unique constraint có những giới hạn liên quan đến partition key. Foreign key, index và thao tác detach cần được kiểm tra theo phiên bản.

Nếu cần archive trước khi drop, detach partition để nó không còn nằm trong bảng trực tuyến, sau đó copy/backup/verify từ partition detached rồi mới drop. Trong thời gian detached, ứng dụng không còn nhìn thấy dữ liệu đó qua parent table.

### MySQL

MySQL hỗ trợ partitioning và có thể dùng ALTER TABLE ... DROP PARTITION để loại bỏ partition hết hạn:

```sql
ALTER TABLE events
DROP PARTITION p2025_01;
```

DROP PARTITION là thao tác phá hủy dữ liệu trong partition. Cần xác minh đúng tên và ranh giới partition trước khi chạy, đồng thời kiểm tra giới hạn partitioning, unique key, foreign key và engine của phiên bản MySQL. Không coi DROP PARTITION là archive; nếu cần giữ dữ liệu, phải export và xác minh trước.

### SQL Server

SQL Server có thể dùng partition switching để chuyển partition sang bảng staging có cấu trúc tương thích, sau đó archive hoặc truncate staging. Partition switch là thao tác metadata trong điều kiện phù hợp, nhưng yêu cầu schema, index, constraint và filegroup tương thích. Có thể cần CHECK constraint chứng minh phạm vi dữ liệu và các partition boundary chính xác.

Không switch partition đang có tham chiếu hoặc index không tương thích. Hãy thử trong môi trường gần production và xác minh khóa, schema, filegroup và quyền.

### Oracle

Oracle hỗ trợ các thao tác partition maintenance như EXCHANGE PARTITION, TRUNCATE PARTITION và DROP PARTITION. Có thể exchange partition với bảng staging để export hoặc xử lý riêng, sau đó truncate/drop theo chính sách. Global index có thể cần maintenance hoặc rebuild/update global indexes tùy thao tác.

Trước khi chạy, kiểm tra local/global index, constraint, foreign key, interval partition và tùy chọn UPDATE GLOBAL INDEXES theo phiên bản. Thao tác partition có thể nhanh nhưng vẫn cần quản lý metadata, index và archive.

## 17. Partitioning không thay thế retention policy

Partitioning là cách tổ chức vật lý, không phải quyết định dữ liệu nào được giữ. Một partition tháng 1 chỉ được drop khi:

- Toàn bộ dữ liệu trong partition đã hết hạn.
- Không có legal hold hoặc ngoại lệ.
- Archive đã được xác minh nếu cần lưu.
- Các tham chiếu và ràng buộc đã được xử lý.
- Backup/replica và quy trình khôi phục đã được cân nhắc.
- Có phê duyệt hoặc quyền thực hiện theo chính sách.

Nếu retention cutoff nằm giữa partition, không thể drop cả partition mà không xóa nhầm dữ liệu còn hạn. Khi đó cần purge phần đầu partition theo batch, hoặc chia partition nhỏ hơn ở thiết kế tương lai.

Partition pruning giúp truy vấn đọc chỉ chạm partition cần thiết nếu predicate phù hợp. Nhưng nếu truy vấn không lọc theo partition key hoặc dùng biểu thức khiến planner không pruning được, nó vẫn có thể quét nhiều partition.

## 18. Foreign key, cascade và thứ tự purge

Xóa dữ liệu cha có thể bị chặn bởi foreign key hoặc kích hoạt ON DELETE CASCADE. Ví dụ:

```sql
orders
  └── order_items
        └── item_adjustments
```

Xóa một hàng orders có thể kéo theo nhiều hàng order_items và item_adjustments. Một batch 1.000 đơn hàng có thể xóa hàng trăm nghìn hàng con, làm log và thời gian transaction vượt xa dự kiến.

### Xác định thứ tự xóa

Nếu không dùng cascade, thường phải xóa bảng con trước bảng cha:

1. Xóa hoặc archive dữ liệu ở bảng con sâu nhất.
2. Xóa các bảng con cấp trên.
3. Xóa bảng cha.

Thứ tự cụ thể phụ thuộc graph foreign key và quy tắc nghiệp vụ. Có thể dùng staging key list để xác định tập cha rồi xử lý từng tầng con theo cùng batch.

### Index phía foreign key

Index ở cột tham chiếu giúp DB tìm con nhanh khi kiểm tra/xóa cha. Thiếu index có thể biến một batch nhỏ thành nhiều scan lớn. Hãy kiểm tra cả index ghép và thứ tự cột.

### Cascade có thể tạo transaction lớn

ON DELETE CASCADE thuận tiện nhưng có thể tạo lượng xóa lớn trong một statement. Nếu cần kiểm soát batch, có thể purge con theo batch trước rồi xóa cha khi không còn tham chiếu. Không thay đổi cascade chỉ vì hiệu năng nếu điều đó làm mất quy tắc toàn vẹn; cần đánh giá mọi đường ghi.

## 19. Trigger, audit và CDC

DELETE có thể kích hoạt trigger, audit log, change data capture hoặc stream replication. Các cơ chế này có thể tạo thêm ghi và I/O.

Trước khi purge, xác định:

- Trigger nào chạy theo từng hàng hoặc statement.
- Có audit yêu cầu ghi lại actor, thời điểm và lý do không.
- CDC hoặc logical replication có gửi từng delete không.
- Downstream consumer có xử lý lượng delete lớn không.
- Có retention riêng cho audit log và CDC slot/queue không.

Không tắt trigger hoặc audit để tăng tốc nếu chưa đánh giá yêu cầu toàn vẹn và kiểm toán. Nếu cần tối ưu, có thể dùng đường maintenance được phê duyệt, ghi manifest/audit tương đương và kiểm chứng consumer downstream.

## 20. Tác động lên transaction log, WAL, undo và storage

Xóa hàng là một thay đổi ghi. Database cần lưu thông tin đủ để phục hồi transaction, rollback và đồng bộ replica.

### PostgreSQL

DELETE tạo tuple version mới về mặt MVCC và ghi WAL. Không gian của tuple đã xóa chưa lập tức được trả lại hệ điều hành; VACUUM đánh dấu không gian có thể tái sử dụng khi không còn snapshot cần phiên bản cũ. Autovacuum có thể phải xử lý nhiều dead tuple sau purge lớn. Transaction hoặc replication slot giữ xmin cũ có thể trì hoãn cleanup.

Sau purge, bảng có thể không nhỏ lại trên filesystem. VACUUM thường giúp tái sử dụng không gian trong relation; VACUUM FULL hoặc rewrite có thể trả dung lượng về hệ điều hành nhưng cần khóa mạnh và I/O lớn. Không chạy VACUUM FULL ngay sau mọi purge nếu chưa có kế hoạch bảo trì.

Theo dõi dead tuples, autovacuum, table/index bloat, WAL generation, replication slot retention và replica lag.

### MySQL InnoDB

InnoDB ghi undo/redo và giữ phiên bản cũ cần thiết cho transaction consistent read. Purge thread dọn undo history khi không còn transaction cần phiên bản cũ. Transaction dài có thể làm history list length tăng và purge chậm.

DELETE lớn có thể tăng redo, undo, binlog và replica apply workload. Dung lượng file tablespace không nhất thiết giảm ngay sau khi xóa; phần trống có thể được tái sử dụng. OPTIMIZE TABLE hoặc rebuild có thể cần thêm dung lượng và khóa, tùy cấu hình/phiên bản.

Theo dõi history list length, undo tablespace, redo/binlog throughput, replica lag và thời gian transaction.

### SQL Server

DELETE ghi vào transaction log và có thể tạo nhiều log record cho hàng và index. Transaction lớn giữ log space cho đến khi điều kiện truncation cho phép; trong recovery model FULL, log backup cần được chạy đúng lịch. Một transaction lớn có thể làm log file tăng hoặc đầy.

Theo dõi log used percent, log reuse wait, log backup, VLF, lock escalation, version store nếu dùng row versioning và replica/availability group send/redo queue.

### Oracle

DELETE tạo undo và redo. Undo cần cho rollback và consistent read; transaction lớn có thể tăng áp lực undo tablespace và làm phát sinh snapshot too old cho truy vấn dài nếu undo cần thiết không còn. Redo được chuyển qua archive log và Data Guard/replication theo cấu hình.

Theo dõi undo usage, redo generation, archive destination, log switch, apply lag và thời gian transaction.

### Xóa không đồng nghĩa giảm file ngay

Nhiều DBMS giữ lại phần không gian trống trong datafile để tái sử dụng. Điều này thường tốt hơn việc liên tục shrink/rebuild vì tránh tạo I/O và phân mảnh mới. Nếu cần trả dung lượng về hệ điều hành, phải lên kế hoạch riêng, tính thời gian khóa, dung lượng tạm và tác động đến workload.

## 21. Replication và downstream systems

Batch purge tạo ra log hoặc sự kiện xóa cần được replica và consumer áp dụng. Nếu tốc độ xóa vượt khả năng apply, replication lag tăng:

- Replica đọc có thể trả dữ liệu cũ lâu hơn.
- Failover có thể bị trì hoãn hoặc mất mục tiêu RPO nếu không theo kịp.
- CDC consumer hoặc data warehouse có thể có backlog.
- Log/WAL/archive cần giữ lâu hơn và chiếm storage.

Đo lag trước, trong và sau mỗi batch. Nếu lag vượt ngưỡng, giảm tốc độ hoặc tạm dừng purge. Nếu có nhiều replica, theo dõi replica chậm nhất hoặc replica phục vụ workload quan trọng.

Với archive pipeline, cần đảm bảo consumer nhận đủ delete hoặc tombstone để không giữ bản sao đã hết hạn trái với policy. Retention phải được truyền xuống mọi tầng lưu trữ, không chỉ database nguồn.

## 22. Job vận hành an toàn và khả năng chạy lại

Retention job thường chạy theo lịch, có thể bị khởi động lại, chạy trùng hoặc dừng giữa chừng. Thiết kế phải chịu được các tình huống này.

### Idempotency

Một batch chạy lại không được tạo bản archive trùng hoặc xóa dữ liệu ngoài phạm vi. Có thể dùng:

- Khóa archive duy nhất theo source key và policy version.
- Manifest với batch_id duy nhất.
- INSERT ... ON CONFLICT/ignore hoặc MERGE theo semantics DBMS.
- Trạng thái batch rõ ràng và lease.
- Checkpoint bền vững.
- Xóa nguồn chỉ sau khi archive đã verified.

### Ngăn hai job cùng chạy

Có thể dùng scheduler lease, advisory lock, bảng job control hoặc distributed lock. Lease nên có thời hạn và heartbeat; worker chết thì lease hết hạn để worker khác tiếp tục. Nếu dùng session advisory lock, phải lưu ý proxy/pooling và bảo đảm lock gắn với kết nối chuyên dụng phù hợp.

### Hủy job an toàn

Khi cần dừng:

- Ngừng nhận batch mới.
- Cho batch hiện tại commit/rollback theo quy tắc.
- Ghi checkpoint cuối cùng.
- Giải phóng lease/lock.
- Để job tiếp theo tiếp tục từ checkpoint.

Không hủy giữa lúc archive object chưa hoàn chỉnh rồi đánh dấu batch đã xong. Dùng trạng thái tạm và kiểm tra object trước khi tiếp tục.

### Giới hạn thời gian chạy

Job nên có thời gian tối đa hoặc cửa sổ bảo trì. Nếu không hoàn thành, nó có thể tiếp tục ở lần chạy sau. Cần tránh chạy chồng lấn với chính nó hoặc với backup, index rebuild, partition maintenance và các job nặng khác.

## 23. Quy trình điều tra khi purge làm chậm database

1. **Xác nhận phạm vi.** Job đang xóa bảng/partition nào, cutoff nào, batch size và số worker bao nhiêu?
2. **Đo tác động.** Throughput purge, p95/p99 API, CPU, I/O, log generation và replication lag.
3. **Xem execution plan.** Predicate có dùng index/partition pruning không? Số hàng ước lượng và thực tế ra sao?
4. **Kiểm tra khóa.** Waiter, blocker, lock escalation, deadlock và transaction age.
5. **Kiểm tra ràng buộc.** Foreign key, index con, cascade và trigger.
6. **Kiểm tra log/undo.** Log utilization, WAL/redo, undo history và tốc độ backup/apply.
7. **Kiểm tra storage.** IOPS, throughput, latency, queue depth và dung lượng trống.
8. **Điều chỉnh batch.** Giảm batch hoặc worker, thêm khoảng nghỉ và giới hạn tốc độ.
9. **Chọn chiến lược phù hợp.** Dùng partition drop/switch nếu toàn partition hết hạn; dùng batch DELETE nếu cutoff nằm giữa partition.
10. **Đo lại.** So sánh cùng workload và xác minh dữ liệu còn hạn không bị tác động.

Không tăng batch chỉ vì job cần hoàn tất nhanh hơn. Nếu DB đang bị giới hạn bởi log, I/O hoặc replica apply, batch lớn hơn có thể làm thời gian tổng dài hơn do blocking và retry.

## 24. Ví dụ thiết kế retention cho bảng sự kiện

Giả sử bảng events nhận 20 triệu sự kiện mỗi tháng. Yêu cầu:

- Giữ 90 ngày trong database OLTP.
- Giữ 2 năm trong archive có thể tra cứu.
- Không purge sự kiện đang bị legal hold.
- Chỉ xóa nguồn sau khi archive được xác minh.

Một quy trình có thể:

1. Tính cutoff UTC cố định cho lượt chạy.
2. Chọn các event trước cutoff, loại event đang hold.
3. Chia theo tháng/partition nếu bảng đã partition theo occurred_at.
4. Với partition đã hoàn toàn hết hạn, export/verify rồi detach/drop.
5. Với phần dữ liệu nằm trong partition hiện tại chưa hết hạn hoàn toàn, dùng keyset batch.
6. Ghi archive manifest và checksum theo batch.
7. Sau khi verified, xóa đúng event_id đã archive.
8. Commit checkpoint và ghi số hàng.
9. Theo dõi WAL/log, replica lag và p95 API.
10. Chạy sweep cuối để xử lý hàng bị SKIP LOCKED hoặc dữ liệu đến muộn.

### Điều kiện xóa mẫu

```sql
DELETE FROM events
WHERE occurred_at < :cutoff_utc
  AND NOT EXISTS (
      SELECT 1
      FROM event_legal_holds AS h
      WHERE h.event_id = events.event_id
        AND h.released_at IS NULL
  );
```

Predicate này thể hiện quy tắc loại trừ legal hold, nhưng nếu xóa theo batch, cần chọn ID trước rồi archive/verify và xóa đúng tập ID đó. Cần index trên event_legal_holds(event_id) và index phù hợp trên events(occurred_at, event_id). Nếu hold có thể được tạo đồng thời với purge, transaction phải kiểm tra lại hold trước khi xóa để tránh race condition.

### Xác minh sau mỗi batch

- Số hàng archive bằng số khóa đã chọn.
- Checksum của payload khớp.
- Mọi event_id đã xóa đều có bản archive verified.
- Không có event đang hold bị xóa.
- Checkpoint phản ánh đúng batch đã commit.
- Replication lag và p95 API vẫn trong ngưỡng.

## 25. Kiểm thử trước khi đưa retention job vào production

Kiểm thử phải bao gồm dữ liệu lớn và tình huống lỗi:

- Bảng có kích thước, index và phân bố dữ liệu gần production.
- Hàng đủ hạn, chưa đủ hạn, đến muộn và đang legal hold.
- Foreign key nhiều tầng và cascade.
- Trigger, audit, CDC và replica.
- Worker chạy song song, worker chết giữa batch và job bị khởi động lại.
- Archive upload thành công nhưng manifest chưa commit.
- Manifest đã commit nhưng nguồn chưa purge.
- Connection loss trong lúc commit.
- Replica lag hoặc transaction log gần đầy.
- Truy vấn trực tuyến đồng thời trên cùng bảng.

Đo thời gian mỗi batch, rows/sec, log bytes, lock wait, deadlock, replica lag, storage latency và p95/p99 của API. Xác minh cả dữ liệu còn lại và archive, không chỉ exit code của job.

## 26. Những sai lầm thường gặp

- **Xóa tất cả bằng một DELETE lớn:** tạo transaction log, lock và replication burst.
- **Dùng OFFSET lớn:** các batch sau tốn nhiều công sức bỏ qua hàng và có thể lệch khi dữ liệu thay đổi.
- **Không cố định cutoff:** ranh giới retention trôi trong lúc job chạy.
- **Chỉ dựa vào ID tăng dần:** dữ liệu cũ đến muộn có thể nằm ngoài high-water mark.
- **Archive rồi xóa mà không xác minh:** có thể xóa nguồn khi object bị thiếu hoặc sai.
- **Chỉ so sánh row count:** bỏ sót sai khác nội dung, NULL, encoding hoặc schema.
- **Quên legal hold:** xóa dữ liệu còn nghĩa vụ giữ.
- **Bỏ qua foreign key và trigger:** một batch cha nhỏ có thể gây lượng xóa con rất lớn.
- **Thiếu index ở cột khóa ngoại:** mỗi batch có thể quét bảng con.
- **Cho rằng DELETE trả dung lượng về OS:** không gian thường chỉ được tái sử dụng trong DB.
- **Tăng worker khi log/replica đã nghẽn:** làm backlog và contention nặng hơn.
- **Commit checkpoint trước khi xóa:** job có thể bỏ qua dữ liệu chưa được xử lý.
- **Ghi checkpoint sau xóa mà không idempotent:** retry có thể tạo archive trùng hoặc đếm sai.
- **Drop partition khi cutoff nằm giữa partition:** xóa nhầm dữ liệu còn hạn.
- **Coi backup là archive:** backup không nhất thiết cho phép truy vấn/khôi phục từng bản ghi thuận tiện.
- **Không thử khôi phục archive:** phát hiện lỗi định dạng hoặc encryption key khi đã cần dữ liệu.

## 27. Checklist thiết kế và vận hành

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Mục đích giữ dữ liệu là gì? | Có yêu cầu nghiệp vụ, pháp lý và kiểm toán |
| Cột thời gian nào quyết định tuổi dữ liệu? | Ý nghĩa timestamp, timezone và cutoff đã rõ |
| Có legal hold hoặc ngoại lệ không? | Purge kiểm tra hold ngay trước khi xóa |
| Dữ liệu cần archive hay có thể purge trực tiếp? | Đích archive và thời hạn từng tầng đã xác định |
| Archive có thể khôi phục không? | Manifest, checksum, encryption và restore test |
| Batch dùng khóa ổn định nào? | Keyset/high-water mark không bỏ sót dữ liệu đến muộn |
| Có index hỗ trợ predicate không? | Execution plan và row estimate đã được kiểm tra |
| Foreign key/trigger/cascade ảnh hưởng ra sao? | Index con, thứ tự xóa và số hàng phụ đã biết |
| Batch size có giới hạn tác động không? | Log, lock, I/O và p95/p99 được đo |
| Có checkpoint và idempotency không? | Job có thể chạy lại sau crash |
| Có nhiều worker hoặc job chồng lấn không? | Lease/lock và cơ chế claim rõ ràng |
| Partition có thể loại bỏ metadata không? | Toàn partition hết hạn và archive đã verified |
| Replica và CDC có theo kịp không? | Có lag threshold và throttle |
| Dung lượng được giải phóng theo cách nào? | Phân biệt reuse trong DB với shrink/rebuild |
| Kết quả được đối chiếu ra sao? | Count, checksum và invariant nghiệp vụ |

## 28. Nguyên tắc ra quyết định

Retention policy xác định dữ liệu nào còn cần thiết và trong bao lâu; archive giữ lại dữ liệu cần tra cứu nhưng ít truy cập; purge loại bỏ dữ liệu đã hết mục đích giữ. Ba bước phải liên kết với nhau bằng cutoff rõ ràng, ngoại lệ legal hold, manifest và bằng chứng xác minh.

Với dữ liệu nằm trong một phần bảng, hãy dùng batch có khóa ổn định, transaction ngắn, index phù hợp và checkpoint có thể chạy lại. Với dữ liệu nằm trọn trong partition đã hết hạn, partition detach/drop hoặc switch có thể giảm đáng kể công việc so với xóa từng hàng. Dù dùng cách nào, phải tính đến foreign key, trigger, transaction log, undo, vacuum, replication và backup.

Một quy trình bảo trì tốt hoàn tất trong giới hạn tài nguyên đã định, không làm chậm giao dịch trực tuyến vượt SLO, không xóa dữ liệu còn hạn và có thể tiếp tục hoặc khôi phục sau lỗi. Đo throughput purge cùng lock wait, log generation, replica lag, I/O và p95/p99 sẽ cho biết chính sách retention có bền vững khi dữ liệu tiếp tục tăng hay không.
