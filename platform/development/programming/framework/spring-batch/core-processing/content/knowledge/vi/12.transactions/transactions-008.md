# Isolation level của batch transaction

Trong Spring Batch, một step thường đọc và ghi dữ liệu trong các transaction do Spring quản lý. Khi nhiều transaction cùng truy cập một database, **isolation level** quyết định mức độ một transaction nhìn thấy thay đổi của transaction khác. Chọn isolation level phù hợp giúp batch đọc dữ liệu nhất quán, tránh một số lỗi cạnh tranh và kiểm soát chi phí khóa hoặc chờ đợi.

Isolation level đặc biệt quan trọng với job xử lý dữ liệu lớn, job chạy đồng thời với ứng dụng online hoặc nhiều batch job cùng cập nhật một tập bảng. Tuy nhiên, không phải cứ chọn mức cao nhất là tốt nhất. Mức cô lập cao có thể làm tăng lock contention, giảm thông lượng hoặc khiến transaction bị hủy do xung đột. Cần cân bằng yêu cầu nhất quán nghiệp vụ với khả năng xử lý đồng thời của hệ thống.

## 1. Transaction và isolation level là gì?

Transaction là một đơn vị công việc được database quản lý. Trong một transaction, ứng dụng có thể đọc dữ liệu, thực hiện cập nhật rồi commit hoặc rollback. Isolation level mô tả mức độ transaction được cách ly khỏi các thay đổi đồng thời do transaction khác tạo ra.

Ví dụ, một batch job đọc các đơn hàng có trạng thái `READY`, tính toán tổng tiền rồi cập nhật chúng thành `PROCESSED`. Trong lúc batch chạy, một ứng dụng khác cũng có thể sửa trạng thái hoặc thêm đơn hàng mới. Nếu không hiểu isolation level và cách database thực thi truy vấn, batch có thể đọc dữ liệu đang thay đổi, đọc lại một giá trị khác ở lần truy vấn sau hoặc bỏ sót/bị lặp bản ghi khi phân trang.

Isolation level không phải là một tùy chọn chỉ dành riêng cho Spring Batch. Đây là khái niệm của transaction/database được Spring biểu diễn qua `TransactionDefinition` và `PlatformTransactionManager`.

## 2. Các hiện tượng đọc không nhất quán

Các mức isolation thường được giải thích qua ba hiện tượng chính: dirty read, non-repeatable read và phantom read.

### Dirty read

Dirty read xảy ra khi transaction A đọc một thay đổi mà transaction B chưa commit. Nếu B rollback, A đã đọc dữ liệu chưa bao giờ trở thành dữ liệu đã commit.

```text
Transaction A                 Transaction B
-------------                 -------------
                              UPDATE account
                              SET balance = 500
                              (chưa commit)
SELECT balance
-> đọc được 500
                              ROLLBACK

A đã đọc một giá trị không được commit.
```

### Non-repeatable read

Non-repeatable read xảy ra khi một transaction đọc cùng một hàng hai lần nhưng nhận giá trị khác nhau vì transaction khác đã commit cập nhật ở giữa hai lần đọc.

```text
Transaction A                 Transaction B
-------------                 -------------
SELECT balance
-> 1000
                              UPDATE account
                              SET balance = 800
                              COMMIT
SELECT balance
-> 800

Cùng một hàng cho kết quả khác trong một transaction.
```

### Phantom read

Phantom read xảy ra khi transaction chạy lại một truy vấn theo điều kiện và nhận thêm hoặc mất đi các hàng vì transaction khác đã commit thao tác insert, delete hoặc update làm thay đổi tập kết quả.

Ví dụ, transaction A chạy `SELECT * FROM orders WHERE status = 'READY'` và nhận 100 hàng. Transaction B thêm một đơn hàng mới với trạng thái `READY` rồi commit. Nếu A chạy lại cùng truy vấn và thấy 101 hàng, hàng mới xuất hiện là một phantom row.

Ba hiện tượng trên là mô hình giúp hiểu isolation. Cách database cụ thể thực hiện có thể dựa trên lock, MVCC, snapshot hoặc kết hợp nhiều cơ chế. Vì vậy, hành vi thực tế còn phụ thuộc hệ quản trị cơ sở dữ liệu và loại truy vấn.

## 3. Các isolation level trong Spring

Spring biểu diễn isolation level bằng các hằng số trong `TransactionDefinition`:

| Spring constant | Mức isolation | Đặc điểm khái quát |
|---|---|---|
| `ISOLATION_DEFAULT` | Mặc định của database | Để database quyết định mức isolation mặc định cho connection/transaction. |
| `ISOLATION_READ_UNCOMMITTED` | Read Uncommitted | Có thể cho phép dirty read; mức cô lập thấp nhất. |
| `ISOLATION_READ_COMMITTED` | Read Committed | Chỉ đọc dữ liệu đã commit; cùng một hàng có thể thay đổi giữa hai lần đọc. |
| `ISOLATION_REPEATABLE_READ` | Repeatable Read | Bảo vệ tính lặp lại của việc đọc hàng theo semantics của database; phantom và snapshot behavior phụ thuộc hệ quản trị. |
| `ISOLATION_SERIALIZABLE` | Serializable | Mức cô lập cao nhất theo mô hình SQL; transaction có hành vi tương đương một thứ tự tuần tự, có thể phải chờ hoặc bị hủy do xung đột. |

`ISOLATION_DEFAULT` thường là lựa chọn mặc định trong Spring. Nó không có nghĩa là một mức isolation cố định; nó yêu cầu transaction manager/database dùng cấu hình mặc định của datasource.

### READ_UNCOMMITTED

Read Uncommitted cho phép transaction có thể nhìn thấy dữ liệu chưa commit của transaction khác. Điều này có nguy cơ dirty read. Một số database không thực sự hỗ trợ mức này và nâng hành vi lên mức cao hơn.

Với batch nghiệp vụ, mức này hiếm khi phù hợp vì job có thể tính toán trên dữ liệu sau đó bị rollback. Chỉ cân nhắc khi chấp nhận dữ liệu gần đúng và đã hiểu rõ semantics của database.

### READ_COMMITTED

Read Committed bảo đảm truy vấn chỉ nhìn thấy dữ liệu đã commit. Tuy nhiên, nếu cùng một transaction đọc lại một hàng sau khi transaction khác commit cập nhật, lần đọc sau có thể thấy giá trị mới. Tập hàng thỏa điều kiện truy vấn cũng có thể thay đổi.

Đây là mức phổ biến trong nhiều hệ thống quan hệ. Nó thường cân bằng giữa tính nhất quán và khả năng đồng thời, nhưng batch cần có chiến lược nếu tập dữ liệu thay đổi trong lúc xử lý.

### REPEATABLE_READ

Repeatable Read nhằm bảo đảm việc đọc lại cùng hàng trong một transaction không cho giá trị thay đổi theo semantics của database. Mức này thường hạn chế non-repeatable read. Cách xử lý phantom read khác nhau giữa các hệ quản trị và implementation.

Một số database dùng MVCC để cung cấp snapshot nhất quán; database khác có thể dùng lock hoặc range lock. Vì thế, không nên suy luận chỉ từ tên mức isolation rằng mọi truy vấn phân trang hoặc mọi phantom đều được xử lý giống nhau ở mọi database.

### SERIALIZABLE

Serializable là mức cô lập cao nhất theo mô hình SQL. Database cố gắng bảo đảm kết quả tương đương với việc các transaction chạy tuần tự. Để đạt điều đó, database có thể giữ lock lâu hơn, chặn transaction khác hoặc phát hiện xung đột và hủy một transaction.

Với batch, Serializable có thể hữu ích khi một đơn vị nghiệp vụ cần đọc và cập nhật một tập dữ liệu với yêu cầu nhất quán nghiêm ngặt. Nhưng transaction kéo dài ở mức này có thể gây giảm thông lượng, lock contention hoặc serialization failure. Ứng dụng cần có cách xử lý retry phù hợp.

## 4. So sánh các mức isolation

Bảng dưới đây mô tả mô hình SQL phổ biến. Cần kiểm tra tài liệu của database đang dùng vì một số hệ quản trị triển khai MVCC hoặc locking theo cách riêng.

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---:|---:|---:|
| Read Uncommitted | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra |
| Read Committed | Không | Có thể xảy ra | Có thể xảy ra |
| Repeatable Read | Không | Không theo semantics chuẩn | Có thể xảy ra theo SQL chuẩn; database có thể mạnh hơn |
| Serializable | Không | Không | Không theo mô hình tuần tự hóa |

Mức isolation cao hơn thường đặt ra nhiều ràng buộc hơn đối với các transaction đồng thời. Tuy nhiên, không nên chỉ dùng bảng này để dự đoán hiệu năng. Ví dụ, database dùng MVCC có thể cho phép reader tiếp tục đọc snapshot mà không chặn writer, trong khi một truy vấn locking có thể chặn transaction khác.

## 5. Transaction boundary trong Spring Batch

Trong chunk-oriented step, Spring Batch thường tạo một transaction cho mỗi chunk. Reader lấy item, processor xử lý, writer ghi kết quả; sau khi writer hoàn tất, framework commit transaction. Nếu lỗi xảy ra trước commit, transaction có thể rollback theo cấu hình.

```text
Chunk 1
  BEGIN TRANSACTION
    read item 1 ... N
    process items
    write chunk
  COMMIT

Chunk 2
  BEGIN TRANSACTION
    read item N+1 ... 2N
    process items
    write chunk
  COMMIT

Chunk 3 ...
```

Isolation level được áp dụng cho transaction của từng chunk theo transaction manager và transaction attribute của step. Với chunk size lớn, mỗi transaction có thể kéo dài hơn vì cần đọc và ghi nhiều item trước khi commit. Điều này ảnh hưởng thời gian giữ lock, mức độ cạnh tranh và lượng công việc phải rollback nếu lỗi.

Một job có nhiều step không mặc định chạy trong một transaction duy nhất từ đầu đến cuối. Các chunk hoặc lần gọi tasklet có transaction riêng theo cấu hình. Khi một step sau thất bại, các chunk đã commit của step trước không tự động rollback.

## 6. Cấu hình isolation cho chunk-oriented step

Trong Spring Batch 5 trở lên, có thể cấu hình transaction attribute của step bằng `DefaultTransactionAttribute`. Ví dụ sau chọn Read Committed cho transaction của chunk:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .transactionAttribute(transactionAttribute)
            .build();
}
```

Trong ví dụ:

- `chunk(500, transactionManager)` chọn kích thước chunk và transaction manager.
- `setIsolationLevel(...)` đặt isolation level cho transaction của step.
- `setTimeout(120)` đặt timeout transaction theo đơn vị giây, nếu transaction manager hỗ trợ.
- `transactionAttribute(...)` gắn thuộc tính transaction vào step.

Nếu không cấu hình riêng, step thường sử dụng isolation mặc định do transaction manager/database cung cấp. Không nên thay đổi isolation chỉ vì một job chạy chậm; trước tiên cần xác định vấn đề là lock contention, truy vấn chậm, chunk quá lớn hay dữ liệu cạnh tranh.

## 7. Cấu hình isolation cho Tasklet step

Tasklet step cũng sử dụng transaction manager. Có thể áp dụng transaction attribute tương tự:

```java
@Bean
Step reconcileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
            TransactionDefinition.ISOLATION_REPEATABLE_READ);

    Tasklet reconcileTasklet = (contribution, chunkContext) -> {
        // Đọc dữ liệu và thực hiện một tác vụ đối soát.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("reconcileStep", jobRepository)
            .tasklet(reconcileTasklet, transactionManager)
            .transactionAttribute(transactionAttribute)
            .build();
}
```

Với tasklet trả `RepeatStatus.CONTINUABLE`, framework có thể gọi lại tasklet nhiều lần. Transaction được quản lý theo lần gọi và cấu hình step. Nếu tác vụ cần đọc một tập dữ liệu ổn định qua nhiều lần gọi, cần thiết kế rõ ranh giới transaction và snapshot; không nên giả định mọi lần gọi tasklet nằm trong cùng một transaction dài.

## 8. Phân biệt isolation của step transaction và JobRepository

Đây là điểm dễ nhầm trong Spring Batch. `JobRepository` cũng sử dụng transaction để lưu metadata như JobInstance, JobExecution và StepExecution. Khi repository tạo metadata cho một execution mới, Spring Batch có cấu hình isolation riêng cho thao tác tạo.

Trong cấu hình repository truyền thống, `isolationLevelForCreate` thường mặc định là `ISOLATION_SERIALIZABLE`. Mục đích là giảm nguy cơ hai yêu cầu đồng thời cùng tạo metadata cho một JobInstance khi cùng job và identifying parameters được khởi chạy gần như cùng lúc.

Isolation này **khác với isolation của transaction xử lý dữ liệu nghiệp vụ trong step**:

| Cấu hình | Phạm vi | Mục đích |
|---|---|---|
| Isolation của step transaction | Transaction đọc/ghi dữ liệu trong chunk hoặc tasklet | Kiểm soát tính nhất quán khi xử lý dữ liệu nghiệp vụ. |
| `isolationLevelForCreate` của JobRepository | Transaction tạo metadata thực thi | Bảo vệ việc đăng ký JobInstance/JobExecution khi có yêu cầu khởi chạy đồng thời. |

Với cấu hình Spring Batch dùng `@EnableBatchProcessing`, thuộc tính `isolationLevelForCreate` điều khiển isolation cho thao tác tạo của repository theo phiên bản hỗ trợ. Ví dụ:

```java
@Configuration
@EnableBatchProcessing(
        isolationLevelForCreate = "ISOLATION_SERIALIZABLE")
public class BatchInfrastructureConfiguration {
}
```

Không nên thay đổi `isolationLevelForCreate` để điều chỉnh transaction của chunk. Ngược lại, thay isolation của step cũng không thay đổi cơ chế bảo vệ việc tạo metadata của JobRepository. Trong ứng dụng Spring Boot, hạ tầng Batch có thể được auto-configure; hãy xem cách cấu hình repository thực tế của ứng dụng trước khi tùy chỉnh.

## 9. Isolation level và reader database

Isolation level ảnh hưởng đến cách reader nhìn thấy dữ liệu khi các transaction khác đồng thời thay đổi database.

### Cursor reader

`JdbcCursorItemReader` thường mở một cursor/ResultSet và đọc tuần tự. Tùy database và driver, cursor có thể nhìn thấy snapshot tại thời điểm mở, dữ liệu theo transaction hoặc semantics riêng. Transaction và isolation level có thể ảnh hưởng thời gian giữ snapshot, lock và khả năng nhìn thấy thay đổi mới.

Với job chạy lâu, cursor có thể giữ connection trong thời gian dài. Cần cân nhắc pool, transaction timeout, isolation và tài nguyên database. Không nên giả định cursor luôn nhìn thấy cùng một tập dữ liệu trên mọi hệ quản trị.

### Paging reader

`JdbcPagingItemReader` thực hiện nhiều truy vấn để lấy các trang. Nếu mỗi trang được đọc trong một transaction khác nhau hoặc snapshot không được giữ xuyên suốt, dữ liệu thay đổi trong lúc job chạy có thể làm dịch chuyển ranh giới trang.

Ví dụ, reader đọc trang đầu gồm ID 1-100. Trong lúc đó, một transaction khác chèn bản ghi mới có ID nằm trước ranh giới trang. Truy vấn trang tiếp theo có thể trả về một tập khác so với khi không có insert. Tùy chiến lược phân trang và sort key, có thể xảy ra lặp hoặc bỏ sót hàng.

Để giảm rủi ro:

- Dùng `ORDER BY` với sort key ổn định, tốt nhất là khóa duy nhất.
- Chốt tập dữ liệu bằng batch ID, watermark hoặc mốc thời gian.
- Tránh cập nhật các cột dùng trong điều kiện lọc hoặc sort key trong lúc đang phân trang.
- Cân nhắc snapshot transaction nếu database và yêu cầu vận hành hỗ trợ.
- Với tập dữ liệu biến động, cân nhắc keyset pagination hoặc chiến lược claim dữ liệu thay vì offset paging.

Chọn Repeatable Read hoặc Serializable không tự động giải quyết mọi vấn đề phân trang nếu các trang nằm trong những transaction khác nhau. Cần xác định transaction boundary thực tế của reader và step.

## 10. Isolation level không thay thế khóa nghiệp vụ

Giả sử hai batch job cùng truy vấn các đơn hàng `READY`. Cả hai có thể đọc cùng một đơn hàng trước khi một job cập nhật trạng thái. Nếu mỗi job xử lý trong các transaction riêng với Read Committed, cả hai có thể cùng tính toán và thực hiện tác dụng phụ cho một đơn hàng.

Tăng isolation level có thể giảm một số kiểu xung đột, nhưng không phải giải pháp duy nhất hoặc luôn phù hợp. Các cách thiết kế thường dùng gồm:

- Cập nhật trạng thái theo điều kiện nguyên tử, ví dụ `UPDATE ... WHERE status = 'READY'` và kiểm tra số hàng được cập nhật.
- Dùng cột version và optimistic locking để phát hiện cập nhật cạnh tranh.
- Claim một tập bản ghi bằng trạng thái hoặc batch ID trước khi xử lý.
- Dùng khóa database hoặc `SELECT ... FOR UPDATE` khi phù hợp với database và transaction boundary.
- Dùng cơ chế như `SKIP LOCKED` nếu hệ quản trị hỗ trợ và nghiệp vụ chấp nhận bỏ qua hàng đang bị khóa để worker khác xử lý.
- Chia phạm vi dữ liệu rõ ràng giữa các partition/job để tránh hai worker nhận cùng item.
- Bảo vệ kết quả bằng unique constraint và thao tác writer idempotent.

Isolation quản lý cách transaction nhìn thấy và tương tác với thay đổi đồng thời. Khóa nghiệp vụ xác định ai được quyền xử lý một đơn vị dữ liệu. Hai cơ chế thường cần phối hợp.

## 11. Isolation level, deadlock và lock contention

Isolation càng cao thường có thể làm tăng thời gian chờ hoặc số lượng lock tùy database. Với batch, chunk size lớn và transaction dài có thể khiến lock được giữ lâu, làm các request online hoặc batch khác phải chờ.

Deadlock xảy ra khi hai hoặc nhiều transaction giữ tài nguyên mà transaction còn lại cần, tạo thành vòng chờ. Ví dụ:

```text
Transaction A giữ lock trên Order 1
Transaction B giữ lock trên Order 2

A cần Order 2  ---- chờ B
B cần Order 1  ---- chờ A

Database phát hiện deadlock và hủy một transaction.
```

Một số cách giảm nguy cơ:

- Cập nhật các bảng/hàng theo thứ tự nhất quán trong mọi transaction.
- Giữ transaction ngắn bằng cách chọn chunk size phù hợp.
- Tạo index cho điều kiện lọc và join để giảm thời gian quét/giữ lock.
- Tránh gọi API hoặc thực hiện công việc chậm trong khi transaction database đang mở.
- Phân chia phạm vi xử lý giữa các job hoặc partition.
- Thiết kế retry có giới hạn cho lỗi deadlock/serialization transient.

Không nên tăng isolation lên Serializable chỉ để tránh deadlock. Mức này có thể làm xung đột nghiêm trọng hơn nếu transaction dài hoặc nhiều job cùng truy cập một tập dữ liệu.

## 12. Isolation level và retry khi transaction bị hủy

Ở một số database, transaction chạy với Serializable hoặc snapshot-based isolation có thể bị hủy khi phát hiện xung đột. Ứng dụng cần phân biệt lỗi có thể retry với lỗi dữ liệu hoặc lỗi nghiệp vụ không thể tự khắc phục.

Ví dụ, có thể cấu hình retry cho một loại exception transient do database/driver phát ra:

```java
return new StepBuilder("updateBalancesStep", jobRepository)
        .<BalanceInput, BalanceUpdate>chunk(200, transactionManager)
        .reader(balanceReader)
        .processor(balanceProcessor)
        .writer(balanceWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Ví dụ này chỉ minh họa chính sách retry tổng quát. Cần xác định exception thực tế được database driver và Spring dịch ra, vì serialization failure hoặc deadlock có thể được ánh xạ thành các loại exception khác nhau tùy nền tảng.

Retry phải có giới hạn, backoff phù hợp và logic ghi có khả năng chạy lại an toàn. Nếu writer gửi yêu cầu sang hệ thống ngoài hoặc cập nhật tài nguyên không tham gia transaction, rollback database không tự hoàn tác tác dụng phụ đó.

## 13. Chọn isolation level theo nhu cầu nghiệp vụ

Không có một mức isolation tối ưu cho mọi batch job. Có thể dùng các nguyên tắc sau để bắt đầu lựa chọn:

| Loại công việc | Mức có thể cân nhắc | Điều cần xác nhận |
|---|---|---|
| Import dữ liệu độc lập, không cần đọc lại cùng hàng trong một transaction | `READ_COMMITTED` hoặc `DEFAULT` | Dữ liệu nguồn có thay đổi trong lúc job chạy không? |
| Đối soát cần đọc lặp cùng hàng trong một transaction | `REPEATABLE_READ` hoặc snapshot phù hợp | Database bảo đảm snapshot như thế nào và transaction kéo dài bao lâu? |
| Cập nhật tập dữ liệu có yêu cầu tuần tự hóa nghiêm ngặt | `SERIALIZABLE` hoặc cơ chế khóa/claim cụ thể | Có thể chấp nhận blocking, retry và serialization failure không? |
| Báo cáo cần snapshot nhất quán | Snapshot isolation hoặc transaction phù hợp với database | Có thể giữ snapshot trong toàn bộ phạm vi truy vấn không? |
| Batch chạy song song với hệ thống online | Thường bắt đầu từ `DEFAULT`/`READ_COMMITTED` rồi điều chỉnh | Lock contention, thời gian transaction và xung đột cập nhật ra sao? |

Đối với nhiều job, cách hiệu quả hơn có thể là xác định một tập dữ liệu cố định bằng watermark hoặc batch ID, sau đó xử lý từng chunk bằng Read Committed. Cách này tránh phải giữ một transaction Serializable rất dài trong toàn bộ thời gian batch.

## 14. Ví dụ: chốt tập dữ liệu bằng watermark

Giả sử batch cần xử lý tất cả đơn hàng được tạo trước thời điểm bắt đầu. Thay vì giữ một transaction dài để ngăn mọi insert mới, ứng dụng có thể xác định một watermark tại thời điểm bắt đầu job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("cutoffTime", "2026-11-15T00:00:00Z", true)
        .toJobParameters();
```

Reader dùng cùng cutoff cho tất cả truy vấn:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE created_at < :cutoffTime
ORDER BY order_id
```

Nếu điều kiện dữ liệu và thứ tự được giữ ổn định, các bản ghi mới tạo sau cutoff không đi vào tập xử lý của batch hiện tại. Batch kế tiếp có thể dùng cutoff mới.

Watermark không tự giải quyết trường hợp một bản ghi cũ bị cập nhật hoặc xóa trong lúc job chạy. Nếu cần snapshot hoàn chỉnh, phải chọn cơ chế snapshot/transaction phù hợp với database hoặc sao chép dữ liệu đầu vào sang một tập bất biến trước khi xử lý.

## 15. `@Transactional` trong service được gọi từ processor hoặc writer

Một service được gọi từ processor/writer có thể được đánh dấu `@Transactional`. Tuy nhiên, nếu service tham gia transaction đang mở của chunk với propagation mặc định `REQUIRED`, nó thường dùng chung transaction đó. Khai báo isolation khác trên method tham gia transaction hiện tại không tự tạo một transaction mới với isolation mới.

Ví dụ:

```java
@Service
public class OrderLookupService {

    @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE)
    public OrderEntity findOrder(String orderId) {
        // Truy vấn trong transaction hiện tại nếu đã có.
        return repository.findById(orderId).orElseThrow();
    }
}
```

Nếu method được gọi khi chunk transaction đã tồn tại, propagation `REQUIRED` thường tham gia transaction hiện tại. Isolation của transaction đang tồn tại sẽ có hiệu lực; annotation trên method không tự nâng isolation của transaction đó. Một số transaction manager có thể được cấu hình để validate việc tham gia transaction với isolation không tương thích, nhưng không nên dựa vào annotation trên service như cách thay isolation của step.

Nếu thực sự cần transaction độc lập, `REQUIRES_NEW` có thể tạo transaction riêng khi transaction manager hỗ trợ. Tuy nhiên, nó làm thay đổi ranh giới commit: transaction con có thể commit ngay cả khi chunk bên ngoài rollback. Chỉ sử dụng khi nghiệp vụ yêu cầu rõ ràng và đã đánh giá tác động đến restart, idempotency và tính nhất quán.

Thông thường, cấu hình isolation tại step transaction là nơi dễ hiểu hơn cho toàn bộ thao tác read/process/write của chunk.

## 16. Những yếu tố khác ảnh hưởng đến tính nhất quán

Isolation level chỉ là một phần của thiết kế transaction. Một batch job còn chịu ảnh hưởng bởi:

- **Transaction manager:** phải quản lý đúng datasource hoặc tài nguyên mà reader/writer sử dụng.
- **Transaction propagation:** service tham gia transaction hiện tại hay tạo transaction mới.
- **Transaction timeout:** transaction quá lâu có thể bị hủy hoặc giữ tài nguyên quá lâu.
- **Locking strategy:** pessimistic lock, optimistic lock, version column hoặc claim dữ liệu.
- **Chunk size:** ảnh hưởng thời gian transaction và lượng dữ liệu rollback.
- **Query plan và index:** truy vấn chậm làm transaction tồn tại lâu hơn.
- **MVCC/snapshot implementation:** quyết định cách database cung cấp dữ liệu nhất quán.
- **Nguồn dữ liệu ngoài database:** file, API và message broker không tự tham gia transaction JDBC.
- **Restart và idempotency:** item hoặc thao tác ngoài transaction có thể được thực hiện lại.

Vì vậy, khi có lỗi nhất quán dữ liệu, cần xem toàn bộ đường đi từ reader, transaction manager, processor, writer đến database thay vì chỉ thay một giá trị isolation.

## 17. Kiểm tra isolation level trong môi trường thực tế

Trước khi triển khai một mức isolation mới, nên xác nhận hành vi của database bằng thử nghiệm có kiểm soát:

1. Xác định database, phiên bản, JDBC driver và transaction manager đang dùng.
2. Kiểm tra isolation mặc định của database và connection pool.
3. Xác nhận step thực sự dùng transaction manager nào.
4. Tạo hai transaction đồng thời để kiểm tra dirty read, non-repeatable read hoặc phantom theo trường hợp nghiệp vụ.
5. Đo thời gian chờ lock, deadlock, serialization failure và thông lượng batch.
6. Thử với chunk size và tập dữ liệu gần với production.
7. Kiểm tra restart sau khi transaction rollback hoặc bị database hủy.
8. Xác nhận writer không tạo dữ liệu trùng khi item được xử lý lại.

Theo dõi thêm thời gian mỗi chunk, số lần retry, số lỗi skip, thời gian chờ connection, lock wait và thời gian commit. Các chỉ số này giúp xác định liệu vấn đề đến từ isolation, query, chunk size hay cạnh tranh tài nguyên.

## 18. Các lỗi thường gặp khi cấu hình isolation cho batch

| Vấn đề | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| Nghĩ Serializable luôn tốt nhất | Bỏ qua chi phí lock, blocking và serialization failure. | Chọn mức theo yêu cầu nhất quán và đo tải thực tế. |
| Thay isolation của JobRepository nhưng chunk không đổi | Nhầm `isolationLevelForCreate` với transaction của step. | Cấu hình transaction attribute của step cho business transaction. |
| Thêm `@Transactional(isolation=...)` vào service nhưng không có hiệu lực | Method tham gia transaction chunk hiện tại với `REQUIRED`. | Cấu hình tại step hoặc thiết kế transaction mới khi thật sự cần. |
| Paging bị lặp hoặc bỏ sót hàng | Sort key không ổn định hoặc dữ liệu nguồn thay đổi giữa các trang. | Dùng sort key duy nhất, watermark hoặc snapshot. |
| Batch giữ lock quá lâu | Chunk quá lớn, transaction chậm hoặc truy vấn thiếu index. | Giảm thời gian transaction, tối ưu query và đo lại chunk size. |
| Deadlock khi nhiều job chạy cùng lúc | Các transaction cập nhật hàng theo thứ tự khác nhau hoặc cạnh tranh cùng dữ liệu. | Chuẩn hóa thứ tự cập nhật, phân vùng dữ liệu và retry lỗi transient. |
| Retry gây ghi trùng | Tác dụng phụ không tham gia transaction hoặc writer không idempotent. | Dùng khóa nghiệp vụ, idempotency key, outbox hoặc đối soát. |
| Đọc dữ liệu thay đổi giữa các chunk | Mỗi chunk là transaction riêng, không có snapshot xuyên suốt job. | Chốt tập dữ liệu bằng watermark hoặc dùng snapshot phù hợp. |

## 19. Những điểm cần ghi nhớ

- Isolation level quyết định mức độ transaction nhìn thấy thay đổi từ transaction đồng thời.
- Dirty read, non-repeatable read và phantom read là ba hiện tượng cần hiểu khi chọn mức cô lập.
- Spring cung cấp `ISOLATION_DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` qua `TransactionDefinition`.
- Chunk-oriented step thường có transaction riêng cho mỗi chunk; không mặc định toàn job nằm trong một transaction.
- Có thể cấu hình isolation cho step bằng `DefaultTransactionAttribute` và `.transactionAttribute(...)`.
- Isolation của step transaction khác với `isolationLevelForCreate` dùng cho transaction tạo metadata của JobRepository.
- Cursor và paging reader có hành vi nhất quán khác nhau; paging cần sort key ổn định và tập dữ liệu được xác định rõ.
- Isolation không thay thế khóa nghiệp vụ, claim dữ liệu, unique constraint hoặc idempotency.
- Mức isolation cao có thể tăng lock contention, blocking hoặc serialization failure; cần retry có giới hạn nếu phù hợp.
- `@Transactional` trên service tham gia transaction hiện tại không tự nâng isolation của chunk transaction.
- Chọn isolation theo database, yêu cầu nghiệp vụ, transaction boundary và số lượng job chạy đồng thời; kiểm chứng bằng thử nghiệm thực tế.

Khi thiết kế batch transaction, hãy bắt đầu từ yêu cầu nhất quán của dữ liệu: job cần đọc snapshot ổn định hay chỉ cần đọc dữ liệu đã commit, các job có thể cập nhật cùng bản ghi hay không, và transaction kéo dài bao lâu. Sau đó chọn isolation level, chunk size và chiến lược khóa phù hợp. Cách tiếp cận này giúp batch xử lý dữ liệu an toàn mà vẫn duy trì thông lượng cho các ứng dụng chạy đồng thời.
