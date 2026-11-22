# Truy vấn cập nhật hoặc xóa khối lượng lớn theo từng đợt

Các hệ thống vận hành lâu ngày thường phải cập nhật hoặc xóa một lượng lớn dữ liệu: đánh dấu bản ghi hết hạn, chuẩn hóa trạng thái, chuyển dữ liệu lịch sử sang vùng lưu trữ, dọn hàng đợi đã xử lý hoặc xóa dữ liệu theo chính sách lưu giữ. Một câu UPDATE hoặc DELETE duy nhất có thể diễn đạt công việc rất gọn, nhưng khi phạm vi lên tới hàng triệu hàng, giao dịch kéo dài có thể giữ khóa lâu, tạo lượng log lớn, làm tăng I/O, gây áp lực bộ nhớ, làm chậm replica và ảnh hưởng các giao dịch trực tuyến.

Chia công việc thành các đợt nhỏ (batching) giúp giới hạn lượng dữ liệu xử lý trong mỗi giao dịch, tạo điểm commit thường xuyên và cho phép điều tiết tốc độ theo tình trạng hệ thống. Tuy nhiên, batching cần được thiết kế cẩn thận. Nếu mỗi đợt quét lại toàn bộ bảng, chọn hàng không có thứ tự ổn định, cập nhật lặp lại cùng bản ghi hoặc ghi checkpoint sai thời điểm, tổng chi phí có thể còn cao hơn một thao tác lớn.

Trong phạm vi DATABASE_PERFORMANCE, bài học này trình bày cách thiết kế UPDATE/DELETE theo batch dựa trên đo đạc tải, kế hoạch thực thi, chỉ mục và cơ chế giao dịch. Trọng tâm là giới hạn phạm vi từng đợt, giữ khả năng tiếp tục sau lỗi, phối hợp với workload trực tuyến và kiểm chứng tính đúng đắn sau khi hoàn tất.

## 1. Vì sao cần chia UPDATE và DELETE lớn thành batch?

Một giao dịch lớn có thể tạo ra nhiều loại áp lực cùng lúc:

- **Khóa và tranh chấp:** giao dịch giữ khóa trên nhiều hàng hoặc trang trong thời gian dài; giao dịch khác phải chờ hoặc bị deadlock.
- **Transaction log, WAL hoặc undo:** mỗi thay đổi cần được ghi nhận để phục hồi, rollback, replication hoặc MVCC. Một đợt quá lớn có thể tạo log tăng đột biến.
- **I/O và checkpoint:** nhiều trang dữ liệu bị sửa hoặc xóa làm tăng ghi dữ liệu, flush log và công việc checkpoint.
- **MVCC và dọn phiên bản cũ:** ở hệ quản trị dùng row versioning, giao dịch dài hoặc snapshot cũ có thể ngăn việc thu hồi phiên bản không còn cần thiết.
- **Replication lag:** tốc độ sinh log vượt tốc độ áp dụng ở replica làm độ trễ sao chép tăng.
- **Bộ nhớ và tài nguyên tạm:** kế hoạch cập nhật có join, sort hoặc tập khóa lớn có thể cần memory grant hoặc spill.
- **Rollback và phục hồi:** nếu lỗi ở cuối giao dịch, DB có thể phải rollback một lượng thay đổi lớn, kéo dài thời gian phục hồi.
- **Ảnh hưởng đến người dùng:** CPU, I/O và log bị chiếm dụng có thể làm p95/p99 của truy vấn trực tuyến tăng.

Batching chia một công việc lớn thành nhiều giao dịch nhỏ hơn. Sau mỗi batch, hệ thống có thể commit, giải phóng phần lớn khóa giao dịch, ghi nhận tiến độ và tạm dừng để workload khác sử dụng tài nguyên.

Ví dụ, thay vì xóa 5 triệu bản ghi lịch sử trong một giao dịch, có thể xóa từng nhóm 2.000 hàng, commit, đo tình trạng hệ thống rồi tiếp tục. Con số 2.000 chỉ là điểm bắt đầu minh họa; kích thước thực tế cần được đo trên dữ liệu, chỉ mục, phần cứng và mức tải của hệ thống.

### Batching không tự động làm giảm tổng công việc

Chia batch chủ yếu kiểm soát kích thước giao dịch và nhịp tải. Tổng số hàng phải thay đổi, số mục chỉ mục phải cập nhật và lượng log cần ghi về cơ bản vẫn tồn tại. Mỗi batch còn có overhead riêng như parse/execute, commit, cập nhật checkpoint và điều phối.

Nếu batch quá nhỏ, overhead commit và điều phối có thể chiếm tỷ lệ lớn. Nếu batch quá lớn, giao dịch vẫn giữ khóa lâu, tạo log lớn và gây đỉnh tải. Mục tiêu là chọn kích thước đủ lớn để đạt throughput tốt nhưng đủ nhỏ để giữ độ trễ, log, lock wait và replication lag trong giới hạn.

## 2. Xác định chính xác tập dữ liệu cần thay đổi

Trước khi thiết kế vòng lặp batch, cần xác định predicate nghiệp vụ và phạm vi dữ liệu. Một câu lệnh an toàn phải chỉ rõ hàng nào được phép cập nhật hoặc xóa, điều kiện nào loại trừ dữ liệu còn hiệu lực và cách xử lý bản ghi mới phát sinh trong khi công việc đang chạy.

Ví dụ, xóa sự kiện đã hết thời hạn lưu giữ:

```sql
DELETE FROM events
WHERE occurred_at < :retention_cutoff;
```

Predicate trên xác định tập dữ liệu theo thời gian, nhưng chưa xác định cách chia batch. Cần thêm một khóa ổn định để chia nhỏ và tiếp tục công việc.

### Đếm và ước lượng trước khi chạy

Trước khi thay đổi dữ liệu, hãy ước lượng quy mô và kiểm tra phân bố:

```sql
SELECT COUNT(*)
FROM events
WHERE occurred_at < :retention_cutoff;

SELECT
    MIN(event_id) AS min_id,
    MAX(event_id) AS max_id
FROM events
WHERE occurred_at < :retention_cutoff;
```

COUNT trên bảng lớn cũng có chi phí; hãy cân nhắc thời điểm chạy, thống kê hiện có hoặc cách ước lượng được DBMS hỗ trợ. Kết quả đếm tại một thời điểm không bảo đảm tập hàng sẽ giữ nguyên khi công việc bắt đầu nếu ứng dụng vẫn đang ghi dữ liệu.

Nên xác định:

- Predicate chính xác và tham số cutoff.
- Số hàng dự kiến, kích thước dữ liệu và phân bố theo khóa.
- Khóa chính hoặc khóa duy nhất dùng để chọn từng batch.
- Các index, foreign key, trigger và cascade có liên quan.
- Thứ tự xử lý cần thiết, chẳng hạn bảng con trước bảng cha.
- Dữ liệu mới có thể xuất hiện trong lúc chạy hay không.
- Điều kiện dừng, thời hạn hoàn tất và giới hạn tài nguyên.

### Predicate phải giữ đúng ý nghĩa nghiệp vụ

Không được bỏ điều kiện quan trọng chỉ để làm batch dễ hơn. Ví dụ, một tác vụ chỉ được xóa đơn đã hủy và đã quá thời hạn phải giữ cả hai điều kiện:

```sql
DELETE FROM orders
WHERE status = 'CANCELLED'
  AND cancelled_at < :retention_cutoff;
```

Khi chuyển sang batch, mọi đợt phải áp dụng cùng predicate hoặc một predicate con đã chứng minh nằm trong tập mục tiêu. Nếu điều kiện thay đổi giữa các batch, có thể xóa nhầm dữ liệu hoặc bỏ sót hàng.

## 3. Chọn khóa chia batch ổn định

Một batch thường chọn một tập khóa trước, sau đó UPDATE hoặc DELETE đúng những hàng đó. Khóa chia batch nên:

- Duy nhất hoặc kết hợp thành một khóa duy nhất.
- Có thứ tự xác định để tiến độ có thể tiếp tục.
- Có index hỗ trợ việc tìm batch.
- Ít thay đổi trong thời gian xử lý.
- Không phụ thuộc vào giá trị bị chính UPDATE làm thay đổi.

Khóa tăng dần như ID thường thuận tiện, nhưng không phải lúc nào cũng phù hợp. Nếu dữ liệu phân bố theo tenant hoặc thời gian, có thể chia theo khóa ghép như (tenant_id, event_id) hoặc theo partition.

### Keyset batching theo khóa tăng dần

Một cách phổ biến là lưu khóa cuối cùng đã xử lý, rồi lấy batch kế tiếp có khóa lớn hơn:

```sql
SELECT event_id
FROM events
WHERE event_id > :last_event_id
  AND event_id <= :high_water_mark
  AND occurred_at < :retention_cutoff
ORDER BY event_id
LIMIT 2000;
```

Sau khi xử lý và commit batch, cập nhật last_event_id thành khóa lớn nhất đã xử lý. Lần tiếp theo bắt đầu từ khóa đó.

Keyset batching tránh phải bỏ qua một số lượng hàng ngày càng lớn như OFFSET. Nếu có index phù hợp, DB có thể tìm từ vị trí khóa tiếp theo thay vì quét và loại bỏ mọi hàng trước đó.

### High-water mark

Khi bắt đầu công việc, có thể ghi nhận một high-water mark, chẳng hạn MAX(event_id) của tập mục tiêu. Các batch chỉ xử lý khóa không vượt quá mốc này:

```sql
SELECT MAX(event_id)
FROM events
WHERE occurred_at < :retention_cutoff;
```

High-water mark giúp xác định một phạm vi hữu hạn. Các hàng mới có khóa lớn hơn mốc không bị kéo vào một công việc đang chạy vô thời hạn. Tuy nhiên, nó không tự giải quyết mọi thay đổi đồng thời: một hàng có khóa nhỏ hơn mốc có thể được cập nhật để trở thành đủ điều kiện sau khi con trỏ đã đi qua. Nếu điều đó có thể xảy ra, cần chọn snapshot, quét lặp lại, trạng thái công việc hoặc quy tắc nghiệp vụ để không bỏ sót.

### Vì sao OFFSET thường không phù hợp cho batch lớn?

Mẫu sau có thể đơn giản nhưng càng về sau càng tốn:

```sql
SELECT event_id
FROM events
WHERE occurred_at < :retention_cutoff
ORDER BY event_id
LIMIT 2000 OFFSET 1000000;
```

DB thường phải đi qua hoặc loại bỏ khoảng một triệu hàng trước khi trả batch tiếp theo. Các batch sau có thể chậm dần. Keyset pagination theo khóa cuối cùng thường phù hợp hơn cho tiến trình dài.

### Không dùng thứ tự không duy nhất làm checkpoint

Nếu chia theo created_at nhưng nhiều hàng có cùng timestamp, checkpoint chỉ lưu timestamp có thể bỏ sót hoặc lặp lại hàng ở ranh giới batch. Hãy dùng khóa ghép có thứ tự toàn phần:

```sql
WHERE
    created_at > :last_created_at
    OR (
        created_at = :last_created_at
        AND event_id > :last_event_id
    )
ORDER BY created_at, event_id
LIMIT 2000;
```

Khóa event_id phân biệt các hàng có cùng created_at. Cần xử lý NULL theo quy tắc rõ ràng hoặc loại NULL khỏi phạm vi bằng predicate phù hợp.

## 4. Chọn batch và thực hiện UPDATE

UPDATE theo batch nên chọn tập hàng mục tiêu có giới hạn rồi thay đổi đúng tập đó trong một transaction. Có thể chọn bằng khóa chính hoặc khóa duy nhất, không nên phụ thuộc vào thứ tự vật lý của bảng.

### Mẫu logic tổng quát

1. Tìm tối đa N khóa thỏa điều kiện và nằm sau checkpoint.
2. Cập nhật các hàng có khóa thuộc tập vừa chọn.
3. Ghi số hàng thực tế và khóa cuối cùng đã xử lý.
4. Commit dữ liệu và tiến độ theo một ranh giới nhất quán.
5. Đo tài nguyên, điều tiết nếu cần rồi lấy batch tiếp theo.

Ví dụ minh họa:

```sql
UPDATE customer_events
SET normalized_status = 'ARCHIVED'
WHERE event_id IN (
    SELECT event_id
    FROM customer_events
    WHERE event_id > :last_event_id
      AND event_id <= :high_water_mark
      AND status = 'CLOSED'
      AND normalized_status IS DISTINCT FROM 'ARCHIVED'
    ORDER BY event_id
    LIMIT 1000
);
```

Đây là dạng minh họa theo cú pháp PostgreSQL; không phải cú pháp portable cho mọi DBMS. Predicate loại bỏ hàng đã có giá trị đích giúp tránh ghi lại dữ liệu không cần thiết. Với hệ quản trị không hỗ trợ IS DISTINCT FROM, có thể viết điều kiện NULL-safe tương đương theo dialect.

### Tránh cập nhật hàng không thay đổi

Một câu UPDATE đặt cùng giá trị hiện tại vẫn có thể tạo công việc: ghi log, cập nhật index, kích hoạt trigger hoặc tạo row version tùy DBMS. Nếu mục tiêu là thay đổi trạng thái, hãy lọc để chỉ cập nhật hàng thực sự khác:

```sql
UPDATE accounts
SET status = 'INACTIVE'
WHERE status <> 'INACTIVE'
  AND last_activity_at < :inactive_cutoff;
```

Nếu status có thể NULL, điều kiện trên không chọn các hàng NULL. Cần xác định NULL có thuộc tập mục tiêu không và viết predicate tường minh. Không nên thay đổi ngữ nghĩa chỉ để giảm số hàng cập nhật.

### Cập nhật theo phép biến đổi xác định

Các batch dễ phục hồi hơn khi phép biến đổi là xác định và có thể chạy lại an toàn. Ví dụ:

```sql
WITH batch AS (
    SELECT invoice_id
    FROM invoices
    WHERE invoice_id > :last_invoice_id
      AND invoice_id <= :high_water_mark
      AND normalized_code IS DISTINCT FROM UPPER(TRIM(invoice_code))
    ORDER BY invoice_id
    LIMIT 1000
    FOR UPDATE
)
UPDATE invoices AS i
SET normalized_code = UPPER(TRIM(i.invoice_code))
FROM batch AS b
WHERE i.invoice_id = b.invoice_id
RETURNING i.invoice_id;
```

Đây là ví dụ theo cú pháp PostgreSQL: CTE chọn và khóa một batch bằng khóa chính, sau đó UPDATE qua JOIN và trả về khóa đã thay đổi. Các hệ quản trị khác có thể dùng UPDATE ... ORDER BY ... LIMIT hoặc CTE/TOP với cú pháp riêng; IS DISTINCT FROM cũng không portable. Hãy dùng dạng cú pháp phù hợp với DBMS đang vận hành.

Tránh phép biến đổi phụ thuộc thời gian hiện tại hoặc trạng thái bên ngoài nếu cần retry. Nếu giá trị đích thay đổi mỗi lần chạy, retry có thể tạo kết quả khác hoặc cập nhật lại cùng hàng liên tục.

## 5. Chọn batch và thực hiện DELETE

DELETE theo batch cũng cần chọn khóa trước, rồi xóa đúng tập hàng đó. Ví dụ PostgreSQL:

```sql
WITH batch AS (
    SELECT event_id
    FROM events
    WHERE event_id > :last_event_id
      AND event_id <= :high_water_mark
      AND occurred_at < :retention_cutoff
    ORDER BY event_id
    LIMIT 2000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM events AS e
USING batch AS b
WHERE e.event_id = b.event_id
RETURNING e.event_id;
```

CTE chọn một nhóm khóa có giới hạn, khóa các hàng đã chọn và bỏ qua hàng đang bị transaction khác khóa. DELETE chỉ xóa những khóa đã được chọn. RETURNING trả về khóa thực tế đã xóa để ứng dụng ghi nhận tiến độ hoặc thống kê.

Trong ví dụ có SKIP LOCKED, không được cập nhật checkpoint chỉ bằng khóa lớn nhất nếu các hàng bị khóa đã bị bỏ qua. Một con trỏ tiến về phía trước có thể đi qua chúng và không bao giờ quay lại. Cần lưu danh sách hàng bỏ qua, chạy vòng quét lại, hoặc dùng một cơ chế trạng thái/queue bảo đảm hàng chưa xử lý được thử lại.

### MySQL: DELETE có LIMIT

MySQL hỗ trợ LIMIT trong một số dạng single-table DELETE:

```sql
DELETE FROM events
WHERE occurred_at < ?
ORDER BY event_id
LIMIT 2000;
```

Ứng dụng có thể lặp lại câu lệnh cho đến khi số hàng bị ảnh hưởng bằng 0 hoặc đạt điều kiện dừng. Để tiếp tục hiệu quả hơn trên bảng lớn, có thể kết hợp keyset theo khóa:

```sql
DELETE FROM events
WHERE event_id > ?
  AND event_id <= ?
  AND occurred_at < ?
ORDER BY event_id
LIMIT 2000;
```

Sau mỗi batch, cần xác định khóa cuối cùng đã xử lý theo cách không bỏ qua hàng đủ điều kiện nhưng chưa xóa. Nếu chỉ dùng LIMIT và predicate, DB có thể tiếp tục lấy các hàng đầu còn thỏa điều kiện; điều này đơn giản nhưng cần index để tránh quét lặp quá nhiều.

### SQL Server: chọn TOP trong CTE

SQL Server thường dùng TOP và CTE hoặc bảng tạm để chọn batch:

```sql
;WITH batch AS (
    SELECT TOP (2000) event_id
    FROM dbo.Events WITH (UPDLOCK, READPAST, ROWLOCK)
    WHERE event_id > @last_event_id
      AND event_id <= @high_water_mark
      AND occurred_at < @retention_cutoff
    ORDER BY event_id
)
DELETE e
OUTPUT deleted.event_id
FROM dbo.Events AS e
JOIN batch AS b
  ON b.event_id = e.event_id;
```

UPDLOCK yêu cầu khóa cập nhật khi chọn hàng; READPAST bỏ qua một số hàng đang bị khóa; ROWLOCK là gợi ý khóa hàng và không phải cam kết tuyệt đối. Các hint có giới hạn theo isolation level và cấu hình. READPAST có thể khiến hàng bị bỏ qua phải được xử lý ở lần chạy sau; không nên tăng checkpoint qua các khóa bị bỏ qua nếu chưa có cách theo dõi chúng.

OUTPUT deleted.event_id giúp lấy khóa hàng đã xóa. Có thể ghi kết quả vào bảng tiến độ hoặc nhận về ứng dụng, nhưng phải giữ tính nhất quán giữa việc xóa và checkpoint.

### Oracle: row limiting và SKIP LOCKED

Oracle có thể dùng cursor với FOR UPDATE SKIP LOCKED và PL/SQL bulk processing để nhiều worker lấy các hàng chưa bị worker khác khóa. Một cursor có thể được đọc theo lô bằng FETCH BULK COLLECT ... LIMIT; sau đó dùng khóa chính của các hàng đã lấy để cập nhật hoặc xóa trong cùng transaction. Cần giữ transaction mở trong suốt thời gian các hàng đã chọn được xử lý, rồi commit theo batch. Cú pháp cụ thể phụ thuộc phiên bản và cấu trúc PL/SQL; cần kiểm tra tài liệu Oracle đang triển khai, đặc biệt các giới hạn khi kết hợp row limiting clause với FOR UPDATE.

## 6. Transaction boundary và commit theo batch

Một batch nên có transaction boundary rõ ràng. Mỗi batch thường gồm chọn hàng, thay đổi hàng, ghi checkpoint và commit. Batch kế tiếp chỉ bắt đầu sau khi transaction trước hoàn tất hoặc sau khi cơ chế điều phối xác nhận có thể tiếp tục.

### Vì sao không bọc toàn bộ vòng lặp trong một transaction?

Nếu vòng lặp xử lý 5 triệu hàng nhưng chỉ commit một lần ở cuối:

- Khóa có thể được giữ đến cuối toàn bộ công việc.
- Log hoặc WAL cần được giữ đủ để phục hồi giao dịch.
- Rollback khi lỗi có thể rất lâu.
- Snapshot dài có thể cản trở dọn phiên bản cũ.
- Replica và backup có thể chịu ảnh hưởng từ lượng log lớn.
- Công việc không có điểm tiến độ bền vững giữa chừng.

Commit sau từng batch tạo ranh giới phục hồi rõ ràng. Tuy nhiên, nếu nghiệp vụ yêu cầu toàn bộ thay đổi phải nguyên tử như một giao dịch duy nhất, không thể tự ý chia commit mà không thay đổi semantics. Khi đó cần thiết kế quy trình staging, trạng thái chuyển tiếp, versioning hoặc cơ chế publish/activate phù hợp.

### Ghi checkpoint cùng transaction

Giả sử bảng job_progress lưu last_key. Một transaction cần:

1. Chọn và thay đổi batch.
2. Xác định các khóa thực sự đã thay đổi.
3. Cập nhật checkpoint tương ứng.
4. Commit cả dữ liệu lẫn checkpoint.

Nếu xóa dữ liệu commit thành công nhưng checkpoint chưa được ghi, lần chạy lại có thể xử lý lại vùng đã xóa. Điều này có thể an toàn nếu thao tác idempotent, nhưng gây thêm scan. Ngược lại, nếu checkpoint commit trước khi xóa dữ liệu, lỗi có thể làm bỏ sót hàng chưa xử lý.

Khi ghi cả thay đổi và checkpoint trong cùng transaction, hai phần cùng commit hoặc cùng rollback. Với nhiều worker xử lý tập khóa rời rạc, checkpoint cần mô hình hóa trạng thái theo từng batch hoặc từng hàng, không thể luôn dùng một số khóa lớn nhất toàn cục.

### Transaction nhỏ không có nghĩa mọi thao tác đều độc lập

Nếu một đợt cập nhật phải đồng bộ với thay đổi ở bảng khác, các thao tác liên quan cần nằm trong cùng transaction của batch. Ví dụ, chuyển đơn hàng sang archive có thể cần ghi bản ghi archive và đánh dấu bản gốc đã chuyển. Nếu hai thay đổi commit riêng, lỗi ở giữa có thể tạo dữ liệu trùng hoặc thiếu.

Thiết kế cần nêu rõ invariant nghiệp vụ nào phải được giữ trong mỗi batch và invariant nào chỉ cần đúng sau khi toàn bộ job hoàn tất.

## 7. Kích thước batch và nhịp điều tiết

Không có một batch size phù hợp cho mọi bảng. Kích thước nên được xác định bằng thử nghiệm tăng dần và quan sát các chỉ số trong điều kiện tải gần thực tế.

### Các yếu tố quyết định

- Số hàng mỗi batch.
- Độ rộng hàng và số cột thay đổi.
- Số index cần cập nhật.
- Trigger, foreign key và cascade.
- Tỷ lệ hàng đủ điều kiện trong vùng quét.
- Khả năng ghi log/WAL và tốc độ flush.
- Thời gian giữ khóa và mức tranh chấp.
- Thời gian commit và độ trễ replica.
- Mức tải trực tuyến trong cùng thời điểm.

Batch 5.000 hàng trên bảng hẹp có một index có thể nhẹ hơn batch 500 hàng trên bảng có nhiều index, trigger và quan hệ cascade. Vì vậy, không nên dùng số hàng làm chỉ số duy nhất; cần theo dõi thời gian transaction, log bytes và tài nguyên.

### Bắt đầu nhỏ và tăng dần

Một cách thực tế:

1. Chọn batch nhỏ để xác minh logic và đo overhead.
2. Tăng batch từng bước, chẳng hạn 500, 1.000, 2.000, 5.000 hàng, tùy quy mô.
3. Với mỗi mức, ghi thời gian batch, rows affected, log bytes, lock wait, CPU, I/O và replica lag.
4. Dừng tăng khi throughput không cải thiện đáng kể hoặc các chỉ số ảnh hưởng bắt đầu vượt ngưỡng.
5. Chọn mức thấp hơn điểm bão hòa để có biên an toàn.

Các mức trong ví dụ chỉ là một dãy thử nghiệm, không phải cấu hình mặc định.

### Điều tiết giữa các batch

Có thể nghỉ một khoảng ngắn sau mỗi batch, giới hạn số batch đồng thời hoặc dùng bộ điều khiển dựa trên metric:

- Nếu p95 của giao dịch trực tuyến tăng vượt ngưỡng, giảm batch size hoặc tăng thời gian nghỉ.
- Nếu replication lag tăng liên tục, giảm tốc độ ghi hoặc tạm dừng job.
- Nếu lock wait/deadlock tăng, giảm concurrency và kiểm tra thứ tự khóa.
- Nếu I/O latency tăng, giới hạn số worker hoặc chuyển job sang khung giờ phù hợp.
- Nếu batch quá ngắn và overhead commit chiếm phần lớn, có thể tăng nhẹ kích thước.

Điều tiết nên có giới hạn và hysteresis để tránh dao động liên tục. Ví dụ, chỉ tăng batch sau nhiều chu kỳ ổn định và giảm ngay khi vượt ngưỡng rõ ràng.

## 8. Chỉ mục hỗ trợ việc chọn batch

Một batch hiệu quả cần tìm nhanh hàng đủ điều kiện và theo đúng thứ tự checkpoint. Nếu predicate là:

```sql
WHERE status = 'EXPIRED'
  AND event_id > :last_event_id
ORDER BY event_id
LIMIT 2000
```

một chỉ mục ghép có thể được cân nhắc theo dạng (status, event_id), tùy selectivity và cách workload khác sử dụng bảng.

Nếu predicate chính là thời gian:

```sql
WHERE occurred_at < :cutoff
ORDER BY event_id
LIMIT 2000
```

thứ tự index cần được chọn dựa trên cách DB truy cập dữ liệu. Index (occurred_at, event_id) có thể lọc theo thời gian nhưng không nhất thiết cung cấp thứ tự toàn cục theo event_id qua nhiều giá trị occurred_at. Index (event_id) cung cấp thứ tự checkpoint nhưng có thể phải kiểm tra nhiều hàng mới tìm đủ hàng thỏa cutoff. Cần so sánh hai kế hoạch và phân bố dữ liệu.

### Tránh quét lại vùng đã xử lý

Nếu mỗi batch dùng predicate thời gian và ORDER BY nhưng không có checkpoint, DB có thể liên tục bắt đầu từ những hàng đầu tiên còn thỏa điều kiện. Khi hàng đầu bị xóa, tiến trình có thể vẫn ổn; nhưng với UPDATE làm điều kiện không đổi, cùng hàng có thể được chọn lại nếu predicate không loại bỏ nó.

Đối với UPDATE, hãy đảm bảo mỗi hàng sau khi xử lý rời khỏi predicate hoặc checkpoint tiến qua một khóa ổn định. Ví dụ:

```sql
UPDATE tasks
SET cleanup_state = 'DONE'
WHERE task_id > :last_task_id
  AND task_id <= :high_water_mark
  AND cleanup_state = 'PENDING'
ORDER BY task_id
LIMIT 1000;
```

Sau khi commit, các hàng đã cập nhật không còn thỏa cleanup_state = 'PENDING'. Tuy nhiên, nếu có hàng khóa bị bỏ qua hoặc một worker khác thay đổi trạng thái, tiến trình phải có cách xử lý phần còn lại thay vì chỉ tiến checkpoint theo khóa lớn nhất được nhìn thấy.

### Kiểm tra execution plan

Với truy vấn chọn batch, hãy xem:

- Có index seek/range scan hay full table scan?
- Số hàng ước lượng có gần số hàng thực tế không?
- Có Sort trước LIMIT không?
- Có lookup quá nhiều lần không?
- Predicate có được đẩy xuống index scan không?
- Số hàng bị đọc để tìm đủ một batch là bao nhiêu?

Với UPDATE/DELETE, cần xem thêm kế hoạch DML, số index bị cập nhật, trigger và cascade. Một truy vấn chọn ID nhanh chưa chắc toàn bộ thao tác xóa nhanh nếu mỗi hàng phải cập nhật nhiều index hoặc kiểm tra nhiều foreign key.

## 9. Khóa, deadlock và nhiều worker

Nhiều worker có thể tăng throughput bằng cách xử lý các batch độc lập, nhưng cũng làm tăng tranh chấp. Nếu các worker chọn cùng hàng, khóa có thể khiến một worker chờ hoặc deadlock. Cần phân chia công việc rõ ràng.

### Chia phạm vi tĩnh

Có thể chia theo khoảng khóa:

- Worker A xử lý event_id từ 1 đến 10 triệu.
- Worker B xử lý event_id từ 10 triệu đến 20 triệu.
- Worker C xử lý event_id từ 20 triệu đến 30 triệu.

Phân vùng tĩnh giảm khả năng chọn trùng nhưng có thể mất cân bằng nếu dữ liệu phân bố lệch. Cần đo số hàng đủ điều kiện trong mỗi phạm vi.

### Chia việc động bằng SKIP LOCKED

Một số DBMS hỗ trợ bỏ qua hàng đang bị khóa để worker khác lấy hàng tiếp theo. Cách này hữu ích cho queue worker hoặc cleanup job song song:

- Mỗi worker chọn một batch và khóa hàng.
- Worker khác bỏ qua các hàng đã khóa.
- Mỗi worker xử lý và commit batch riêng.

SKIP LOCKED không tự đảm bảo công bằng. Hàng thường xuyên bị khóa có thể bị trì hoãn lâu; cần theo dõi tuổi của hàng chưa xử lý và có vòng quét lại. Không dùng một high-water mark duy nhất nếu các worker xử lý các vùng khóa không liên tục.

### Deadlock và thứ tự khóa

Nếu các worker cập nhật nhiều bảng hoặc nhiều hàng theo thứ tự khác nhau, có thể tạo chu trình chờ. Giảm rủi ro bằng cách:

- Xử lý hàng theo một thứ tự khóa nhất quán, thường theo khóa chính.
- Giữ transaction ngắn.
- Không gọi dịch vụ ngoài khi đang giữ transaction DB nếu không cần.
- Chia batch nhỏ hơn khi có tranh chấp.
- Xử lý deadlock bằng retry có giới hạn và backoff.
- Đảm bảo thao tác có thể chạy lại an toàn.

Không nên chỉ tăng số lần retry mà không điều tra nguyên nhân deadlock. Retry quá dày có thể tạo thêm tải và khiến hệ thống dao động.

### Lock escalation

Một số DBMS có thể nâng nhiều khóa hàng/trang thành khóa phạm vi lớn hơn khi số lượng khóa hoặc áp lực bộ nhớ đạt ngưỡng. Điều này có thể làm các giao dịch khác bị chặn rộng hơn dự kiến. Hint khóa hàng không phải lúc nào cũng bảo đảm không escalation. Cần theo dõi lock escalation event và cấu hình của hệ quản trị.

## 10. DELETE, foreign key và cascade

Xóa một hàng cha có thể kích hoạt kiểm tra hoặc xóa hàng con theo foreign key. Nếu cascade xóa nhiều hàng con, batch 1.000 hàng cha có thể gây ra hàng trăm nghìn thay đổi thực tế.

Trước khi xóa lớn, hãy xác định:

- Có foreign key tham chiếu bảng mục tiêu không?
- Có ON DELETE CASCADE, SET NULL hoặc trigger không?
- Có index trên cột foreign key của bảng con không?
- Thứ tự xóa bảng con và bảng cha có cần được kiểm soát không?
- Trigger có gửi thông điệp, ghi audit hoặc gọi logic phụ không?

Nếu xóa thủ công bảng con trước bảng cha, phải bảo đảm phạm vi và transaction giữ được tính toàn vẹn. Không tắt constraint hoặc trigger chỉ để tăng tốc nếu chưa có quy trình bảo đảm dữ liệu hợp lệ và kiểm tra lại sau đó.

### Xóa theo thời gian và partition

Nếu dữ liệu được phân vùng theo thời gian và toàn bộ partition cũ đã hết hạn, detach/drop partition có thể nhanh hơn xóa từng hàng. Thao tác metadata này có thể giảm lượng log và công việc row-by-row, nhưng semantics khác với DELETE:

- Toàn bộ partition phải nằm trong phạm vi được phép xóa.
- Foreign key, index và constraint có thể giới hạn khả năng detach/drop.
- Dữ liệu trong partition bị loại bỏ toàn bộ; không thể dùng nếu chỉ một phần hàng hết hạn.
- Lock metadata và thời gian detach/drop vẫn cần được đánh giá.
- Backup, replication và chính sách lưu giữ cần được cập nhật tương ứng.

Nếu không thể dùng partition maintenance, DELETE theo batch vẫn là phương án phổ biến. Sau khi xóa nhiều hàng, một số hệ quản trị cần vacuum, purge hoặc bảo trì để thu hồi không gian; không nên giả định file dữ liệu trên đĩa lập tức nhỏ đi.

## 11. UPDATE lớn và tác động đến index

UPDATE cột không được lập chỉ mục có thể có chi phí khác với UPDATE cột khóa index. Khi cập nhật cột nằm trong index, DB có thể phải thay đổi các mục index tương ứng. Với bảng có nhiều index, một hàng thay đổi có thể kéo theo nhiều thao tác ghi.

Các câu hỏi cần kiểm tra:

- Cột nào thực sự thay đổi?
- Cột đó có xuất hiện trong key hoặc INCLUDE của index không?
- Có generated/computed column hoặc expression index phụ thuộc cột đó không?
- Có trigger hoặc CDC/audit capture không?
- Có thể chỉ cập nhật hàng có giá trị khác không?
- Có thể tách cập nhật cột ít thay đổi khỏi cập nhật cột thường xuyên không?

Nếu cập nhật một cột được dùng trong predicate của index, hàng có thể rời khỏi hoặc đi vào vùng index khác. Điều này có thể giúp batch tiếp theo không chọn lại hàng đã xử lý, nhưng cũng làm phát sinh chi phí bảo trì index.

### Tránh đọc và ghi cùng bảng nhiều lần không cần thiết

Một số quy trình cập nhật có thể được chia thành hai bước: tạo danh sách khóa mục tiêu rồi cập nhật. Cách này giúp kiểm soát phạm vi nhưng có thể thêm bảng tạm, I/O và chi phí lưu danh sách. Nếu danh sách rất lớn, cần index trên bảng staging và dọn dẹp sau job.

Nếu điều kiện mục tiêu ổn định, có thể chọn và cập nhật trực tiếp theo batch trong một câu lệnh hoặc transaction. Hãy đo cả phương án trực tiếp và staging; không mặc định một cách luôn nhanh hơn.

## 12. Log, WAL, undo và replication

Mỗi batch tạo ra log hoặc thông tin phục hồi cho các thay đổi. Đối với DELETE, DB cần ghi nhận hàng bị xóa và các mục index bị ảnh hưởng. Đối với UPDATE, DB ghi lại thông tin cần thiết để phục hồi hoặc duy trì phiên bản dữ liệu theo cơ chế của engine.

Một batch lớn có thể:

- Làm transaction log tăng nhanh và gây áp lực dung lượng.
- Tạo nhiều WAL segment hoặc log record trong thời gian ngắn.
- Tăng thời gian flush log khi commit.
- Làm replica cần nhiều thời gian áp dụng thay đổi.
- Tạo thêm công việc checkpoint, vacuum hoặc purge.

Theo dõi:

- Log bytes hoặc WAL generated mỗi batch.
- Commit latency và số lần commit.
- Log volume free space và tốc độ tăng.
- Replica lag theo thời gian và khả năng bắt kịp sau batch.
- Checkpoint duration, dirty pages và background write.
- Thời gian vacuum/purge hoặc dọn phiên bản cũ.

Nếu replica lag vượt ngưỡng, có thể tạm dừng giữa các batch cho replica bắt kịp. Với hệ thống yêu cầu đọc nhất quán từ replica, cần đánh giá tác động lên ứng dụng trong thời gian lag.

Một thao tác DELETE lớn không đồng nghĩa dữ liệu biến mất ngay khỏi mọi bản sao, backup hoặc log archive. Chính sách lưu giữ phải xét cả bản sao, bản backup và cơ chế phục hồi của hệ thống.

## 13. Khả năng tiếp tục sau lỗi: checkpoint và idempotency

Job dài cần có khả năng tiếp tục sau timeout, restart, mất kết nối hoặc lỗi deadlock. Không nên dựa vào bộ nhớ của tiến trình ứng dụng để nhớ batch cuối cùng nếu job có thể bị dừng đột ngột.

### Bảng tiến độ công việc

Một bảng job_progress có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| job_id | Định danh một lần chạy hoặc loại công việc |
| status | PENDING, RUNNING, PAUSED, COMPLETED hoặc FAILED |
| high_water_mark | Giới hạn trên đã chốt cho lần chạy |
| last_key | Khóa cuối cùng đã xử lý thành công nếu dùng keyset |
| rows_affected | Tổng số hàng đã thay đổi |
| batch_count | Số batch đã commit |
| started_at / updated_at | Thời điểm bắt đầu và cập nhật tiến độ |
| last_error | Lỗi gần nhất để điều tra |

Không phải mọi công việc đều cần tất cả trường. Thiết kế phải phù hợp với cách chia phạm vi và số worker.

### Idempotency

Một thao tác idempotent có thể được thực hiện lại mà không làm thay đổi kết quả cuối ngoài dự kiến. Ví dụ, đặt status thành ARCHIVED nếu chưa phải ARCHIVED thường có thể chạy lại an toàn:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE order_id > :last_order_id
  AND status = 'CLOSED';
```

Ngược lại, phép cộng tăng bộ đếm:

```sql
UPDATE accounts
SET retry_count = retry_count + 1
WHERE account_id = :account_id;
```

không idempotent nếu cùng batch bị chạy lại. Cần một khóa sự kiện duy nhất, bảng ledger hoặc điều kiện version để tránh áp dụng cùng tác vụ hai lần.

DELETE thường idempotent ở mức kết quả dữ liệu: xóa lại hàng đã xóa không tạo thêm tác dụng trên hàng đó. Nhưng trigger, audit, cascade và side effect có thể khiến lần chạy lại vẫn tạo thay đổi khác. Cần xem toàn bộ hành vi của transaction, không chỉ câu DELETE.

### Checkpoint và retry

Checkpoint chỉ được tiến sau khi batch thực sự hoàn tất. Nếu batch bị rollback, checkpoint tương ứng cũng phải rollback hoặc không được ghi nhận là đã xong.

Với nhiều worker hoặc SKIP LOCKED, một con trỏ đơn có thể không đủ. Hãy dùng trạng thái theo batch/partition, bảng claim công việc hoặc danh sách khóa đã hoàn thành để theo dõi vùng xử lý không liên tục.

Retry nên:

- Chỉ áp dụng cho lỗi tạm thời như deadlock hoặc serialization failure theo chính sách DBMS.
- Có số lần tối đa và exponential backoff có jitter.
- Giữ nguyên định danh job và khóa idempotency.
- Không retry vô hạn lỗi dữ liệu, constraint hoặc lỗi cấu hình.
- Ghi lại batch, khóa và nguyên nhân để có thể điều tra.

## 14. Lập lịch và phối hợp với workload trực tuyến

Bulk update/delete thường là công việc nền. Cần tránh để nó cạnh tranh quá mức với truy vấn người dùng.

Các biện pháp:

- Chạy trong khung giờ tải thấp nếu yêu cầu thời hạn cho phép.
- Giới hạn số worker và số transaction đồng thời.
- Dùng connection pool riêng hoặc quota cho job nền.
- Chọn batch size và delay theo p95/p99 của workload trực tuyến.
- Tạm dừng khi CPU, I/O, lock wait hoặc replica lag vượt ngưỡng.
- Không chạy đồng thời nhiều job cùng cập nhật một bảng hoặc vùng dữ liệu.
- Dành tài nguyên cho backup, replication và tác vụ bảo trì cần thiết.

Một job có thể được phép chạy lâu nhưng không được phép làm request tương tác vượt SLO. Hãy xác định ưu tiên nghiệp vụ: thời hạn hoàn tất job, mức độ ảnh hưởng chấp nhận được và điều kiện tự động pause/resume.

## 15. Đo lường hiệu quả của mỗi batch

Không chỉ ghi tổng số hàng đã xử lý. Mỗi batch nên tạo một bản ghi quan sát đủ để biết tốc độ và tác động:

| Chỉ số | Mục đích |
|---|---|
| Batch ID và key range | Biết chính xác phạm vi đã xử lý |
| Rows selected / affected | Phân biệt số hàng được chọn và số hàng thực sự thay đổi |
| Batch elapsed time | Đo thời gian từ lúc bắt đầu đến commit |
| Rows per second | Đo throughput thực tế |
| Commit latency | Phát hiện log flush hoặc commit chậm |
| Lock wait/deadlock | Đo tranh chấp |
| CPU và I/O | Phát hiện nút thắt tài nguyên |
| Log/WAL bytes | Theo dõi áp lực phục hồi và sao chép |
| Replica lag | Biết tác động lên bản sao |
| Online request p95/p99 | Đo ảnh hưởng đến người dùng |
| Error/retry count | Phát hiện batch không ổn định |

Nên lưu p50/p95/p99 theo cửa sổ thời gian cho workload trực tuyến. Một batch trung bình nhanh không bảo đảm không có batch chậm do khóa nóng hoặc phân bố dữ liệu lệch.

### Throughput và thời gian còn lại

Nếu một job còn 4 triệu hàng và tốc độ ổn định là 20.000 hàng/giây, thời gian ước lượng sơ bộ là 200 giây. Nhưng tốc độ có thể thay đổi theo độ rộng hàng, index maintenance, trigger, cache và replica lag. Hãy cập nhật dự báo bằng throughput thực tế của các batch gần nhất thay vì dùng một phép đo ban đầu cho toàn bộ job.

Nếu số hàng đủ điều kiện giảm dần hoặc batch bị bỏ qua do khóa, rows affected có thể thấp hơn batch size. Cần phân biệt job đã hoàn tất với batch hiện tại chỉ không tìm thấy hàng trong phạm vi đã quét.

## 16. Ví dụ tổng hợp: dọn sự kiện đã hết hạn

Một hệ thống ghi 50 triệu sự kiện vào bảng events. Chính sách yêu cầu xóa các sự kiện cũ hơn 180 ngày. Bảng vẫn nhận dữ liệu mới liên tục; API đọc các sự kiện gần đây.

### Bước 1: Xác định phạm vi

Chọn cutoff cố định cho lần chạy và ghi nhận high-water mark:

```sql
SELECT MAX(event_id)
FROM events;
```

Cutoff và high-water mark được lưu vào job_progress. Nếu một sự kiện có event_id nhỏ hơn high-water mark nhưng occurred_at được cập nhật để trở thành cũ sau khi con trỏ đã đi qua, cần có vòng quét lại hoặc bảo đảm dữ liệu đủ điều kiện đã cố định trước khi job bắt đầu.

### Bước 2: Kiểm tra đường truy cập

Đánh giá các index hiện có. Một index trên occurred_at hỗ trợ lọc thời gian; index trên event_id hỗ trợ checkpoint và thứ tự. Có thể cần index ghép tùy phân bố. So sánh kế hoạch để biết số hàng phải đọc để lấy 2.000 hàng đủ điều kiện.

### Bước 3: Chạy batch

Trong mỗi transaction:

1. Chọn tối đa 2.000 event_id theo thứ tự ổn định.
2. Xóa các hàng đã chọn.
3. Lấy số hàng thực tế đã xóa.
4. Cập nhật tiến độ trong cùng transaction theo mô hình checkpoint đã chọn.
5. Commit.

Nếu có worker song song, cần claim hoặc khóa hàng để không xóa trùng. Nếu dùng SKIP LOCKED, các hàng bị bỏ qua phải được thử lại ở vòng quét sau.

### Bước 4: Điều tiết

Sau mỗi batch, kiểm tra thời gian commit, WAL bytes, I/O latency, lock wait, replica lag và p95 API. Nếu API chậm hoặc replica lag tăng, giảm batch size, giảm số worker hoặc tạm nghỉ.

### Bước 5: Xác minh

Sau khi job báo hoàn tất, kiểm tra lại số hàng còn thỏa predicate:

```sql
SELECT COUNT(*)
FROM events
WHERE occurred_at < :retention_cutoff
  AND event_id <= :high_water_mark;
```

Nếu còn hàng, xác định chúng bị bỏ qua do khóa, không nằm trong phạm vi đã quét hay lỗi điều kiện. Chỉ đánh dấu COMPLETED khi phạm vi mục tiêu đã được xử lý theo đúng quy tắc nghiệp vụ.

Các số liệu và batch size trong ví dụ là giả định. Cần đo trên hệ thống thật và xác nhận chính sách lưu giữ, foreign key, backup và replication trước khi chạy.

## 17. Khác biệt giữa các hệ quản trị

| Hệ quản trị | Cách thường dùng | Điểm cần kiểm tra |
|---|---|---|
| PostgreSQL | CTE chọn khóa với ORDER BY/LIMIT, UPDATE/DELETE USING, RETURNING, FOR UPDATE SKIP LOCKED | MVCC, WAL, vacuum, row locks, giới hạn của SKIP LOCKED |
| MySQL/InnoDB | UPDATE/DELETE với LIMIT trong các dạng hỗ trợ, keyset theo khóa, transaction commit từng batch | Undo/redo, purge, gap/next-key locks, replication và cú pháp LIMIT |
| SQL Server | CTE với TOP, UPDATE/DELETE JOIN, OUTPUT, lock hints có mục tiêu | Lock escalation, transaction log, isolation level, READPAST và row versioning |
| Oracle | Row limiting, FOR UPDATE SKIP LOCKED, PL/SQL loop, bulk processing | Undo, redo, row locks, consistent read và cơ chế commit |

Không nên sao chép nguyên cú pháp giữa các DBMS. Các hệ quản trị khác nhau về cách chọn hàng, khóa, giới hạn batch, trả về khóa đã thay đổi, cập nhật log và quản lý phiên bản. Hãy kiểm tra tài liệu phiên bản cụ thể và chạy thử trên dữ liệu đại diện.

## 18. Kiểm thử trước khi chạy production

Một quy trình bulk operation cần được thử như một workload, không chỉ kiểm tra câu SQL có chạy thành công:

1. Dùng bản sao dữ liệu có quy mô và phân bố gần thực tế.
2. Xác nhận predicate chọn đúng hàng; so sánh danh sách khóa mẫu với quy tắc nghiệp vụ.
3. Chạy một batch nhỏ và kiểm tra số hàng, giá trị trước/sau, trigger và cascade.
4. Mô phỏng lỗi giữa batch, trước commit và sau commit để xác nhận rollback/checkpoint.
5. Thử retry cùng batch để xác nhận idempotency.
6. Chạy đồng thời workload trực tuyến và quan sát lock wait, p95/p99, CPU, I/O.
7. Thử replica chậm hoặc tạm gián đoạn nếu môi trường cho phép; xác nhận job biết pause/resume.
8. Đo batch size khác nhau và chọn mức đáp ứng giới hạn.
9. Kiểm tra khả năng dừng thủ công và tiếp tục từ checkpoint.
10. Xác minh tổng số hàng, ràng buộc và dữ liệu liên quan sau khi hoàn tất.

Với DML có tác động lớn, cần biết chính xác cách môi trường thử nghiệm xử lý trigger, gửi thông điệp hoặc gọi tác vụ ngoài. Rollback transaction không nhất thiết đảo ngược side effect bên ngoài DB.

## 19. Những sai lầm thường gặp

- **Một transaction cho toàn bộ hàng triệu bản ghi:** giữ khóa và log lâu, rollback khó và không có điểm tiếp tục.
- **Batch quá nhỏ:** commit overhead và điều phối có thể chiếm phần lớn thời gian.
- **Batch quá lớn:** vẫn gây lock wait, log spike, spill và replication lag.
- **Dùng OFFSET tăng dần:** các batch sau phải bỏ qua ngày càng nhiều hàng.
- **Checkpoint chỉ theo timestamp không duy nhất:** có thể bỏ sót hàng cùng timestamp ở ranh giới.
- **Tiến checkpoint qua hàng bị SKIP LOCKED:** hàng bị bỏ qua có thể không bao giờ được xử lý.
- **Không có high-water mark hoặc điều kiện dừng:** job có thể chạy vô hạn khi dữ liệu mới liên tục xuất hiện.
- **Cập nhật lại giá trị không đổi:** tạo log và bảo trì index không cần thiết.
- **Không có index cho predicate và thứ tự batch:** mỗi batch có thể quét lại một vùng lớn.
- **Bỏ qua foreign key, trigger và cascade:** số hàng thay đổi thực tế lớn hơn dự kiến.
- **Retry không idempotent:** cập nhật lặp có thể tăng bộ đếm hoặc tạo side effect trùng.
- **Ghi checkpoint tách transaction:** lỗi giữa hai commit có thể làm lặp hoặc bỏ sót dữ liệu.
- **Chạy quá nhiều worker:** throughput có thể giảm vì lock, CPU, I/O và log tranh chấp.
- **Chỉ đo thời gian job:** bỏ qua p95/p99 của API và replication lag.
- **Coi hết batch là hoàn tất:** vẫn có thể còn hàng đủ điều kiện bị bỏ qua hoặc phát sinh trong lúc chạy.

## 20. Checklist vận hành UPDATE/DELETE theo batch

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Predicate có mô tả đúng tập dữ liệu nghiệp vụ không? | Có điều kiện, cutoff và phạm vi rõ ràng |
| Có khóa duy nhất và thứ tự ổn định không? | Checkpoint không bỏ sót hàng trùng khóa sắp xếp |
| Có high-water mark hoặc điều kiện dừng không? | Job có phạm vi hữu hạn |
| Batch query có index phù hợp không? | Execution plan không quét lặp quá mức |
| Batch size dựa trên đo đạc chưa? | Có thời gian, log, lock và throughput |
| Mỗi batch có transaction boundary rõ ràng không? | Commit và rollback có thể dự đoán |
| Checkpoint có commit cùng thay đổi không? | Không tiến tiến độ trước dữ liệu |
| Retry có an toàn và giới hạn không? | Idempotency và backoff được xác định |
| Có foreign key, trigger hoặc cascade không? | Phạm vi tác động thực tế đã được tính |
| Có nhiều worker hoặc SKIP LOCKED không? | Hàng bị bỏ qua được thử lại |
| Replica và workload trực tuyến có được giám sát không? | Có ngưỡng pause/throttle |
| Kết quả cuối đã được đối chiếu chưa? | Không còn hàng mục tiêu chưa xử lý |

## 21. Nguyên tắc ra quyết định

UPDATE/DELETE khối lượng lớn nên được xem là một workload có vòng đời, tiến độ và giới hạn tài nguyên. Chia batch giúp kiểm soát transaction, khóa, log và tác động đến hệ thống, nhưng chỉ hiệu quả khi mỗi đợt chọn được tập hàng xác định bằng khóa ổn định, dùng đường truy cập phù hợp và có checkpoint nhất quán.

Hãy bắt đầu bằng predicate nghiệp vụ, chọn khóa chia batch và high-water mark, sau đó đo batch size trong điều kiện tải đại diện. Commit theo từng đợt, ghi tiến độ cùng transaction, thiết kế retry idempotent và theo dõi lock wait, log/WAL, I/O, replica lag cùng p95/p99 của workload trực tuyến. Sau khi job kết thúc, xác minh lại toàn bộ phạm vi mục tiêu và các ràng buộc liên quan.

Một quy trình bulk operation tốt không chỉ hoàn tất nhanh. Nó phải có thể dừng, tiếp tục, chạy lại an toàn, không bỏ sót dữ liệu và giữ hiệu năng của các giao dịch khác trong giới hạn đã thống nhất.
