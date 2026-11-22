# ItemWriteListener

`ItemWriteListener` là listener của Spring Batch dùng để quan sát vòng đời ghi dữ liệu trong một chunk-oriented step. Listener cung cấp callback trước khi writer được gọi, sau khi writer hoàn tất bình thường và khi writer ném exception.

Listener hữu ích để ghi log, theo dõi số lượng item, đo thời gian ghi hoặc ghi nhận lỗi vận hành. Nó giúp đặt logic quan sát cạnh giai đoạn write mà không phải nhồi logging và metric vào `ItemWriter`.

Điều cần nhớ là `afterWrite` có nghĩa phương thức writer đã trả về thành công; nó không tự chứng minh transaction của chunk đã commit. Nếu cần hành động chỉ được thực hiện sau commit, phải dùng cơ chế gắn với transaction commit hoặc outbox.

## 1. ItemWriteListener nằm ở đâu trong chunk?

Trong chunk-oriented processing, Spring Batch đọc item, chuyển từng item qua processor rồi chuyển nhóm item đầu ra cho writer. `ItemWriteListener` bao quanh lời gọi writer của từng chunk.

```text
Chunk transaction bắt đầu
        |
        v
   ItemReader
        |
        v
   ItemProcessor
        |
        v
   beforeWrite(chunk)
        |
        v
   ItemWriter.write(chunk)
        |
        +---- writer thành công ----> afterWrite(chunk)
        |
        +---- writer ném lỗi -------> onWriteError(exception, chunk)
        |
        v
   Các bước hoàn tất transaction
        |
        v
   Commit hoặc rollback
```

Listener làm việc theo chunk, không phải callback riêng cho từng item. Nếu chunk chứa 100 item, `beforeWrite` và `afterWrite` thường mỗi callback được gọi một lần cho nhóm đó, không phải 100 lần.

## 2. Ba callback chính

Trong Spring Batch 5, `ItemWriteListener<T>` nhận `Chunk`:

```java
public interface ItemWriteListener<S> extends StepListener {
    default void beforeWrite(Chunk<? extends S> items) { }
    default void afterWrite(Chunk<? extends S> items) { }
    default void onWriteError(Exception exception, Chunk<? extends S> items) { }
}
```

Ba callback có ý nghĩa khác nhau:

| Callback | Thời điểm | Mục đích thường dùng |
|---|---|---|
| `beforeWrite(items)` | Ngay trước khi gọi `ItemWriter.write` | Ghi nhận bắt đầu ghi, kích thước chunk hoặc thời gian bắt đầu |
| `afterWrite(items)` | Sau khi `ItemWriter.write` trả về bình thường | Ghi nhận writer call hoàn tất, số item đã được writer xử lý |
| `onWriteError(exception, items)` | Khi `ItemWriter.write` ném exception | Ghi log lỗi và thông tin chunk liên quan |

Các callback nhận chunk được đưa cho writer. `onWriteError` nhận cả exception và chunk, nhưng không tự xác định chính xác item nào trong chunk gây lỗi.

## 3. Triển khai ItemWriteListener

Ví dụ listener ghi log cho một step nhập đơn hàng:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderWriteListener.class);

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("Starting write for {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.info("Writer completed for {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.error(
            "Writer failed for a chunk containing {} orders",
            items.size(),
            exception
        );
    }
}
```

Ví dụ dùng `Logger` để ghi số lượng item và exception. Listener không sửa item, không nuốt lỗi và không tự gọi writer lần nữa. Nếu cần thêm thông tin để điều tra, chỉ log các mã định danh không nhạy cảm thay vì dump toàn bộ payload.

## 4. Đăng ký listener vào Step

Có thể khai báo listener thành bean Spring rồi gắn vào step bằng `.listener(...)`:

```java
@Bean
OrderWriteListener orderWriteListener() {
    return new OrderWriteListener();
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        OrderWriteListener orderWriteListener) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderWriteListener)
        .build();
}
```

Listener được gắn vào step nên nó nhận sự kiện write của writer trong step đó. Nếu một job có nhiều step ghi dữ liệu, có thể đăng ký listener ở từng step với kiểu item phù hợp hoặc dùng một listener dùng chung nếu hợp đồng và phạm vi quan sát tương thích.

## 5. beforeWrite: quan sát trước khi ghi

`beforeWrite` chạy ngay trước lời gọi writer. Đây là nơi phù hợp để:

- Ghi log rằng một chunk sắp được ghi.
- Ghi nhận số item chuẩn bị ghi.
- Bắt đầu đo thời gian của writer call.
- Thêm thông tin tương quan vào log như job execution ID hoặc step name.

Ví dụ bắt đầu đo thời gian:

```java
public class TimedOrderWriteListener implements ItemWriteListener<Order> {

    private final ThreadLocal<Long> startedAt = new ThreadLocal<>();

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        startedAt.set(System.nanoTime());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        Long start = startedAt.get();
        if (start != null) {
            long elapsedNanos = System.nanoTime() - start;
            recordWriteDuration(elapsedNanos, items.size());
        }
        startedAt.remove();
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        startedAt.remove();
    }
}
```

Đây là ví dụ minh họa việc đo thời gian giữa hai callback; `recordWriteDuration` là hàm metric của ứng dụng. Nếu step chạy song song, state đo thời gian phải được cô lập theo thread hoặc theo execution. `ThreadLocal` cần được dọn ở cả đường thành công và lỗi để tránh giữ state trên thread pool.

Không nên dùng `beforeWrite` để sửa item nhằm thay đổi dữ liệu đầu ra. Việc chuẩn hóa và biến đổi dữ liệu thuộc reader/processor; writer nhận item đã được chuẩn bị theo hợp đồng của pipeline.

## 6. afterWrite: writer call đã hoàn tất

`afterWrite` được gọi khi phương thức `ItemWriter.write` trả về bình thường. Nó phù hợp để ghi nhận writer call thành công hoặc cập nhật metric về số item mà writer đã xử lý.

```java
@Override
public void afterWrite(Chunk<? extends Order> items) {
    successfulWriteCalls.increment();
    writtenItems.add(items.size());
    log.debug("Writer returned normally for {} orders", items.size());
}
```

Các metric trong ví dụ có thể là counter của Micrometer hoặc bộ đếm do ứng dụng quản lý. Nên đặt tên metric thể hiện rõ đó là số lần writer trả về thành công hoặc số item được gửi tới writer.

### afterWrite không đồng nghĩa với commit

`afterWrite` xảy ra sau khi writer method trả về nhưng trong quá trình xử lý chunk. Transaction của chunk chưa nhất thiết đã commit. Một lỗi xảy ra ở bước hoàn tất transaction hoặc khi commit có thể khiến chunk rollback sau khi `afterWrite` đã chạy.

Vì vậy, tránh dùng `afterWrite` để:

- Gửi thông báo bên ngoài với nội dung khẳng định dữ liệu đã commit.
- Cập nhật hệ thống khác như thể giao dịch nghiệp vụ đã hoàn tất chắc chắn.
- Đánh dấu item là hoàn tất vĩnh viễn trong một kho dữ liệu không tham gia transaction.

Nếu cần phát sự kiện chỉ sau khi transaction commit, hãy dùng transaction synchronization phù hợp hoặc ghi sự kiện vào outbox trong cùng transaction với dữ liệu nghiệp vụ rồi phát đi sau commit. Điều này giúp tránh thông báo thành công cho dữ liệu đã rollback.

## 7. onWriteError: ghi nhận lỗi của writer

`onWriteError` được gọi khi writer ném exception. Listener nhận exception và toàn bộ chunk được truyền cho writer trong lần gọi đó.

```java
@Override
public void onWriteError(
        Exception exception,
        Chunk<? extends Order> items) {

    log.error(
        "Failed to write {} orders; exception type={}",
        items.size(),
        exception.getClass().getSimpleName(),
        exception
    );
}
```

Callback này hữu ích để quan sát lỗi SQL, lỗi kết nối hoặc lỗi ghi file. Nó cũng có thể ghi metric lỗi và thông tin tương quan giúp truy vết JobExecution/StepExecution.

Listener không nên bắt exception writer rồi coi như đã xử lý xong. Exception phải tiếp tục được Spring Batch xử lý theo transaction, retry và skip policy. Nếu listener nuốt lỗi hoặc tự gọi writer lần nữa, trạng thái step có thể không phản ánh đúng kết quả thực tế.

### onWriteError không nhất thiết chỉ ra item lỗi

Writer nhận cả chunk trong một lời gọi. Nếu writer ném lỗi khi ghi một trong các item, listener thường chỉ biết chunk nào thất bại và exception nào được ném; không phải lúc nào cũng biết chính xác item gây lỗi.

Ví dụ chunk có 100 đơn hàng nhưng database báo lỗi unique constraint. Nếu exception không chứa khóa gây lỗi hoặc writer không cung cấp thông tin đó, `onWriteError` không thể suy ra item lỗi chỉ từ chunk.

Khi cần xác định item cụ thể bị skip sau recovery, dùng `SkipListener.onSkipInWrite(item, exception)`. Đây là callback khác với `ItemWriteListener.onWriteError` và có ngữ nghĩa theo từng item bị skip.

## 8. Phân biệt ItemWriteListener và SkipListener

Hai listener thường được dùng cùng nhau nhưng quan sát hai điều khác nhau:

| Listener | Callback | Phạm vi thông tin | Mục đích |
|---|---|---|---|
| `ItemWriteListener` | `beforeWrite` | Chunk sắp ghi | Quan sát bắt đầu write |
| `ItemWriteListener` | `afterWrite` | Chunk writer xử lý thành công | Quan sát writer call hoàn tất |
| `ItemWriteListener` | `onWriteError` | Exception và chunk bị lỗi | Quan sát lần gọi writer thất bại |
| `SkipListener` | `onSkipInWrite` | Item cụ thể bị skip và exception | Ghi nhận item bị loại sau recovery |

Ví dụ, writer thử ghi một chunk và ném exception. `onWriteError` có thể ghi nhận chunk thất bại. Nếu fault-tolerance policy xác định một item được skip, `onSkipInWrite` ghi nhận item đó. Nếu chunk được retry và sau đó thành công, listener write có thể được gọi lại trong các lần thử.

Không nên dùng `onWriteError` làm nguồn thống kê cuối cùng cho số item bị skip. Một chunk lỗi có thể được retry thành công, hoặc lỗi có thể làm step thất bại mà không có item nào được skip.

## 9. Listener khi retry và skip

Khi step được cấu hình retry, một writer call có thể được thử lại. Vì vậy, `beforeWrite` và các callback tương ứng có thể xuất hiện nhiều lần cho cùng dữ liệu. `onWriteError` ghi nhận từng lần writer ném lỗi; `afterWrite` ghi nhận những lần writer trả về bình thường.

Ví dụ cấu hình fault tolerance:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .listener(orderWriteListener)
    .build();
```

Đây là cấu hình minh họa: lỗi ghi tạm thời có thể được retry theo policy, còn lỗi dữ liệu cụ thể có thể được skip nếu phát sinh ở giai đoạn phù hợp. Hãy chọn exception và giới hạn theo nghiệp vụ.

Khi thiết kế metric, phân biệt:

- Số lần writer được gọi.
- Số lần writer ném exception.
- Số lần writer trả về bình thường.
- Số item được gửi vào writer.
- Số item thực sự bị skip sau recovery.
- Số chunk cuối cùng được commit.

Các con số này không tương đương. Ví dụ một chunk có thể được writer gọi hai lần: lần đầu lỗi, lần sau thành công. Nếu chỉ cộng số item trong `afterWrite`, có thể đếm cùng một item nhiều lần khi có retry.

## 10. Callback và transaction boundary

Các callback của `ItemWriteListener` diễn ra trong luồng xử lý write của chunk. Chúng không tạo transaction riêng và cũng không tự commit hoặc rollback dữ liệu.

```text
Transaction chunk
    |
    +--> beforeWrite
    |
    +--> ItemWriter.write
    |       |
    |       +--> trả về bình thường: afterWrite
    |       |
    |       +--> ném exception: onWriteError
    |
    +--> hoàn tất step/chunk transaction
            |
            +--> COMMIT
            |
            +--> ROLLBACK nếu có lỗi
```

Listener có thể truy cập metadata thông qua các cơ chế phù hợp nếu cần, nhưng không nên tự quản lý transaction của step. Nếu listener ghi vào cùng datasource và cùng transaction manager, thay đổi có thể tham gia transaction chunk. Nếu ghi sang datasource khác hoặc gọi hệ thống ngoài, cần xử lý tính nhất quán riêng.

## 11. Không đặt nghiệp vụ ghi dữ liệu trong listener

Listener là hook quan sát vòng đời, không phải nơi thay thế writer hoặc processor. Tránh đặt các thao tác nghiệp vụ quan trọng trong callback vì chúng có thể bị gọi lại do retry hoặc có thể chạy trước khi transaction commit.

Các việc phù hợp:

- Ghi log kỹ thuật có kiểm soát.
- Tăng metric về số item và thời gian writer call.
- Thêm correlation ID hoặc thông tin step vào log.
- Ghi nhận exception để chẩn đoán.

Các việc cần cân nhắc hoặc nên đặt ở thành phần khác:

- Biến đổi item: thực hiện trong `ItemProcessor`.
- Ghi dữ liệu đích: thực hiện trong `ItemWriter`.
- Lưu reject record cho từng item bị skip: dùng `SkipListener` hoặc cơ chế reject chuyên biệt.
- Phát sự kiện sau commit: dùng outbox hoặc transaction synchronization.
- Thay đổi trạng thái nghiệp vụ quan trọng: đặt trong service/writer với transaction rõ ràng.

Nếu listener ném exception, callback có thể làm ảnh hưởng đến execution của step. Vì vậy, logging và metrics trong listener nên có độ tin cậy phù hợp; tránh để lỗi của hệ thống quan sát làm hỏng batch nếu chính sách vận hành không yêu cầu điều đó.

## 12. Thread safety và listener dùng chung

Listener bean Spring thường là singleton và có thể được dùng bởi nhiều lần chạy hoặc nhiều thread tùy cấu hình step. Không nên lưu state mutable theo chunk trong field thông thường nếu listener có thể được gọi đồng thời.

Ví dụ không an toàn:

```java
public class UnsafeListener implements ItemWriteListener<Order> {
    private long currentChunkStart;

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        currentChunkStart = System.nanoTime();
    }
}
```

Nếu hai thread cùng dùng listener, thread này có thể ghi đè thời điểm bắt đầu của thread kia. Hãy dùng state theo execution/thread, metric thread-safe hoặc tránh lưu state trong listener. Với `ThreadLocal`, phải xóa dữ liệu ở cả đường thành công và lỗi.

Khi dùng partitioning, mỗi step execution có thể có listener instance riêng hoặc dùng chung tùy cách cấu hình bean và scope. Hãy xác định lifecycle thực tế và kiểm tra concurrency trước khi thêm mutable state.

## 13. Ghi log và metric có ích

Log listener nên giúp trả lời được các câu hỏi vận hành:

- Job nào và step nào đang ghi?
- Chunk có bao nhiêu item?
- Writer call mất bao lâu?
- Lỗi thuộc loại nào và có correlation ID nào?
- Đây là lần thử thứ mấy nếu có retry?

Không nên ghi toàn bộ object hoặc dữ liệu nhạy cảm vào log. Dùng mã định danh nghiệp vụ đã được phép, execution ID và số lượng item. Với metric, tránh dùng order ID hoặc tenant ID có cardinality quá cao làm label; thay vào đó dùng nhãn ổn định như job name, step name, outcome và exception category.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `afterWrite` với transaction commit | Có thể phát thông báo thành công trước khi chunk rollback | Dùng after-commit hook hoặc outbox cho sự kiện sau commit |
| Cho rằng `onWriteError` xác định được item lỗi | Chỉ có thể biết chunk và exception nếu writer không cung cấp item cụ thể | Dùng `SkipListener.onSkipInWrite` khi cần item bị skip |
| Đếm item trong `afterWrite` như số item unique đã commit | Retry có thể làm cùng item được đếm nhiều lần | Phân biệt writer-call metric với committed-item metric |
| Nuốt exception trong listener | Che giấu lỗi hoặc thay đổi kết quả xử lý step | Để exception writer tiếp tục đi qua Spring Batch; listener không nuốt lỗi |
| Thực hiện side effect bên ngoài trong `afterWrite` | Side effect có thể tồn tại dù chunk rollback | Dùng outbox hoặc after-commit synchronization |
| Giữ mutable state trong singleton listener | Race condition khi chạy song song | Dùng state thread-safe hoặc theo execution |
| Log toàn bộ chunk | Tăng log volume và có thể lộ dữ liệu nhạy cảm | Log count, ID an toàn và correlation metadata |

## 15. Kiểm thử ItemWriteListener

Có thể kiểm thử listener độc lập bằng cách gọi trực tiếp các callback với chunk mẫu, đồng thời kiểm thử tích hợp qua một step để xác nhận callback được gọi ở đúng tình huống.

Các tình huống nên bao gồm:

1. Writer trả về bình thường: `beforeWrite` và `afterWrite` được gọi.
2. Writer ném exception: `beforeWrite` và `onWriteError` được gọi; `afterWrite` không được xem là callback thành công cho lần gọi đó.
3. Retry: xác nhận listener ghi nhận từng attempt theo cách metric mong muốn.
4. Skip khi write lỗi: phân biệt chunk-level `onWriteError` với item-level `SkipListener.onSkipInWrite`.
5. Commit thất bại sau khi writer trả về: xác nhận `afterWrite` không bị hiểu nhầm là bằng chứng commit.
6. Chạy song song: listener không trộn state hoặc metric giữa các execution.

Với integration test, có thể dùng writer giả lập để kiểm soát khi nào writer trả về hoặc ném exception. Kiểm tra trạng thái JobExecution/StepExecution và dữ liệu transaction để xác nhận listener chỉ quan sát sự kiện theo đúng ranh giới đã thiết kế.

## Kết luận

`ItemWriteListener` cung cấp ba callback ở cấp chunk: `beforeWrite` chạy trước writer, `afterWrite` chạy khi writer trả về bình thường và `onWriteError` chạy khi writer ném exception. Listener phù hợp cho logging, metrics và quan sát lỗi; nó không thay thế `ItemWriter`, `SkipListener` hoặc cơ chế transaction.

Đặc biệt, `afterWrite` không đồng nghĩa dữ liệu đã commit. Khi có retry, callback có thể xuất hiện nhiều lần cho cùng chunk; khi cần ghi nhận item bị skip, hãy dùng `SkipListener`. Giữ listener stateless hoặc thread-safe, tránh side effect không idempotent và dùng outbox/after-commit hook cho hành động chỉ được phép xảy ra sau commit.
