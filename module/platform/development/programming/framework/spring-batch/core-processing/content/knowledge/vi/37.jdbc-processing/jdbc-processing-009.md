# Isolation level và repeatable read

Trong Spring Batch, chunk-oriented Step thường đọc, xử lý và ghi dữ liệu database trong các transaction lặp lại. Khi nhiều Job hoặc ứng dụng cùng truy cập một bảng, dữ liệu có thể bị thay đổi giữa lúc reader truy vấn và lúc processor/writer hoàn tất. Transaction isolation level xác định mức độ một transaction nhìn thấy thay đổi của transaction khác.

`REPEATABLE_READ` là một mức isolation trong JDBC và Spring. Mục tiêu của nó là bảo đảm một transaction đọc lại cùng một row thì không thấy giá trị row đó thay đổi bởi transaction khác trước khi transaction hiện tại kết thúc. Tuy nhiên, hành vi cụ thể đối với phantom rows và snapshot phụ thuộc database. Ngoài ra, trong Spring Batch, transaction thường được tạo theo từng chunk; vì vậy `REPEATABLE_READ` trên chunk không mặc nhiên tạo một snapshot nhất quán cho toàn bộ Job.

Để chọn đúng isolation level, cần hiểu anomaly nào cần ngăn chặn, transaction boundary của Step nằm ở đâu, reader có dùng cùng connection với chunk transaction hay không, và database thực thi isolation theo lock hay MVCC.

## 1. Transaction isolation là gì?

Transaction isolation mô tả mức độ các transaction đồng thời có thể quan sát thay đổi của nhau. Khi nhiều transaction đọc và ghi cùng dữ liệu, isolation level quyết định một transaction có thể nhìn thấy dữ liệu chưa commit, dữ liệu đã thay đổi giữa hai lần đọc, hoặc các row mới thỏa mãn cùng điều kiện truy vấn hay không.

Ví dụ hai transaction cùng làm việc với tài khoản:

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT balance -> 1,000
                                      UPDATE balance = 800
                                      COMMIT
SELECT balance -> ?
COMMIT
```

Giá trị mà lần `SELECT` thứ hai của A nhìn thấy phụ thuộc isolation level và cách database triển khai nó. Isolation không làm các transaction chạy tuần tự hoàn toàn trong mọi trường hợp; nó đặt ra những bảo đảm về dữ liệu mà mỗi transaction được phép quan sát.

Trong Spring Batch, điều này quan trọng khi reader lấy dữ liệu từ database, processor kiểm tra hoặc tính toán dựa trên dữ liệu đọc được, và writer cập nhật bảng trong cùng hoặc các transaction khác nhau.

## 2. Các mức isolation trong JDBC

JDBC định nghĩa các hằng số isolation trong `Connection`:

| JDBC constant | Spring constant | Ý nghĩa khái quát |
|---|---|---|
| `TRANSACTION_READ_UNCOMMITTED` | `ISOLATION_READ_UNCOMMITTED` | Có thể đọc thay đổi chưa commit của transaction khác |
| `TRANSACTION_READ_COMMITTED` | `ISOLATION_READ_COMMITTED` | Chỉ đọc dữ liệu đã commit; hai lần đọc có thể thấy giá trị khác nhau |
| `TRANSACTION_REPEATABLE_READ` | `ISOLATION_REPEATABLE_READ` | Bảo đảm mạnh hơn cho việc đọc lại cùng row; phantom behavior phụ thuộc database |
| `TRANSACTION_SERIALIZABLE` | `ISOLATION_SERIALIZABLE` | Mức cô lập mạnh nhất theo mô hình transaction serializable; có thể tăng contention hoặc abort transaction |
| — | `ISOLATION_DEFAULT` | Dùng isolation mặc định của database/driver |

Không phải mọi database đều hỗ trợ mọi mức theo cùng cách. Một số database ánh xạ mức isolation JDBC sang cơ chế nội bộ riêng, hoặc không hỗ trợ `READ_UNCOMMITTED` độc lập. Cần đọc tài liệu database và kiểm thử với driver thực tế.

## 3. Dirty read

Dirty read xảy ra khi transaction A đọc dữ liệu mà transaction B đã thay đổi nhưng chưa commit. Nếu B rollback, A đã đọc một giá trị chưa bao giờ trở thành dữ liệu được commit.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
                                      UPDATE account
                                      SET balance = 0
SELECT balance -> 0
                                      ROLLBACK
```

Nếu A dùng giá trị 0 để tạo báo cáo hoặc quyết định ghi dữ liệu khác, kết quả có thể sai vì B đã rollback.

`READ_COMMITTED` trở lên ngăn dirty read theo mô hình chuẩn. `READ_UNCOMMITTED` cho phép anomaly này, dù một số database vẫn không thực sự cung cấp dirty reads do cách lưu trữ/MVCC.

Với dữ liệu tài chính, tồn kho hoặc trạng thái nghiệp vụ quan trọng, không nên chọn `READ_UNCOMMITTED` chỉ để tăng throughput nếu chưa chứng minh được rằng dữ liệu chưa commit có thể chấp nhận.

## 4. Non-repeatable read

Non-repeatable read xảy ra khi một transaction đọc cùng một row hai lần nhưng nhận giá trị khác nhau vì transaction khác đã cập nhật và commit row đó giữa hai lần đọc.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT price -> 100
                                      UPDATE product
                                      SET price = 120
                                      COMMIT
SELECT price -> 120
COMMIT
```

`READ_COMMITTED` cho phép tình huống này: mỗi câu SELECT có thể nhìn thấy snapshot/phiên bản mới nhất đã commit tại thời điểm câu lệnh chạy.

`REPEATABLE_READ` được thiết kế để ngăn việc đọc lại cùng row thấy giá trị đã bị transaction khác thay đổi trong khi transaction hiện tại còn mở. Database có thể thực hiện bằng row locks, snapshot/MVCC hoặc kết hợp các cơ chế.

## 5. Phantom read

Phantom read xảy ra khi một transaction chạy lại một truy vấn theo điều kiện và thấy thêm hoặc mất các row thỏa mãn điều kiện, do transaction khác insert/delete/update row làm thay đổi tập kết quả.

```text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN
SELECT * FROM orders
WHERE status = 'NEW' -> 10 rows
                                      INSERT new order
                                      SET status = 'NEW'
                                      COMMIT
SELECT * FROM orders
WHERE status = 'NEW' -> 11 rows
COMMIT
```

Theo mô hình SQL chuẩn, `REPEATABLE_READ` ngăn non-repeatable read nhưng vẫn có thể cho phép phantom read. `SERIALIZABLE` nhằm ngăn các anomaly này bằng cách làm kết quả tương đương một thứ tự thực thi tuần tự.

Tuy nhiên, không nên áp dụng kết luận về phantom một cách máy móc cho mọi database. Ví dụ, PostgreSQL dùng snapshot isolation cho `REPEATABLE READ`, nên các câu SELECT thông thường trong cùng transaction nhìn thấy cùng snapshot và không thấy phantom theo cách trên; nhưng snapshot isolation vẫn có thể cho phép một số serialization anomaly. MySQL InnoDB có các quy tắc riêng giữa consistent reads và locking reads, cùng next-key/gap locks trong một số tình huống. Hãy kiểm tra semantics cụ thể của database đang chạy.

## 6. Repeatable read bảo đảm điều gì?

Ở mức khái quát, `REPEATABLE_READ` giúp transaction đọc lại cùng row và nhận cùng dữ liệu mà transaction đó đã quan sát trước đó, bất kể transaction khác đã commit update row sau lần đọc đầu.

Ví dụ:

```text
Transaction A (REPEATABLE_READ)       Transaction B
--------------------------------       -------------
BEGIN
SELECT balance -> 1,000
                                       BEGIN
                                       UPDATE balance = 800
                                       COMMIT
SELECT balance -> 1,000
COMMIT
```

Ở database dùng snapshot/MVCC, A có thể tiếp tục nhìn thấy phiên bản row tại snapshot của A. Ở database dùng locking, B có thể phải chờ hoặc A giữ lock tùy câu lệnh và cách triển khai.

Điểm cần nhớ: `REPEATABLE_READ` áp dụng trong phạm vi một transaction. Khi transaction kết thúc, bảo đảm đó kết thúc. Một transaction mới có thể thấy giá trị mới đã commit.

## 7. Repeatable read không đồng nghĩa serializable

`REPEATABLE_READ` và `SERIALIZABLE` không thể thay thế cho nhau trong mọi trường hợp.

| Tiêu chí | `REPEATABLE_READ` | `SERIALIZABLE` |
|---|---|---|
| Dirty read | Bị ngăn | Bị ngăn |
| Non-repeatable read | Bị ngăn | Bị ngăn |
| Phantom read | Theo chuẩn có thể xảy ra; database có thể cung cấp bảo đảm mạnh hơn | Được ngăn theo semantics serializable |
| Concurrent throughput | Thường cao hơn serializable | Có thể thấp hơn do lock hoặc transaction abort |
| Nguy cơ deadlock/serialization failure | Có thể có, tùy DB và query | Thường cần chuẩn bị retry khi xung đột |
| Phù hợp | Cần đọc lại row ổn định trong transaction | Quy tắc nghiệp vụ cần kết quả tương đương thực thi tuần tự |

Snapshot isolation ở một số database có thể ngăn nhiều anomaly hơn định nghĩa SQL tối thiểu của repeatable read, nhưng không tự động tương đương serializable. Ví dụ, hai transaction có thể cùng đọc một tập dữ liệu rồi cập nhật hai row khác nhau dựa trên cùng một điều kiện, dẫn đến write skew nếu database không phát hiện xung đột serialization.

Nếu quy tắc nghiệp vụ phụ thuộc vào một bất biến trên nhiều row, chỉ chọn `REPEATABLE_READ` chưa chắc đủ. Có thể cần constraint ở database, locking phù hợp hoặc `SERIALIZABLE`.

## 8. Isolation level trong chunk-oriented Step

Spring Batch thường tạo transaction cho từng chunk. Với chunk size 100, một transaction bao quanh một nhóm item được đọc, xử lý, ghi và commit.

```text
Step bắt đầu
   |
   +--> Transaction chunk 1
   |       read/process/write 1..100
   |       update stream state
   |       commit
   |
   +--> Transaction chunk 2
   |       read/process/write 101..200
   |       update stream state
   |       commit
   |
   +--> Transaction chunk 3
           read/process/write 201..300
           update stream state
           commit
```

Isolation level được cấu hình cho transaction do Step tạo. Nếu dùng `REPEATABLE_READ`, bảo đảm đọc lặp lại tồn tại trong từng chunk transaction tương ứng.

Điều đó không có nghĩa toàn bộ Step giữ một snapshot từ item đầu tiên đến item cuối cùng. Sau khi chunk 1 commit, chunk 2 bắt đầu transaction mới và có thể thấy dữ liệu đã thay đổi sau commit của chunk 1.

Ví dụ, cùng một bảng được query trong chunk 1 và chunk 5. Một ứng dụng khác cập nhật bảng giữa hai chunk. `REPEATABLE_READ` của chunk 1 không buộc chunk 5 tiếp tục nhìn thấy snapshot của chunk 1.

## 9. Cấu hình isolation cho Step

Có thể đặt isolation level trên transaction attribute của chunk Step. Ví dụ:

```java
@Bean
public Step reconcileOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ReconciledOrder> processor,
        ItemWriter<ReconciledOrder> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("reconcileOrdersStep", jobRepository)
            .<Order, ReconciledOrder>chunk(100, transactionManager)
            .transactionAttribute(transactionAttribute)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Các import chính:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;
import org.springframework.transaction.PlatformTransactionManager;
```

`transactionAttribute(...)` cấu hình thuộc tính transaction của chunk. `ISOLATION_REPEATABLE_READ` là hằng số Spring tương ứng với JDBC `Connection.TRANSACTION_REPEATABLE_READ`.

Nếu không chỉ định isolation, Spring thường dùng `ISOLATION_DEFAULT`, tức mức mặc định của database/connection. Đó thường là lựa chọn ban đầu hợp lý; chỉ nâng isolation khi có anomaly cụ thể cần ngăn chặn và đã đo tác động.

## 10. Phân biệt isolation của Step với @Transactional

Có thể thấy annotation như:

```java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public void processBatch() {
    // database operations
}
```

Annotation này áp dụng khi Spring mở một transaction mới cho method được proxy quản lý. Trong chunk Step, transaction thường đã được Spring Batch mở bởi `PlatformTransactionManager` trước khi gọi reader/processor/writer.

Nếu method writer/processor dùng propagation `REQUIRED`, nó thường tham gia transaction đang có. Isolation khai báo trên method không thể nâng cấp isolation của transaction đã bắt đầu. Vì vậy, để đặt isolation cho chunk transaction, cấu hình transaction attribute trên Step là rõ ràng hơn.

Nếu dùng `REQUIRES_NEW`, method tạo transaction riêng. Khi đó, nó không còn cùng atomic boundary với chunk transaction; commit của method có thể tồn tại ngay cả khi chunk ngoài rollback. Không dùng propagation này chỉ để cố thay đổi isolation nếu chưa đánh giá hệ quả checkpoint và consistency.

Với transaction manager khác nhau hoặc nhiều `DataSource`, mỗi transaction manager quản lý connection/resource riêng. Isolation trên transaction manager của Step không tự áp dụng sang một database khác.

## 11. DataSourceTransactionManager và JDBC connection

Transaction manager JDBC quản lý connection gắn với transaction. Khi bắt đầu transaction, nó lấy connection từ `DataSource`, cấu hình read-only/isolation/auto-commit phù hợp, rồi bind connection vào transaction context để các thao tác JDBC tham gia transaction đó có thể dùng chung connection.

Khi Step yêu cầu `REPEATABLE_READ`, transaction manager cố gắng đặt isolation tương ứng trên connection trước khi transaction thực thi câu SQL. Khi transaction kết thúc, connection được trả về pool và các thuộc tính cần được khôi phục theo cơ chế transaction manager/connection pool.

Điều kiện quan trọng:

- Reader/writer phải dùng `DataSource` tham gia cùng transaction manager nếu muốn cùng transaction.
- JDBC access cần lấy connection theo cơ chế Spring-aware, ví dụ `JdbcTemplate` hoặc `DataSourceUtils`.
- Dùng trực tiếp `dataSource.getConnection()` trong code có thể tạo connection khác và không tham gia transaction đang có.
- Database/driver phải hỗ trợ isolation được yêu cầu.
- Connection pool không được giữ lại isolation state sai giữa các lần mượn connection.

Không nên thay isolation trên một connection sau khi transaction đã bắt đầu. Database có thể từ chối hoặc không áp dụng thay đổi đó như mong đợi.

## 12. Reader có dùng cùng transaction connection không?

Không phải mọi reader database đều đọc qua cùng connection mà chunk writer sử dụng. Đây là chi tiết rất quan trọng khi suy luận về isolation.

| Thành phần | Cách truy cập thường gặp | Điều cần kiểm tra |
|---|---|---|
| `JdbcTemplate` trong processor/service | Có thể tham gia transaction hiện tại nếu dùng cùng DataSource | Có dùng đúng transaction manager/DataSource không |
| `JdbcBatchItemWriter` | Thường tham gia transaction của Step khi cùng DataSource | Có cấu hình đúng transaction manager không |
| `JdbcPagingItemReader` | Thực thi query theo page qua JDBC infrastructure | Kiểm tra connection và transaction participation của phiên bản/cấu hình |
| `JdbcCursorItemReader` mặc định | Mở cursor bằng connection riêng để giữ cursor trong Step | Isolation của cursor connection không tự động được quyết định bởi chunk transaction attribute |
| Custom reader dùng `dataSource.getConnection()` | Thường tạo connection riêng nếu không dùng Spring transaction-aware access | Cần tham gia transaction hoặc cấu hình isolation riêng |

Một câu `SELECT` chỉ được bảo vệ bởi isolation level của transaction trên connection thực thi câu SELECT đó. Cấu hình `REPEATABLE_READ` cho chunk không thể tự bảo vệ một query chạy trên connection độc lập với transaction khác.

## 13. Lưu ý đặc biệt với JdbcCursorItemReader

`JdbcCursorItemReader` thường mở một connection riêng để giữ `ResultSet` cursor trong khi các chunk transaction được commit lần lượt. Vì vậy, transaction attribute của chunk Step không nhất thiết đặt isolation cho connection đang giữ cursor.

Cursor connection có isolation và transaction behavior riêng theo cấu hình reader, driver và database. Nếu cần một snapshot nhất quán cho toàn cursor, phải kiểm tra isolation của chính connection đó và cách database giữ snapshot trong suốt thời gian cursor mở.

`useSharedExtendedConnection` cho phép một số cấu hình dùng connection mở rộng chia sẻ với transaction của Step, thông qua `ExtendedConnectionDataSourceProxy` và yêu cầu driver hỗ trợ cursor holdability qua commit. Đây là cấu hình nâng cao; không phải driver/database nào cũng hỗ trợ.

Không nên bật shared extended connection chỉ để “bật repeatable read”. Trước tiên cần xác định cursor đang dùng connection nào, database snapshot được tạo khi nào, cursor tồn tại qua commit ra sao và transaction ghi có ảnh hưởng gì đến cursor.

## 14. JdbcPagingItemReader và repeatable read

`JdbcPagingItemReader` chia việc đọc thành nhiều query theo page. Nếu các page query tham gia các chunk transaction khác nhau, mỗi transaction có thể nhìn thấy snapshot khác nhau. Một row mới được thêm hoặc một row cũ bị thay đổi giữa các page có thể ảnh hưởng tập dữ liệu mà reader nhìn thấy, tùy isolation và sort key.

Nếu tất cả query page tham gia cùng một transaction `REPEATABLE_READ` kéo dài, snapshot có thể nhất quán hơn nhưng điều đó có thể làm transaction và snapshot tồn tại lâu, tăng áp lực database. Trong chunk Step tiêu chuẩn, transaction thường kết thúc sau mỗi chunk; không nên giả định mọi page của cả Step thuộc một transaction duy nhất.

Để paging ổn định, cần:

- Dùng sort key xác định và duy nhất.
- Cố định phạm vi dữ liệu bằng batch ID, ngày nghiệp vụ hoặc high-water mark.
- Tránh để record mới chen vào giữa các page theo thứ tự sort.
- Dùng snapshot/staging nếu cần cùng một tập dữ liệu xuyên suốt toàn Step.
- Kiểm thử khi nguồn bị insert/update/delete trong lúc Job đang đọc.

## 15. Repeatable read không bảo đảm snapshot cho toàn Job

Giả sử Step có 10.000 item, chunk size 100. Step sẽ tạo khoảng 100 transaction chunk. Với `REPEATABLE_READ`, mỗi chunk có thể có snapshot riêng.

```text
Chunk 1 transaction: snapshot S1
       commit
Chunk 2 transaction: snapshot S2
       commit
Chunk 3 transaction: snapshot S3
       commit
       ...
Chunk 100 transaction: snapshot S100
```

Nếu một bảng tham chiếu được cập nhật giữa chunk 1 và chunk 2, chunk 2 có thể nhìn thấy phiên bản mới. Trong cùng chunk 1, các lần đọc lại row có thể vẫn thấy phiên bản cũ.

Nếu yêu cầu nghiệp vụ là toàn bộ Job phải xử lý cùng một phiên bản dữ liệu tham chiếu, có một số hướng:

- Tạo snapshot/version ID của dữ liệu tham chiếu và truyền version đó vào mọi query.
- Copy tập dữ liệu cần xử lý vào staging table theo batch ID trước khi chạy các chunk.
- Dùng temporal table hoặc query theo `effective_at`/version đã chốt.
- Dùng database snapshot hoặc transaction dài chỉ khi database và vận hành cho phép, sau khi đánh giá lock, MVCC retention và connection lifetime.

Không nên giữ một transaction duy nhất cho hàng triệu item chỉ để có snapshot mà chưa tính đến lock lâu, transaction log, undo/MVCC retention, timeout và khả năng restart.

## 16. Repeatable read và các quy tắc nghiệp vụ nhiều row

Một transaction có thể đọc hai row ổn định nhưng vẫn gặp anomaly ở cấp tập dữ liệu hoặc quy tắc nhiều row tùy database isolation.

Ví dụ quy tắc: một phòng ban phải luôn có ít nhất một nhân viên trực. Hai transaction đồng thời đọc thấy hai nhân viên A và B, rồi mỗi transaction vô hiệu hóa một người khác nhau. Cả hai đều có thể nghĩ rằng còn một người trực, nhưng kết quả cuối cùng không còn ai.

Đây là dạng write skew có thể xảy ra dưới snapshot isolation. Repeatable reads cho từng row không nhất thiết bảo vệ bất biến trên toàn tập dữ liệu.

Các cách bảo vệ:

- Dùng constraint hoặc mô hình dữ liệu khiến database tự bảo vệ bất biến.
- Khóa một row đại diện/parent row để tuần tự hóa thao tác liên quan.
- Dùng `SERIALIZABLE` nếu cần database phát hiện và ngăn anomaly.
- Dùng optimistic locking/version và xử lý conflict.
- Thiết kế thao tác cập nhật theo atomic SQL statement thay vì read-then-write nhiều bước.

Chọn giải pháp theo bất biến nghiệp vụ. Nâng isolation toàn Step có thể đắt hơn một constraint hoặc lock có phạm vi hẹp.

## 17. Pessimistic locking và SELECT FOR UPDATE

Isolation level không phải cơ chế duy nhất để điều phối truy cập đồng thời. Pessimistic locking khóa row hoặc phạm vi dữ liệu trong khi transaction xử lý.

Ví dụ SQL:

```sql
SELECT order_id, status
FROM orders
WHERE order_id = ?
FOR UPDATE;
```

`FOR UPDATE` là cú pháp phổ biến nhưng chi tiết khác nhau theo database. Nó yêu cầu database khóa row phù hợp để transaction khác không thể cập nhật/xóa row đó theo cách xung đột cho đến khi transaction kết thúc.

Trong Spring Batch, có thể dùng locking query khi mỗi chunk cần claim một tập row. Cần cân nhắc:

- Lock được giữ đến khi chunk commit/rollback.
- Chunk lớn có thể giữ nhiều lock lâu hơn.
- Thứ tự lấy lock không nhất quán có thể gây deadlock.
- Nhiều worker cần một chiến lược claim rõ ràng.
- `SKIP LOCKED` hoặc cú pháp tương đương phụ thuộc database.

Không khóa toàn bộ bảng chỉ vì cần tránh non-repeatable read. Chọn đúng row/range và transaction boundary để giảm contention.

## 18. Optimistic locking và version column

Optimistic locking cho phép nhiều transaction đọc cùng dữ liệu nhưng phát hiện xung đột khi cập nhật. Một cột version tăng sau mỗi lần update:

```sql
UPDATE account
SET balance = ?, version = version + 1
WHERE account_id = ?
  AND version = ?;
```

Nếu số row được update bằng 0, version đã thay đổi bởi transaction khác. Ứng dụng biết dữ liệu đã bị cập nhật kể từ lúc đọc và có thể retry/reload hoặc báo conflict.

Optimistic locking phù hợp khi xung đột không thường xuyên và không muốn giữ lock lâu. Trong batch, có thể dùng version column để tránh ghi đè thay đổi mới của ứng dụng online.

Repeatable read và optimistic locking giải quyết các khía cạnh khác nhau: isolation kiểm soát snapshot/visibility trong transaction; version kiểm tra liệu row có bị thay đổi kể từ khi ứng dụng đọc hay không.

## 19. Read-only transaction và isolation

Một số reader hoặc service chỉ đọc dữ liệu. Có thể đánh dấu transaction read-only để database/driver tối ưu hoặc từ chối một số thao tác ghi tùy hệ thống:

```java
DefaultTransactionAttribute attribute = new DefaultTransactionAttribute();
attribute.setReadOnly(true);
attribute.setIsolationLevel(TransactionDefinition.ISOLATION_REPEATABLE_READ);
```

Tuy nhiên, chunk Step thường vừa đọc vừa ghi. Đánh dấu toàn chunk read-only trong khi writer cần cập nhật database là không phù hợp. Nếu có Step chỉ đọc để export, read-only có thể hữu ích nếu transaction manager/database hỗ trợ.

Read-only không phải isolation level và không tự tạo snapshot nhất quán. Nó là một thuộc tính transaction khác, có ý nghĩa tùy transaction manager/database.

## 20. Lock duration, chunk size và throughput

Isolation cao hơn có thể tăng thời gian giữ lock, số lock, khả năng conflict hoặc thời gian giữ snapshot. Chunk size cũng ảnh hưởng số lượng item được xử lý trong mỗi transaction.

| Chunk size | Tác động thường gặp |
|---|---|
| Nhỏ | Transaction ngắn hơn, commit thường xuyên hơn, overhead commit tăng |
| Lớn | Ít commit hơn, transaction dài hơn, có thể giữ lock/snapshot lâu và rollback nhiều item hơn |

Không có chunk size tối ưu chung. Khi dùng `REPEATABLE_READ`, hãy đo:

- Thời gian mỗi chunk transaction.
- Số lock và thời gian chờ lock.
- Deadlock/serialization failure.
- Connection pool usage.
- Transaction log/MVCC version retention.
- Throughput và số lần retry.
- Kích thước dữ liệu phải replay sau rollback.

Nếu isolation cao khiến nhiều transaction chờ nhau, có thể giảm chunk size, giảm thời gian processor, tối ưu index/query hoặc chia dữ liệu thành partition độc lập. Đừng hạ isolation nếu điều đó phá vỡ bất biến nghiệp vụ.

## 21. Deadlock và serialization failure

Khi nhiều transaction giữ lock hoặc database phát hiện xung đột serialization, một transaction có thể bị chọn làm deadlock victim hoặc bị abort. Spring có thể chuyển lỗi database thành `DeadlockLoserDataAccessException`, `CannotSerializeTransactionException` hoặc các exception liên quan tùy driver/translator/version.

Với batch, retry có thể phù hợp nếu transaction có thể thực thi lại an toàn:

```java
return new StepBuilder("updateAccountsStep", jobRepository)
        .<AccountChange, AccountChange>chunk(100, transactionManager)
        .reader(accountChangeReader)
        .writer(accountChangeWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

Tên exception chính xác tùy Spring version và exception translation. Có thể cần cấu hình retry cho root cause tương ứng với database.

Retry phải ở transaction boundary phù hợp để toàn chunk được thực hiện lại, không chỉ lặp một câu lệnh giữa chừng sau khi một phần side effect đã xảy ra. Writer cần idempotent hoặc tham gia transaction rollback đầy đủ.

Giảm deadlock bằng cách cập nhật row theo cùng thứ tự, dùng index phù hợp, giữ transaction ngắn và tránh gọi API bên ngoài khi đang giữ database lock.

## 22. Isolation và restart của Spring Batch

Restart tạo transaction mới. `REPEATABLE_READ` của transaction trước không còn hiệu lực sau khi transaction kết thúc hoặc process dừng. Khi restart, database tạo snapshot/lock context mới theo transaction mới.

Ví dụ:

1. Chunk 1 đọc dữ liệu trong snapshot A và commit.
2. Chunk 2 thất bại, Job dừng.
3. Ứng dụng khác cập nhật bảng nguồn.
4. Job restart, chunk transaction mới có snapshot B.

Reader có thể tiếp tục từ checkpoint item count, nhưng dữ liệu query phía sau có thể đã thay đổi. Isolation level không tự bảo đảm Job restart nhìn thấy cùng snapshot như lần chạy trước.

Muốn restart có thể tái lập, cần cố định input set bằng batch ID, manifest, watermark, snapshot/version hoặc staging table. Với paging, dùng sort key ổn định và query theo ranh giới đã chốt. Với cursor, kiểm tra connection/snapshot lifetime của chính cursor.

## 23. Isolation và JobRepository

Spring Batch lưu JobExecution, StepExecution và ExecutionContext qua `JobRepository`. Transaction của chunk có thể cùng transaction với repository nếu cấu hình cùng DataSource/transaction manager theo kiến trúc phù hợp, hoặc có thể có transaction manager khác.

Điều này quan trọng vì dữ liệu nghiệp vụ và metadata checkpoint cần nhất quán. Nếu writer commit dữ liệu ở một database nhưng metadata repository commit ở một transaction độc lập, lỗi giữa hai commit có thể tạo trạng thái lệch cần được xử lý theo cấu hình repository.

Isolation của chunk transaction không tự áp dụng sang JobRepository nếu repository dùng DataSource/transaction manager khác. Cần hiểu rõ:

- DataSource dùng cho business data.
- DataSource dùng cho JobRepository.
- Transaction manager được truyền vào `chunk(...)`.
- Cấu hình transaction manager của repository.
- Cách metadata và business write phối hợp khi commit.

Không giả định tất cả resource đều nằm trong một transaction chỉ vì chúng được sử dụng trong cùng Step.

## 24. Khi nào nên chọn REPEATABLE_READ?

`REPEATABLE_READ` có thể phù hợp khi một chunk cần đọc lại cùng row nhiều lần và phải dùng cùng giá trị trong suốt transaction. Ví dụ:

- Processor đọc lại một row cấu hình hoặc giá trị tham chiếu trong cùng chunk transaction.
- Một quy trình reconciliation cần kiểm tra lại row trước khi cập nhật trong cùng transaction.
- Nhiều câu SELECT trong một transaction cần nhìn thấy cùng phiên bản của row đã đọc.
- Một quy tắc nghiệp vụ nhạy cảm với non-repeatable read nhưng không cần serializable cho toàn bộ tập dữ liệu.

Không nên chọn chỉ vì “an toàn hơn” mà không xác định anomaly cần ngăn. Nếu mỗi item chỉ đọc một lần và writer dùng optimistic locking/constraint, `READ_COMMITTED` có thể đã đủ. Nếu cần bất biến trên predicate hoặc nhiều row, có thể cần `SERIALIZABLE`, lock tường minh hoặc constraint.

## 25. Khi nào không nên dùng REPEATABLE_READ?

Hãy cân nhắc kỹ khi:

- Step có transaction dài hoặc chunk size quá lớn.
- Nhiều Job cập nhật cùng bảng và lock contention đã cao.
- Database giữ snapshot lâu làm tăng MVCC/undo retention.
- Reader dùng connection riêng nên isolation trên chunk không ảnh hưởng đến query đọc.
- Nguồn dữ liệu cần thay đổi theo từng chunk và việc nhìn thấy phiên bản mới là chủ đích.
- Yêu cầu nghiệp vụ thực ra cần snapshot toàn Job, điều mà chunk-level repeatable read không cung cấp.

Trong các trường hợp này, tối ưu query, chốt input bằng batch ID hoặc dùng staging/version có thể giải quyết đúng vấn đề hơn việc nâng isolation cho mọi chunk.

## 26. Ví dụ so sánh READ_COMMITTED và REPEATABLE_READ

Giả sử một processor đọc giá sản phẩm hai lần trong cùng một transaction để tính mức chiết khấu.

Với `READ_COMMITTED`:

```text
T1: SELECT price -> 100
T2: UPDATE price = 120; COMMIT
T1: SELECT price -> 120
```

Processor có thể dùng hai giá trị khác nhau trong cùng một lần xử lý.

Với `REPEATABLE_READ`:

```text
T1: SELECT price -> 100
T2: UPDATE price = 120; COMMIT hoặc chờ tùy DB
T1: SELECT price -> 100
T1: COMMIT
```

T1 tiếp tục dùng cùng phiên bản row đã đọc. Sau khi T1 commit, transaction mới có thể thấy giá 120.

Nếu processor chỉ đọc giá một lần rồi tính toán, isolation cao hơn có thể không tạo lợi ích đáng kể. Nếu writer cập nhật row, vẫn cần xác định chính sách xử lý khi giá đã đổi trước khi commit và có cần optimistic/pessimistic locking hay không.

## 27. Kiểm thử isolation với hai transaction đồng thời

Không nên chỉ unit test bằng mock để xác nhận `REPEATABLE_READ`. Cần integration test với database/driver tương tự production và hai connection độc lập.

Một test non-repeatable read có thể thực hiện:

1. Transaction A bắt đầu ở mức isolation cần kiểm tra.
2. A đọc một row và ghi nhận giá trị.
3. Transaction B cập nhật cùng row rồi commit.
4. A đọc lại cùng row.
5. So sánh kết quả với semantics mà database cam kết.

Để test phantom:

1. A chạy query theo predicate và đếm số row.
2. B insert một row mới thỏa predicate rồi commit.
3. A chạy lại query.
4. Quan sát số row theo isolation và database cụ thể.

Dùng `CountDownLatch`, barrier hoặc transaction test utilities để điều khiển thứ tự thay vì dùng `sleep()` tùy ý. Test cần bảo đảm mỗi transaction thật sự dùng connection riêng và không vô tình tham gia cùng một transaction thread-bound.

Ngoài ra, nên test Step integration:

- Xác nhận transaction attribute được áp dụng cho chunk.
- Xác nhận reader/writer tham gia đúng DataSource transaction.
- Xác nhận cursor reader có connection riêng hay shared connection.
- Xác nhận retry khi deadlock/serialization failure.
- Xác nhận restart tạo transaction/snapshot mới và nguồn input được cố định đúng.

## 28. Những nhầm lẫn thường gặp

**Cho rằng REPEATABLE_READ tạo snapshot cho toàn bộ Job.** Spring Batch thường mở transaction theo chunk; mỗi chunk có thể có snapshot khác nhau.

**Cho rằng REPEATABLE_READ luôn ngăn phantom trên mọi database.** Theo chuẩn SQL, phantom vẫn có thể xảy ra; database có thể cung cấp semantics mạnh hơn hoặc khác biệt.

**Cho rằng REPEATABLE_READ tương đương SERIALIZABLE.** Snapshot isolation có thể vẫn cho phép write skew hoặc serialization anomaly.

**Đặt @Transactional trên writer rồi nghĩ chunk isolation đã thay đổi.** Method thường tham gia transaction đã mở; isolation không thể nâng cấp giữa transaction.

**Cho rằng mọi reader JDBC dùng connection của chunk.** `JdbcCursorItemReader` mặc định thường dùng connection cursor riêng. Kiểm tra connection thực tế.

**Cho rằng isolation tự giải quyết lost update.** Cần xem câu lệnh update, version column, lock và constraint.

**Tăng isolation để chữa mọi race condition.** Có thể cần unique constraint, claim pattern, idempotency hoặc partition theo khóa thay vì isolation cao hơn.

**Bật SERIALIZABLE mà không chuẩn bị retry.** Database có thể abort transaction do serialization conflict; batch cần xử lý lỗi và retry có giới hạn.

## 29. Cách lựa chọn isolation cho Jdbc processing

Hãy bắt đầu từ anomaly cụ thể. Nếu chỉ cần ngăn dirty read, `READ_COMMITTED` thường là mức tối thiểu phù hợp. Nếu một transaction cần đọc lại cùng row với cùng giá trị, cân nhắc `REPEATABLE_READ`. Nếu quy tắc nghiệp vụ phụ thuộc vào predicate hoặc nhiều row và cần hành vi tương đương tuần tự, đánh giá `SERIALIZABLE`, locking hoặc constraint.

Trong Spring Batch, đặt isolation trên transaction attribute của chunk Step khi đó là transaction cần bảo vệ. Xác nhận reader/writer thực sự dùng connection thuộc transaction đó; đặc biệt chú ý `JdbcCursorItemReader` mặc định mở cursor connection riêng. Đừng nhầm transaction của một chunk với snapshot toàn Step hoặc toàn Job.

Khi cần nhất quán xuyên suốt nhiều chunk và restart, cố định tập dữ liệu bằng batch ID, watermark, manifest, version hoặc staging snapshot. Đo lock wait, deadlock, transaction duration, connection usage và throughput trên database thật. Isolation level là một phần của thiết kế consistency; nó cần phối hợp với transaction boundary, query, locking, versioning và khả năng restart của Job.
