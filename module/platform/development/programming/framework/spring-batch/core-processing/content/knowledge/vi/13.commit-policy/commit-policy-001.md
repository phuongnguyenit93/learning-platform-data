# Commit interval và số item mỗi transaction

Trong Spring Batch, `commit-interval` xác định số item mà một chunk hướng tới xử lý trước khi transaction của chunk được commit. Với chunk-oriented Step, Spring Batch đọc item, chuyển qua processor, gọi writer và cập nhật trạng thái stream trong cùng ranh giới xử lý của chunk. Khi chunk hoàn tất thành công, transaction được commit; nếu có lỗi làm chunk thất bại, transaction hiện tại có thể rollback.

Ví dụ, `commit-interval = 100` nghĩa là Step gom tối đa khoảng 100 item đầu vào cho một chunk trước khi commit. Nếu nguồn có 250 item, về mặt dữ liệu sẽ có hai chunk đủ 100 và một chunk cuối gồm 50 item. Vì vậy, commit interval là kích thước mục tiêu của chunk và quyết định tần suất commit, không phải cam kết rằng writer luôn ghi chính xác từng ấy item.

## 1. Chunk và transaction trong Spring Batch

Chunk-oriented processing chia một lượng dữ liệu lớn thành những nhóm nhỏ. Mỗi nhóm được đọc, xử lý, ghi và commit như một đơn vị transaction.

```text
ItemReader
    |
    v
Đọc item cho đến khi đủ commit interval hoặc hết dữ liệu
    |
    v
ItemProcessor (cho từng item)
    |
    v
ItemWriter (ghi kết quả của chunk)
    |
    v
Cập nhật trạng thái stream / ExecutionContext
    |
    v
Commit transaction của chunk
```

Spring Batch lặp chu trình trên cho đến khi reader báo hết dữ liệu hoặc Step kết thúc. Nếu chunk gặp exception, transaction manager xử lý rollback theo cấu hình. Các chunk đã commit trước đó vẫn là những transaction độc lập và không tự động bị rollback cùng chunk thất bại.

Commit interval thường được cấu hình bằng `chunk(size, transactionManager)`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Trong ví dụ này, `100` là commit interval. `PlatformTransactionManager` quản lý transaction của từng chunk theo cấu hình Step. Các thao tác ghi cần tham gia transaction này nếu muốn rollback của chunk hoàn tác chúng.

## 2. Số item trong một transaction được tính như thế nào?

Giả sử reader cung cấp 250 item và commit interval là 100. Về mặt dữ liệu, Spring Batch xử lý thành ba chunk:

```text
Tổng số item đầu vào: 250
Commit interval:       100

Chunk 1: item   1 - 100  -> process -> write -> commit
Chunk 2: item 101 - 200  -> process -> write -> commit
Chunk 3: item 201 - 250  -> process -> write -> commit
```

| Chunk | Item đầu vào | Số item | Kết quả khi thành công |
|---|---|---:|---|
| 1 | 1–100 | 100 | Commit transaction 1 |
| 2 | 101–200 | 100 | Commit transaction 2 |
| 3 | 201–250 | 50 | Commit transaction 3 |
| Tổng | 1–250 | 250 | 3 nhóm dữ liệu |

Chunk cuối được phép có ít item hơn commit interval. Khi `ItemReader.read()` trả về `null`, Spring Batch hiểu rằng nguồn dữ liệu đã kết thúc và xử lý phần item còn lại như chunk cuối. Framework không bỏ 50 item chỉ vì chúng chưa đủ 100.

Với một nguồn dữ liệu có tổng số item là `N` và commit interval là `C`, số chunk dữ liệu theo cách chia thông thường là:

\[
\text{Số chunk dữ liệu} = \left\lceil \frac{N}{C} \right\rceil
\]

Ví dụ:

| Tổng item (N) | Commit interval (C) | Chunk dữ liệu |
|---:|---:|---|
| 240 | 100 | 100, 100, 40 |
| 300 | 100 | 100, 100, 100 |
| 75 | 100 | 75 |
| 1.050 | 250 | 250, 250, 250, 250, 50 |

Công thức trên mô tả các chunk chứa dữ liệu. Số liệu transaction/commit trong metadata thực tế còn phụ thuộc cách Step kết thúc, retry, skip, rollback và các callback lưu trạng thái; không nên chỉ lấy phép chia để suy ra mọi counter của `StepExecution`.

## 3. Commit interval không đồng nghĩa số item writer ghi

Commit interval chủ yếu xác định kích thước chunk đầu vào mà reader cung cấp. Số item được chuyển tới writer có thể ít hơn vì `ItemProcessor` có thể filter item bằng cách trả về `null`.

Ví dụ, chunk có 100 item đầu vào nhưng processor loại 8 item:

```text
Reader đọc:             100 item
Processor filter:         8 item
Kết quả chuyển đến writer: 92 item
Transaction chunk:         vẫn là chunk xử lý 100 item đầu vào
```

| Chỉ số | Số lượng |
|---|---:|
| Item reader cung cấp | 100 |
| Item bị filter | 8 |
| Item writer nhận | 92 |

Filter không giống skip. Filter là quyết định nghiệp vụ bình thường trong processor; skip xảy ra khi exception thuộc loại được cấu hình để bỏ qua. Retry có thể khiến một số thao tác được thực hiện lại, còn rollback có thể làm chunk hiện tại phải xử lý lại. Vì vậy, không thể kết luận commit interval thay đổi chỉ vì writer nhận ít item hơn.

## 4. Ranh giới transaction và rollback

Với commit interval 100, 100 item của chunk thường nằm trong cùng transaction. Nếu writer ghi 70 item rồi ném exception ở item tiếp theo, kết quả phụ thuộc vào resource writer sử dụng:

- Nếu cả 70 thao tác ghi tham gia transaction của Step, rollback có thể hoàn tác toàn bộ thay đổi chưa commit của chunk.
- Nếu writer commit riêng từng item, dùng transaction manager khác hoặc gọi hệ thống bên ngoài, các thay đổi đã thực hiện có thể vẫn tồn tại.
- Nếu writer bắt exception rồi trả về bình thường, framework có thể coi chunk thành công và commit, dù một phần item chưa được ghi.

Ví dụ, writer dùng `JdbcTemplate` với cùng `DataSource` được transaction manager quản lý:

```java
public class OrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id, amount) values (?, ?)",
                    order.getId(),
                    order.getAmount()
            );
        }
    }
}
```

Nếu insert thứ 71 thất bại và tất cả insert tham gia cùng transaction, các insert trước trong chunk cũng được rollback. Chunk 1 và chunk 2 đã commit trước đó vẫn giữ nguyên kết quả.

Transaction không tự động rollback side effect ở HTTP API, file, email hoặc message broker. Với các đích này, cần thiết kế idempotency, checkpoint, outbox hoặc cơ chế phục hồi riêng.

## 5. Commit interval ảnh hưởng đến checkpoint và restart

Reader và writer có thể triển khai `ItemStream` để lưu trạng thái vào `ExecutionContext`. Spring Batch cập nhật trạng thái stream tại ranh giới chunk và lưu metadata cùng quá trình xử lý transaction theo cấu hình repository.

Với commit interval 100:

1. Reader đọc chunk đầu tiên, processor và writer xử lý 100 item.
2. Chunk commit thành công; checkpoint tương ứng được lưu.
3. Chunk thứ hai xử lý và commit 100 item tiếp theo.
4. Chunk thứ ba gặp lỗi trước commit.
5. Khi restart, reader khôi phục checkpoint của chunk cuối cùng đã commit và tiếp tục phần chưa hoàn tất.

Do đó, commit interval ảnh hưởng đến khoảng cách giữa các checkpoint. Interval lớn có thể làm lượng dữ liệu cần xử lý lại sau sự cố lớn hơn. Interval nhỏ tạo checkpoint thường xuyên hơn nhưng làm tăng số lần commit và chi phí transaction.

Reader phải hỗ trợ restart và nguồn dữ liệu cần có thứ tự/định danh ổn định để checkpoint còn ý nghĩa. Chỉ đặt commit interval không tự làm một reader bất kỳ restartable.

## 6. Commit interval và các kích thước batch khác

Một số cấu hình khác cũng có giá trị số lượng item, nhưng chúng điều khiển các lớp khác nhau. Không nên đặt tất cả bằng cùng một con số chỉ vì tên đều có chữ “size”.

| Cấu hình | Điều khiển | Quan hệ với commit interval |
|---|---|---|
| Chunk size / commit interval | Số item trong một chunk trước khi commit | Quyết định ranh giới transaction của Step |
| Reader page size | Số bản ghi reader lấy trong một lần truy vấn trang | Có thể lớn hơn, nhỏ hơn hoặc bằng commit interval |
| JDBC fetch size | Gợi ý driver lấy dữ liệu theo đợt từ database | Chủ yếu ảnh hưởng cách dữ liệu được fetch, không trực tiếp quyết định commit |
| Writer batch size | Số câu lệnh/item writer gom cho một batch ghi | Có thể được chia nhỏ bên trong một transaction chunk |
| Transaction timeout | Thời gian tối đa transaction được phép chạy | Không phải số item; chunk quá lớn có thể làm transaction kéo dài và vượt timeout |

Ví dụ, commit interval có thể là 500 trong khi database reader dùng page size 200. Reader có thể cần nhiều page để cung cấp một chunk. Ngược lại, reader có thể fetch trước nhiều dòng hơn chunk hiện tại nhưng chỉ giao từng item cho framework theo contract của nó.

Với `JdbcPagingItemReader`, page size thường được chọn theo hiệu năng truy vấn và bộ nhớ; nó không thay thế commit interval. Với `JdbcCursorItemReader`, fetch size là gợi ý cho JDBC driver, không phải số item mỗi transaction.

## 7. Chọn commit interval phù hợp

Không có một commit interval tối ưu cho mọi Job. Cần cân bằng số lần commit, thời gian giữ transaction, bộ nhớ, throughput và khả năng phục hồi.

### Interval nhỏ

Ví dụ `chunk(20, transactionManager)`:

- Transaction ngắn hơn và thường giữ lock trong thời gian ngắn hơn.
- Checkpoint được cập nhật thường xuyên hơn.
- Khi rollback, nhóm item cần xử lý lại thường nhỏ hơn.
- Số transaction và số lần commit tăng, có thể làm giảm throughput nếu chi phí commit cao.
- Overhead quản lý metadata và transaction tăng theo số chunk.

### Interval lớn

Ví dụ `chunk(1_000, transactionManager)`:

- Giảm số lần commit cho cùng một lượng dữ liệu.
- Có thể tận dụng batch insert/update tốt hơn.
- Giữ transaction và lock lâu hơn, làm tăng nguy cơ contention hoặc timeout.
- Giữ nhiều item trong bộ nhớ hơn, nhất là khi item có object graph lớn.
- Khi chunk rollback, nhiều item có thể phải xử lý lại.
- Checkpoint thưa hơn, nên có thể mất nhiều thời gian hơn để phục hồi sau sự cố.

| Yếu tố | Interval nhỏ | Interval lớn |
|---|---|---|
| Tần suất commit | Cao | Thấp |
| Thời gian một transaction | Thường ngắn | Thường dài |
| Bộ nhớ cho chunk | Thấp hơn | Cao hơn |
| Số item trong chunk rollback | Ít hơn | Nhiều hơn |
| Overhead commit/metadata | Cao hơn | Thấp hơn |
| Checkpoint | Thường xuyên hơn | Thưa hơn |

Hãy đo bằng dữ liệu gần với production. Một interval lớn hơn không chắc nhanh hơn nếu database bị lock lâu, connection bị giữ quá thời gian hoặc writer không xử lý batch hiệu quả.

## 8. Ước lượng interval theo tài nguyên

Giả sử mỗi item chiếm trung bình 2 KB trong bộ nhớ khi nằm trong chunk. Với commit interval 500, riêng payload item có thể cần khoảng 1 MB, chưa tính object overhead, buffer, processor state và dữ liệu phụ. Nếu interval tăng lên 5.000, phần payload tương ứng có thể lên khoảng 10 MB.

Đây chỉ là ước lượng thô. Bộ nhớ thực tế phụ thuộc kích thước object, cấu trúc dữ liệu, số item sau processor, writer và cách reader buffer dữ liệu.

Khi đánh giá interval, nên đo:

- Thời gian đọc, xử lý và ghi một chunk.
- Thời gian commit và thời gian giữ connection/lock.
- Heap sử dụng khi chunk ở kích thước mục tiêu.
- Số rollback, retry và skip.
- Throughput item/giây và thời gian toàn Step.
- Thời gian phục hồi sau khi cố ý làm một chunk thất bại.

Chọn một giá trị ban đầu vừa phải, chạy thử với dữ liệu đại diện, rồi điều chỉnh theo metric. Tránh chọn interval chỉ dựa trên số item tổng hoặc một lần benchmark nhỏ.

## 9. Transaction attributes và giới hạn commit interval

Commit interval không phải cấu hình duy nhất ảnh hưởng transaction. Transaction manager, isolation level, propagation, timeout và resource tham gia transaction đều quan trọng.

Ví dụ đặt transaction timeout cho Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute())
        .build();
```

`transactionAttribute()` có thể trả về `DefaultTransactionAttribute` được cấu hình timeout hoặc isolation phù hợp. Cần chọn timeout đủ dài cho chunk ở điều kiện tải dự kiến, đồng thời tránh transaction kéo dài không cần thiết.

Nếu một service được gọi trong writer mở transaction `REQUIRES_NEW`, transaction mới có thể commit độc lập với transaction chunk. Khi chunk bên ngoài rollback, thay đổi đã commit trong transaction độc lập không bị hoàn tác. Đây là nguyên nhân phổ biến khiến số item ghi thực tế khác với kỳ vọng atomic theo chunk.

## 10. Theo dõi số item và số lần commit

`StepExecution` lưu các counter giúp quan sát hoạt động của Step:

| Counter | Ý nghĩa |
|---|---|
| `readCount` | Số item đọc thành công |
| `writeCount` | Số item được ghi thành công |
| `filterCount` | Số item bị processor filter |
| `readSkipCount` | Số item bị skip do lỗi khi đọc |
| `processSkipCount` | Số item bị skip do lỗi khi xử lý |
| `writeSkipCount` | Số item bị skip do lỗi khi ghi |
| `commitCount` | Số lần commit được ghi nhận cho Step |
| `rollbackCount` | Số lần rollback được ghi nhận cho Step |

Có thể ghi log các chỉ số sau khi Step kết thúc:

```java
public class StepMetricsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

Không nên suy ra commit interval bằng cách lấy `readCount / commitCount` trong mọi trường hợp. Filter, skip, retry, rollback, chunk cuối và transaction phụ có thể làm các counter khác nhau. Hãy xem cấu hình Step cùng lịch sử execution để giải thích metric.

## 11. Những nhầm lẫn thường gặp

**Cho rằng commit interval là số item writer bắt buộc phải ghi.** Processor có thể filter item và skip policy có thể loại item. Writer có thể nhận ít item hơn số đã đọc.

**Cho rằng chunk cuối phải đủ kích thước.** Reader báo EOF trước ngưỡng thì phần item còn lại vẫn được xử lý như chunk nhỏ hơn và commit nếu thành công.

**Đồng nhất page size với commit interval.** Page size điều khiển số dòng reader lấy theo trang; commit interval điều khiển chunk và transaction của Step.

**Tăng interval để luôn tăng throughput.** Chunk lớn có thể làm transaction kéo dài, tăng lock, memory và chi phí rollback. Cần đo trong môi trường đại diện.

**Cho rằng một transaction rollback mọi side effect.** Rollback chỉ áp dụng cho resource tham gia transaction đó. File, API và message bên ngoài cần cơ chế phục hồi riêng.

**Dùng commitCount để suy ra chính xác số chunk dữ liệu mà không xét lỗi.** Retry, skip, rollback và kết thúc Step có thể làm counter phức tạp hơn phép chia tổng item cho interval.

## 12. Cách xác định commit interval cho một Step

Trước hết, xác định kích thước và đặc điểm item, chi phí đọc/ghi, giới hạn transaction của database và khả năng rollback. Chọn một interval ban đầu vừa phải, ví dụ 100 hoặc 500, rồi đo thời gian chunk, commit latency, memory, lock wait và throughput. Nếu commit overhead chiếm nhiều thời gian và tài nguyên còn đủ, thử tăng interval. Nếu transaction dài, lock nhiều hoặc rollback gây xử lý lại quá nhiều dữ liệu, thử giảm interval.

Khi thay đổi interval, hãy kiểm tra cả reader và writer: page/fetch size có còn phù hợp không, writer có batch hiệu quả không, stream có lưu checkpoint đúng không và hệ thống đích có tham gia transaction không. Đừng chỉ thay một con số rồi kết luận hiệu năng đã tốt hơn.

`commit-interval` là cách điều khiển kích thước chunk và tần suất commit của Step. Mỗi chunk thành công tạo một ranh giới transaction; chunk cuối có thể nhỏ hơn ngưỡng, và số item writer nhận có thể khác số item reader đã cung cấp. Hiểu rõ các khác biệt này giúp chọn interval phù hợp, kiểm soát rollback và xây dựng quy trình restart đáng tin cậy.
