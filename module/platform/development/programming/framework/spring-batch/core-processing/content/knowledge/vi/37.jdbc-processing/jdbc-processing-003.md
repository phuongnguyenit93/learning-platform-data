# Paging khi dữ liệu thay đổi

Trong Spring Batch, `JdbcPagingItemReader` đọc dữ liệu database theo từng page. Reader dùng sort key để xác định thứ tự và vị trí tiếp tục giữa các page, nhưng việc chia page không tự tạo ra một snapshot bất biến của bảng. Trong lúc Job đang chạy, transaction khác vẫn có thể thêm, xóa hoặc cập nhật các dòng mà reader chưa đọc.

Khi dữ liệu thay đổi giữa các page, kết quả phụ thuộc vào chiến lược paging, sort key, điều kiện lọc, transaction isolation và cách Job xác định tập dữ liệu cần xử lý. Một Job có thể đọc thiếu record, đọc thêm record mới xuất hiện giữa chừng hoặc nhìn thấy nội dung khác nhau ở những page khác nhau. Nếu cần một tập dữ liệu nhất quán, phải thiết kế snapshot/high-watermark hoặc cơ chế cố định membership của lần chạy.

## 1. Paging không đồng nghĩa với snapshot

Paging giải quyết cách lấy dữ liệu theo từng nhóm. Nó không mặc định khóa bảng, giữ một transaction duy nhất cho toàn Job hoặc đóng băng mọi giá trị trong database.

Ví dụ một Job đọc bảng `orders` với page size 3:

```text
Ban đầu:
order_id: 10, 20, 30, 40, 50, 60

Page 1: 10, 20, 30
Page 2: 40, 50, 60
```

Nếu một transaction khác thay đổi bảng sau khi page đầu được đọc nhưng trước khi page tiếp theo được truy vấn, page 2 có thể nhìn thấy trạng thái mới. Kết quả cuối cùng khi đó không nhất thiết phản ánh dữ liệu tại một thời điểm duy nhất.

Nên phân biệt ba khái niệm:

- **Paging:** chia query thành các page để giới hạn lượng dữ liệu mỗi lần đọc.
- **Checkpoint:** lưu vị trí reader đã đạt đến tại ranh giới commit để có thể restart.
- **Snapshot consistency:** bảo đảm các page nhìn thấy cùng một tập dữ liệu hoặc cùng một phiên bản dữ liệu theo yêu cầu nghiệp vụ.

`JdbcPagingItemReader` hỗ trợ paging và checkpoint. Snapshot consistency phải được cung cấp bởi transaction isolation, query predicate, database snapshot/version hoặc thiết kế staging riêng.

## 2. JdbcPagingItemReader tiếp tục từ sort key

`JdbcPagingItemReader` dùng `PagingQueryProvider` để tạo query phù hợp với database. Sort key xác định thứ tự kết quả và giá trị cuối page được dùng làm điểm tiếp tục cho page sau. Câu SQL cụ thể tùy dialect/provider; về mặt logic, provider phải lấy các dòng đứng sau sort key đã đọc.

Ví dụ đọc đơn hàng theo `order_id`:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    Map<String, org.springframework.batch.item.database.Order> sortKeys =
            new LinkedHashMap<>();
    sortKeys.put("order_id",
            org.springframework.batch.item.database.Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, status, amount")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and status = 'READY'")
            .parameterValues(Map.of("tenantId", tenantId))
            .sortKeys(sortKeys)
            .pageSize(500)
            .saveState(true)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("amount")))
            .build();
}
```

`order_id` phải duy nhất trên tập kết quả và không được thay đổi trong lúc Job chạy. Nếu sort key không duy nhất, nhiều dòng có thể cùng nằm tại ranh giới page và reader không có thứ tự tổng thể đủ xác định để tiếp tục chính xác.

Nếu dùng nhiều cột, ví dụ `created_at` và `order_id`, tuple sort key phải duy nhất:

```java
Map<String, org.springframework.batch.item.database.Order> sortKeys =
        new LinkedHashMap<>();
sortKeys.put("created_at",
        org.springframework.batch.item.database.Order.ASCENDING);
sortKeys.put("order_id",
        org.springframework.batch.item.database.Order.ASCENDING);
```

`order_id` đóng vai trò tie-breaker khi nhiều dòng có cùng `created_at`. Các cột sort key cần được chọn trong query và được index phù hợp.

## 3. Dữ liệu thay đổi ảnh hưởng paging như thế nào?

Có bốn nhóm thay đổi cần quan tâm:

1. Insert: có dòng mới được thêm vào tập kết quả.
2. Delete: dòng chưa đọc bị xóa hoặc không còn thỏa điều kiện query.
3. Update sort key: dòng di chuyển đến vị trí trước hoặc sau checkpoint.
4. Update filter/payload: dòng đi vào/ra tập kết quả hoặc giá trị đọc được thay đổi.

Hệ quả phụ thuộc cách paging tiếp tục. Với keyset-style continuation theo sort key, thay đổi thứ tự hoặc filter vẫn có thể làm thiếu/trùng dữ liệu. Với offset pagination, insert/delete trước offset còn có thể làm dịch chuyển vị trí của các dòng sau.

## 4. Insert giữa các page

Giả sử reader dùng sort key tăng dần và đã đọc page đầu đến `order_id = 30`.

```text
Đã đọc:       10, 20, 30
Checkpoint:                 30
```

Sau đó transaction khác insert hai dòng:

```text
order_id = 15
order_id = 35
```

Khi page tiếp theo bắt đầu sau key 30:

- Dòng 15 nằm trước checkpoint nên thường không được đọc trong lần chạy hiện tại.
- Dòng 35 nằm sau checkpoint nên có thể được đọc nếu query không giới hạn tập dữ liệu tại thời điểm bắt đầu.

Điều này có thể đúng hoặc sai tùy nghiệp vụ. Nếu Job có nghĩa “đọc mọi record tồn tại tại thời điểm bắt đầu”, việc nhận thêm dòng 35 là không mong muốn. Nếu Job có nghĩa “đọc liên tục đến khi hết dữ liệu sẵn có”, việc đọc dòng mới có thể được chấp nhận nhưng cần có quy tắc dừng rõ ràng.

### Vì sao sort key tăng dần không đủ?

Sort key ổn định giúp reader không mất vị trí, nhưng không tự giới hạn membership. Nếu không có upper bound, mỗi page tiếp theo có thể thấy các dòng mới có key lớn hơn checkpoint. Nếu insert có key được gán thủ công hoặc key không tăng đơn điệu, dòng mới còn có thể xuất hiện phía sau checkpoint dù giá trị nhỏ hơn một số dòng đã tồn tại.

## 5. Delete giữa các page

Giả sử tập ban đầu là `10, 20, 30, 40, 50, 60` và page đầu đã đọc `10, 20, 30`. Trước page tiếp theo, dòng 40 bị xóa.

Với keyset continuation, query tiếp theo sau 30 sẽ trả `50, 60`; dòng 40 không còn tồn tại để đọc. Nếu nghiệp vụ yêu cầu xử lý mọi record từng tồn tại tại thời điểm bắt đầu, reader không thể đáp ứng điều đó chỉ bằng cách truy vấn bảng hiện tại.

Với offset pagination, xóa dòng trước offset có thể làm các dòng phía sau dịch chuyển về vị trí thấp hơn. Tùy cách tính offset của page tiếp theo, một dòng có thể bị đọc lặp hoặc bị bỏ qua.

Nếu cần bảo đảm membership không thay đổi khi nguồn có thể xóa record, hãy dùng snapshot/membership table, soft delete hoặc cơ chế lưu lịch sử dữ liệu. Không thể khôi phục một row đã bị xóa chỉ bằng sort key checkpoint.

## 6. Update sort key có thể gây thiếu hoặc trùng

Sort key nên bất biến trong suốt thời gian Job đọc. Nếu sort key thay đổi, một dòng có thể di chuyển qua vị trí checkpoint.

Ví dụ sort tăng dần theo `order_id`:

```text
Đã đọc đến: order_id = 30

Dòng chưa đọc ban đầu có order_id = 45
Transaction khác cập nhật order_id thành 25
```

Dòng đó giờ nằm trước checkpoint 30 và có thể bị bỏ sót.

Trường hợp ngược lại:

```text
Dòng đã đọc ban đầu có order_id = 20
Transaction khác cập nhật order_id thành 55
```

Nếu query sau checkpoint tìm các dòng có key lớn hơn 30, dòng đã đọc có thể xuất hiện lại ở page sau và bị xử lý trùng.

Khóa chính thường là sort key tốt hơn cột nghiệp vụ có thể chỉnh sửa, nhưng chỉ khi khóa đó thực sự bất biến và duy nhất trên kết quả query. Không cập nhật khóa dùng làm checkpoint trong thời gian Job đang chạy.

## 7. Update cột filter làm thay đổi membership

Không cần thay sort key để làm tập dữ liệu thay đổi. Chỉ cần một cột trong `WHERE` thay đổi là row có thể đi vào hoặc ra khỏi tập kết quả.

Ví dụ:

```sql
WHERE status = 'READY'
ORDER BY order_id ASC
```

Nếu transaction khác đổi một row chưa đọc từ `READY` sang `DONE`, row đó sẽ không còn được trả về. Nếu transaction đổi một row từ `PENDING` sang `READY` sau khi Job bắt đầu và key của nó lớn hơn checkpoint, row có thể được thêm vào page sau.

Vì vậy, cần xác định rõ:

- Trạng thái được kiểm tra tại thời điểm Job bắt đầu hay tại thời điểm từng page được truy vấn?
- Row được thêm vào `READY` giữa chừng có thuộc lần chạy hiện tại không?
- Row rời `READY` trước khi đọc có cần được xử lý theo snapshot ban đầu không?
- Có cần khóa/claim record để ngăn Job khác xử lý cùng row không?

Nếu không có câu trả lời rõ, Job có thể cho kết quả khác nhau giữa hai lần chạy dù input ban đầu giống nhau.

## 8. Update payload làm thay đổi nội dung đã đọc

Ngay cả khi membership và thứ tự ổn định, các cột được chọn vẫn có thể thay đổi.

Ví dụ, reader đã đọc `order_id = 1001` ở page đầu. Một transaction khác cập nhật `amount` trước khi page sau hoặc trước khi Job restart. Các row khác được đọc sau đó có thể phản ánh trạng thái mới, trong khi row 1001 đã được xử lý theo giá trị cũ.

Kết quả có thể là một output tổng hợp từ nhiều thời điểm khác nhau. Nếu yêu cầu là xuất đúng trạng thái dữ liệu tại một thời điểm, cần snapshot giá trị, không chỉ snapshot danh sách ID.

Các lựa chọn gồm:

- Database snapshot/temporal query tại một thời điểm hoặc version cụ thể.
- Copy các cột cần thiết vào bảng staging/snapshot khi tạo Job.
- Dùng version column và từ chối/ghi nhận row thay đổi kể từ snapshot.
- Dùng change data capture nếu mục tiêu là xử lý thay đổi theo luồng thay vì snapshot.

## 9. Offset pagination và keyset paging khi dữ liệu thay đổi

Hai cách tiếp cận có hành vi khác nhau:

| Tình huống | Offset pagination | Keyset/continuation theo sort key |
|---|---|---|
| Insert trước vị trí page tiếp theo | Có thể đẩy các row sang offset khác, gây lặp/thiếu. | Row mới nằm trước checkpoint thường không được đọc ở page sau. |
| Insert sau checkpoint | Có thể làm dịch chuyển offset của page sau. | Có thể được đọc nếu thỏa predicate và không có upper bound. |
| Delete trước page tiếp theo | Có thể làm các row dịch chuyển vị trí. | Không làm dịch chuyển checkpoint key, nhưng row bị xóa sẽ không còn được đọc. |
| Update sort key | Có thể thay đổi vị trí theo offset. | Có thể làm row di chuyển qua checkpoint, gây thiếu/trùng. |
| Page sâu | Offset lớn có thể tốn chi phí bỏ qua nhiều row. | Thường hiệu quả hơn khi có index phù hợp với sort key. |

`JdbcPagingItemReader` sử dụng `PagingQueryProvider` và sort keys để tạo query theo dialect database; provider thường dựa vào giá trị sort key cuối page để tiếp tục. Không nên suy luận rằng mọi paging reader tự tạo snapshot. Hãy kiểm tra query được sinh ra và semantics của provider đang dùng.

Keyset paging tránh một số vấn đề dịch chuyển offset, nhưng không giải quyết insert/delete/update membership và payload. Muốn có snapshot, cần thêm cơ chế cố định dữ liệu.

## 10. Chọn sort key bất biến và duy nhất

Sort key là một phần của hợp đồng restart. Một sort key phù hợp nên:

- Duy nhất trên từng row của kết quả query.
- Không null hoặc có quy tắc null rõ ràng.
- Không thay đổi trong lúc Job chạy.
- Có thứ tự so sánh ổn định trong database.
- Có index hỗ trợ query và predicate tiếp tục.
- Được giữ nguyên cùng chiều ASC/DESC qua restart.

Ví dụ nếu `created_at` có thể trùng, dùng composite key:

```sql
ORDER BY created_at ASC, order_id ASC
```

Với tuple này, `order_id` duy nhất đóng vai trò tie-breaker. Tuy nhiên, `created_at` cũng nên bất biến. Nếu `created_at` bị sửa sau khi row đã được đọc, tuple vẫn có thể di chuyển qua checkpoint.

Không dùng cột như `updated_at`, `status`, `priority` làm sort key nếu các giá trị này thay đổi trong khi Job chạy, trừ khi ứng dụng có cơ chế version/snapshot đảm bảo thứ tự không bị thay đổi.

## 11. Giới hạn tập dữ liệu bằng high-watermark

Một kỹ thuật đơn giản để tránh đọc thêm các row mới có key lớn hơn những row đã tồn tại lúc bắt đầu là chụp **high-watermark** trước khi đọc và thêm điều kiện upper bound vào query.

Ví dụ, tại thời điểm chuẩn bị Job, lấy ID lớn nhất của tenant:

```sql
SELECT COALESCE(MAX(order_id), 0)
FROM orders
WHERE tenant_id = :tenantId
```

Giả sử kết quả là `9000`. Reader dùng điều kiện:

```sql
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id <= :maxOrderId
ORDER BY order_id ASC
```

Các row được insert sau thời điểm chụp có `order_id > 9000` sẽ không lọt vào tập đọc của Job.

High-watermark hữu ích khi:

- Sort key là khóa tăng đơn điệu hoặc ít nhất bảo đảm row mới có key lớn hơn watermark.
- Muốn chốt phạm vi ID ở đầu Job.
- Không yêu cầu snapshot toàn bộ giá trị cột.
- Chấp nhận rằng delete/update trên các row cũ vẫn có thể ảnh hưởng kết quả.

High-watermark không phải snapshot đầy đủ. Nó không ngăn một transaction gán ID mới nhỏ hơn hoặc bằng watermark, không ngăn row cũ bị xóa, không ngăn status thay đổi và không giữ nguyên payload đã cập nhật.

## 12. Chụp high-watermark một lần và giữ qua restart

Không tính lại `MAX(order_id)` mỗi khi reader mở lại. Nếu restart lấy watermark mới, tập dữ liệu của cùng JobInstance có thể mở rộng và bao gồm các row được insert sau lần chạy đầu.

Có thể chụp watermark trong một bước chuẩn bị rồi lưu vào Job `ExecutionContext`:

```java
@Bean
Step captureOrderWatermarkStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("captureOrderWatermarkStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                Long tenantId = contribution.getStepExecution()
                        .getJobExecution()
                        .getJobParameters()
                        .getLong("tenant.id");

                Long maxId = jdbcTemplate.queryForObject(
                        """
                        SELECT COALESCE(MAX(order_id), 0)
                        FROM orders
                        WHERE tenant_id = ?
                        """,
                        Long.class,
                        tenantId);

                JobExecution jobExecution = contribution
                        .getStepExecution()
                        .getJobExecution();

                jobExecution.getExecutionContext()
                        .putLong("orders.maxOrderId", maxId);

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Reader đọc lại giá trị đã chụp:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobExecutionContext['orders.maxOrderId']}") Long maxOrderId) {

    Map<String, org.springframework.batch.item.database.Order> sortKeys =
            new LinkedHashMap<>();
    sortKeys.put("order_id",
            org.springframework.batch.item.database.Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, status, amount")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and order_id <= :maxOrderId and status = 'READY'")
            .parameterValues(Map.of(
                    "tenantId", tenantId,
                    "maxOrderId", maxOrderId))
            .sortKeys(sortKeys)
            .pageSize(500)
            .saveState(true)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("status"),
                    rs.getBigDecimal("amount")))
            .build();
}
```

Đây là mẫu minh họa cho Job có bước capture chạy một lần trước bước paging. Khi restart từ Step xử lý, Step capture đã hoàn tất nên watermark trong JobExecutionContext được dùng lại. Không cấu hình bước capture chạy lại khi đã hoàn tất nếu mục tiêu là giữ cùng input boundary.

Một lựa chọn khác là hệ thống launch truyền watermark thành JobParameter. Khi đó cần giữ nguyên identifying parameters qua restart của cùng JobInstance. Dù dùng JobParameters hay Job ExecutionContext, nguyên tắc là chỉ chụp một lần và không thay đổi trong lần nghiệp vụ đó.

## 13. Khi high-watermark chưa đủ: materialize membership

Nếu record có thể được insert với ID không đơn điệu, bị xóa hoặc thay đổi cột filter, chỉ dùng `MAX(id)` không đủ để cố định tập row. Có thể tạo bảng membership cho lần chạy:

```sql
INSERT INTO batch_run_order (run_id, order_id)
SELECT :runId, order_id
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY';
```

Reader paging qua membership đã chốt:

```sql
SELECT o.order_id, o.tenant_id, o.status, o.amount
FROM batch_run_order r
JOIN orders o ON o.order_id = r.order_id
WHERE r.run_id = :runId
ORDER BY o.order_id ASC
```

Tập `order_id` thuộc Job đã được cố định. Tuy nhiên, nếu reader join lại bảng `orders`, một row có thể bị xóa hoặc `amount` có thể thay đổi; membership ổn định không đồng nghĩa payload ổn định.

Nếu cần cả membership lẫn giá trị chính xác tại thời điểm bắt đầu, hãy copy các cột cần thiết vào snapshot table:

```sql
INSERT INTO batch_order_snapshot
    (run_id, order_id, tenant_id, customer_id, amount, status)
SELECT :runId, order_id, tenant_id, customer_id, amount, status
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY';
```

Reader sau đó chỉ đọc `batch_order_snapshot` theo `run_id` và sort key duy nhất. Cần có retention/cleanup cho snapshot và khóa duy nhất phù hợp, ví dụ `(run_id, order_id)`.

## 14. Snapshot isolation và transaction boundary

Database có các mức isolation khác nhau, nhưng cần chú ý transaction boundary của Spring Batch. Trong chunk-oriented Step, transaction thường được commit sau mỗi chunk. Một page query có thể chạy trong transaction của chunk, còn page tiếp theo có thể được đọc trong transaction sau.

Do đó:

- `READ COMMITTED` thường cho phép mỗi statement nhìn thấy các thay đổi đã commit trước statement đó.
- `REPEATABLE READ` hoặc snapshot isolation có semantics riêng theo database và transaction; snapshot thường không tự kéo dài xuyên qua nhiều chunk transaction.
- Một Job chạy nhiều chunk không mặc định có một database snapshot duy nhất từ đầu đến cuối.
- Giữ transaction mở cho toàn bộ Job có thể ảnh hưởng lock, undo/version retention, connection và khả năng phục hồi; không nên làm chỉ để hy vọng có snapshot.

Nếu cần consistent snapshot xuyên suốt nhiều page/chunk, hãy kiểm tra khả năng của database cụ thể. Có thể dùng database snapshot/version cố định, temporal/as-of query, snapshot export/import, materialized staging table hoặc quy trình capture dữ liệu riêng. Không giả định chỉ đổi isolation level ở transaction manager là đủ cho toàn bộ Job.

## 15. Dùng temporal/versioned data khi cần trạng thái tại một thời điểm

Một số hệ thống lưu lịch sử phiên bản row hoặc hỗ trợ truy vấn dữ liệu tại một thời điểm/version cụ thể. Khi đó, Job có thể nhận `snapshotTime`, `version` hoặc database-specific SCN/LSN làm input và mọi page đều đọc cùng version.

Khái niệm query:

```sql
SELECT order_id, amount, status
FROM orders_history
WHERE valid_from <= :snapshotTime
  AND (valid_to > :snapshotTime OR valid_to IS NULL)
  AND tenant_id = :tenantId
ORDER BY order_id ASC
```

Đây là ví dụ mô hình temporal do ứng dụng quản lý, không phải cú pháp chung của mọi database. Với tính năng temporal/as-of native, hãy dùng cú pháp theo vendor và kiểm thử query provider/paging dialect phù hợp.

Điểm quan trọng là mọi page và mọi lần restart phải dùng cùng snapshot version. Nếu snapshot version hết thời hạn lưu hoặc không còn truy cập được, Job phải báo lỗi rõ ràng thay vì âm thầm chuyển sang dữ liệu hiện tại.

## 16. Xử lý record theo trạng thái và claim/locking

Một mẫu khác là Job claim record để ngăn nhiều worker hoặc nhiều Job cùng xử lý. Ví dụ transaction cập nhật trạng thái một nhóm ID từ `READY` sang `PROCESSING` và gắn `run_id`:

```sql
UPDATE orders
SET status = 'PROCESSING', batch_run_id = :runId
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id <= :maxOrderId;
```

Reader sau đó paging theo `batch_run_id = :runId`. Cách này giúp xác định quyền sở hữu record, nhưng cần thiết kế atomicity, concurrency và recovery:

- Hai Job không được claim cùng record ngoài ý muốn.
- Claim cần có transaction/locking phù hợp.
- Job crash phải có quy trình giải phóng hoặc tiếp tục claim cũ.
- Không chuyển trạng thái sang `DONE` trước khi output được commit.
- Cần xử lý record đã claim nhưng writer thất bại.

Một số database hỗ trợ `FOR UPDATE SKIP LOCKED` hoặc cơ chế tương tự để nhiều worker claim các row khác nhau. Đây là tính năng phụ thuộc database; cần kiểm tra isolation, locking và execution plan trước khi dùng.

Không dùng locking dài hạn cho hàng triệu row nếu nó làm chặn ứng dụng giao dịch. Có thể claim theo batch nhỏ, dùng lease/owner token hoặc staging membership table.

## 17. Dữ liệu thay đổi khi Job restart

Checkpoint của `JdbcPagingItemReader` lưu vị trí tiếp tục dựa trên state reader và sort key. Nó không lưu bản sao mọi row chưa đọc. Nếu database thay đổi trước khi restart, cùng checkpoint có thể tạo ra tập kết quả khác.

Ví dụ:

```text
Lần đầu:
  Đọc đến order_id 300
  High-watermark = 900
  Checkpoint đã commit

Trước restart:
  Insert order_id 350
  Delete order_id 400
  Update status của order_id 450 từ READY sang DONE

Restart:
  Tiếp tục sau 300, với cùng watermark 900
```

Kết quả:

- `350` có thể được đọc dù không tồn tại ở thời điểm Job bắt đầu nếu chỉ dùng high-watermark.
- `400` không còn để đọc.
- `450` không còn thỏa filter `READY`.

Vì vậy, restart đúng vị trí không đồng nghĩa restart trên cùng tập dữ liệu. Nếu yêu cầu là xử lý đúng tập đã chọn ban đầu, cần giữ snapshot/membership và payload hoặc dùng dữ liệu versioned.

### Giữ nguyên JobParameters và query definition

Qua restart cùng JobInstance, cần giữ nguyên:

- Tenant/business scope.
- High-watermark hoặc snapshot version.
- Filter parameters.
- Sort key và hướng sort.
- Tên reader và `saveState`.
- Resource/query contract tương thích.

Nếu thay filter hoặc watermark, hãy tạo một JobInstance mới hoặc thực hiện quy trình recovery có kiểm soát. Không tái sử dụng checkpoint cũ với query mang semantics khác.

## 18. Dữ liệu mới đến liên tục: chốt batch boundary

Với bảng giao dịch liên tục nhận dữ liệu, Job cần có một định nghĩa rõ ràng về “đợt dữ liệu” đang xử lý.

Một số cách chốt batch boundary:

- **High-watermark ID:** xử lý ID không lớn hơn giá trị chụp đầu Job.
- **Business date/window:** xử lý các record thuộc ngày hoặc khoảng thời gian đã đóng.
- **Ingestion sequence:** xử lý đến sequence number đã được upstream xác nhận.
- **Manifest:** upstream gửi danh sách file hoặc record set đã hoàn tất.
- **Membership table:** materialize ID thuộc run trước khi paging.
- **CDC offset:** xử lý đến một log position/LSN cụ thể.

Không chỉ dùng `created_at <= now()` nếu đồng hồ nguồn không đồng bộ hoặc dữ liệu có thể đến muộn với timestamp cũ. Một ingestion sequence do nguồn quản lý có thể phù hợp hơn nếu nó phản ánh thứ tự commit/tiếp nhận đáng tin cậy.

## 19. Late-arriving data và overlap window

Một số hệ thống nhận record trễ nhưng mang business date cũ. Nếu Job chụp một khoảng thời gian rồi chạy một lần, record đến muộn có thể bị bỏ qua.

Có thể dùng overlap window:

```sql
WHERE business_date >= :previousWindowStart
  AND business_date < :currentWindowEnd
```

Lần chạy sau đọc chồng một khoảng thời gian trước đó rồi deduplicate theo business key hoặc version. Cách này phù hợp khi upstream có độ trễ giới hạn và hệ thống đích hỗ trợ upsert/deduplication.

Overlap window không phải snapshot. Nó là chiến lược bắt dữ liệu đến muộn bằng cách đọc lại một phần dữ liệu và xử lý idempotent. Cần xác định độ trễ tối đa, retention, khóa deduplication và quy tắc cập nhật bản ghi đã xuất.

## 20. Index và hiệu năng khi query theo checkpoint

Khi dữ liệu thay đổi, page query vẫn cần index hỗ trợ cả filter lẫn sort key. Ví dụ:

```sql
SELECT order_id, amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'READY'
  AND order_id > :lastOrderId
  AND order_id <= :maxOrderId
ORDER BY order_id ASC
```

Index minh họa:

```sql
CREATE INDEX idx_orders_tenant_status_id
    ON orders (tenant_id, status, order_id);
```

Index thực tế phụ thuộc database, selectivity và workload. Hãy xem execution plan của page đầu và page tiếp theo. Nếu query có điều kiện `OR` cho composite sort key, có thể cần index phù hợp hoặc biểu thức rewrite theo khả năng optimizer.

Chỉ chọn các cột cần dùng để giảm I/O và mapping cost. Tránh function trên sort key nếu nó khiến database không thể sử dụng index hiệu quả. Đo query latency, số page, lock wait và database load khi có concurrent writer.

## 21. Test thay đổi dữ liệu giữa các page

Test thông thường chỉ seed dữ liệu rồi đọc đến EOF sẽ không phát hiện race condition. Cần chủ động thay đổi dữ liệu giữa hai page.

Một fixture nhỏ có page size 2:

```text
Ban đầu: 10, 20, 30, 40, 50
Page 1: 10, 20
```

Sau page đầu, test transaction khác insert/delete/update rồi cho reader đọc tiếp. Các tình huống nên có test riêng:

| Thay đổi giữa page | Điều cần xác nhận |
|---|---|
| Insert key nhỏ hơn checkpoint | Row không được âm thầm xuất hiện phía sau; policy late-arrival phải rõ. |
| Insert key lớn hơn checkpoint nhưng dưới max | Xác nhận có/không nhận theo snapshot policy. |
| Insert key lớn hơn high-watermark | Không được đọc nếu query áp dụng upper bound. |
| Delete row chưa đọc | Xác nhận semantics: bỏ qua, fail hoặc đọc từ snapshot. |
| Update sort key từ sau về trước checkpoint | Phát hiện nguy cơ mất row. |
| Update sort key từ trước về sau checkpoint | Phát hiện nguy cơ đọc trùng. |
| Update filter status | Xác nhận membership theo policy. |
| Update payload | Xác nhận snapshot values hay latest values được yêu cầu. |
| Restart sau thay đổi | Cùng checkpoint phải dùng cùng snapshot/membership theo hợp đồng. |

Test nên dùng database engine gần production vì query provider, isolation và locking khác nhau giữa các vendor. H2 có thể hữu ích cho test nhanh nhưng không chứng minh paging SQL hoặc snapshot semantics giống database production.

## 22. Đồng bộ test mà không dùng sleep tùy ý

Để tái hiện thay đổi giữa hai page, cần một điểm đồng bộ xác định:

1. Reader đọc xong page đầu hoặc test fixture xác nhận đã qua checkpoint mong muốn.
2. Test thread thực hiện insert/update/delete trong transaction riêng.
3. Transaction thay đổi commit.
4. Reader tiếp tục lấy page kế tiếp.
5. Test kiểm tra chính xác các item được đọc.

Có thể dùng `CountDownLatch`, barrier, test hook hoặc một service được mock để đồng bộ. Tránh `Thread.sleep(500)` rồi hy vọng reader đã đọc xong page; cách đó dễ flaky trên CI.

Nếu cần kiểm thử restart, phải tạo checkpoint đã commit, kết thúc execution theo cách kiểm soát, thay đổi database, rồi restart cùng JobInstance với cùng parameters. Kiểm tra cả output và `StepExecution` counters.

## 23. Kiểm thử high-watermark

Test high-watermark cần xác nhận giá trị được chụp đúng một lần và dùng lại khi restart:

1. Seed các ID 10, 20, 30, 40.
2. Chạy bước capture và xác nhận watermark là 40.
3. Đọc page đầu đến checkpoint.
4. Insert ID 50.
5. Restart cùng JobInstance.
6. Xác nhận ID 50 không được đọc vì `order_id <= 40`.
7. Xác nhận reader vẫn đọc các ID còn lại trong phạm vi đã chốt.

Thêm test cho dữ liệu không tuân thủ giả định đơn điệu, ví dụ insert ID 25 sau khi watermark 40 đã chụp. Test này minh họa high-watermark không thể loại trừ row mới có key nằm dưới upper bound. Nếu trường hợp đó có thể xảy ra trong hệ thống, cần membership snapshot hoặc một ingestion sequence đáng tin cậy hơn.

## 24. Kiểm thử membership snapshot

Nếu dùng bảng `batch_run_order`, hãy kiểm tra:

- Membership được tạo trong một transaction nhất quán theo yêu cầu.
- Mỗi `(run_id, order_id)` chỉ xuất hiện một lần.
- Reader chỉ lấy row của đúng `run_id`.
- Insert mới vào bảng gốc sau khi capture không tự động vào membership.
- Delete/update bảng gốc có hành vi đã định nghĩa.
- Nếu snapshot chứa payload, thay đổi bảng gốc không làm thay đổi output của run.
- Restart đọc tiếp cùng snapshot và không tạo membership mới.
- Cleanup snapshot chỉ chạy sau khi Job và thời hạn restart/reprocess kết thúc.

Nếu capture membership dùng `INSERT ... SELECT`, cần xác định transaction isolation của câu lệnh đó. Một statement thường nhìn thấy một snapshot theo semantics database tại thời điểm statement thực thi, nhưng semantics cụ thể phụ thuộc engine và isolation level.

## 25. Retry, idempotency và dữ liệu thay đổi

Paging checkpoint không bảo đảm writer side effect chỉ xảy ra đúng một lần. Nếu chunk bị rollback hoặc process mất kết nối trong lúc commit, một số thao tác có thể cần được thử lại hoặc đối soát.

Đặc biệt với writer gọi API ngoài transaction:

- Dùng idempotency key ổn định theo business record/run.
- Lưu operation ID để tra cứu trạng thái khi timeout.
- Dùng outbox nếu cần phối hợp database commit và message/API delivery.
- Không dựa vào `order_id` đơn lẻ nếu cùng row có thể được xử lý trong nhiều business run; có thể cần `(run_id, order_id)`.
- Kiểm tra output unique key để ngăn duplicate khi restart.

Nếu source row thay đổi sau khi đã được đọc, writer nên ghi nhận version/source timestamp đã xử lý nếu nghiệp vụ cần audit. Điều đó giúp phân biệt bản ghi đã xuất theo snapshot cũ với bản cập nhật đến sau.

## 26. Những lỗi thường gặp

### Nghĩ paging tự tạo snapshot

Reader chia query thành page, nhưng không đóng băng bảng. Chốt snapshot/high-watermark hoặc membership nếu cần dữ liệu nhất quán.

### Sort key không duy nhất

Các row trùng key ở ranh giới page có thể bị bỏ sót. Dùng unique key hoặc composite key có tie-breaker.

### Dùng sort key có thể thay đổi

Row có thể di chuyển qua checkpoint và bị đọc thiếu/trùng. Ưu tiên key bất biến.

### Không giới hạn insert mới

Keyset query có thể đọc row mới có key lớn hơn checkpoint. Dùng high-watermark nếu giả định monotonic key phù hợp.

### Cho rằng high-watermark giải quyết mọi thay đổi

Watermark không ngăn delete, update filter/payload hoặc insert có key thấp hơn watermark. Dùng snapshot/membership khi cần bảo đảm mạnh hơn.

### Tính lại watermark khi restart

Tập dữ liệu của JobInstance thay đổi. Capture một lần và giữ nguyên trong JobParameters/JobExecutionContext.

### Đổi filter hoặc sort key giữa restart

Checkpoint cũ không còn tương ứng query cũ. Giữ query contract ổn định hoặc tạo JobInstance mới.

### Dựa vào transaction isolation mà không xét chunk boundary

Snapshot của một transaction chunk không nhất thiết kéo dài qua toàn Job. Kiểm tra semantics database và ranh giới transaction thực tế.

### Chỉ test dữ liệu tĩnh

Race condition chỉ xuất hiện khi có thay đổi giữa các page. Tạo test đồng bộ để insert/delete/update giữa hai lần đọc.

### Dùng H2 để kết luận production database giống hệt

Paging provider, locking và isolation khác nhau. Chạy integration test trên database engine gần production cho các semantics quan trọng.

## 27. Quy trình chọn chiến lược paging khi dữ liệu thay đổi

Khi thiết kế Job đọc bảng đang được ứng dụng khác cập nhật, hãy trả lời các câu hỏi theo thứ tự:

1. Job cần đọc dữ liệu tại thời điểm bắt đầu hay chấp nhận dữ liệu mới xuất hiện trong lúc chạy?
2. Sort key có duy nhất, không null và bất biến không?
3. Các cột filter có thể thay đổi trong khi Job chạy không?
4. Row có thể bị xóa hoặc payload có thể được cập nhật trước khi reader đến không?
5. Có thể chụp một high-watermark đáng tin cậy không?
6. High-watermark có loại trừ được mọi insert mới theo quy tắc cấp ID không?
7. Có cần snapshot cả membership hay cả payload?
8. Database hỗ trợ isolation/snapshot/temporal query nào và transaction chunk ảnh hưởng ra sao?
9. Checkpoint và restart có dùng lại cùng query parameters, sort keys và snapshot version không?
10. Writer có idempotent nếu item được đọc lại sau rollback/restart không?
11. Integration test có mô phỏng insert/delete/update giữa các page và restart không?
12. Index và execution plan có đáp ứng hiệu năng khi bảng đang có concurrent workload không?

| Yêu cầu nghiệp vụ | Chiến lược thường phù hợp |
|---|---|
| Chấp nhận đọc thêm record mới có key lớn trong lúc chạy | Keyset paging với sort key ổn định; định nghĩa rõ điều kiện dừng. |
| Chỉ xử lý record tồn tại đến một ID boundary | High-watermark cố định và predicate `key <= watermark`. |
| Cố định chính xác tập ID tại lúc bắt đầu | Materialize membership vào bảng staging. |
| Cố định cả ID và giá trị payload | Copy dữ liệu cần thiết vào snapshot table hoặc dùng temporal/versioned query. |
| Xử lý record đến muộn | Overlap window + deduplication/upsert hoặc CDC. |
| Nhiều Job cùng lấy record chưa xử lý | Claim/lease/locking có owner và recovery rõ ràng. |
| Restart sau khi source tiếp tục thay đổi | Giữ snapshot/version/membership và checkpoint của cùng JobInstance. |

## Kết luận

`JdbcPagingItemReader` và `PagingQueryProvider` giúp đọc dữ liệu theo page và tiếp tục từ sort key, nhưng không tự bảo đảm mọi page nhìn thấy cùng một snapshot của database. Insert sau checkpoint có thể được đọc thêm, insert trước checkpoint có thể bị bỏ qua, delete làm mất row chưa đọc, còn update sort key/filter/payload có thể làm thay đổi thứ tự, membership hoặc giá trị được xuất. Hãy dùng sort key duy nhất và bất biến, giữ query/parameters ổn định qua restart, và chọn mức cố định dữ liệu theo yêu cầu: high-watermark cho phạm vi key đơn điệu, membership table cho tập ID, snapshot table/temporal query cho cả payload. Transaction isolation phải được xem cùng chunk boundary vì snapshot của một transaction không mặc định kéo dài suốt Job. Kiểm thử các thay đổi giữa page, restart và writer idempotency trên database gần production để chứng minh Job không âm thầm đọc thiếu, trùng hoặc trộn dữ liệu từ những thời điểm khác nhau.
