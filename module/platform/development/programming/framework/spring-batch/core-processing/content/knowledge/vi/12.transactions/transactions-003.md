# Rollback khi reader, processor hoặc writer lỗi

Trong Spring Batch, một chunk Step thường xử lý dữ liệu trong các transaction có ranh giới theo chunk. Nếu lỗi xảy ra trong lúc đọc, xử lý hoặc ghi item, transaction của chunk hiện tại có thể bị rollback. Những thay đổi thuộc transaction đó được hoàn tác nếu tài nguyên tham gia cùng transaction manager; các chunk đã commit trước đó vẫn được giữ lại.

Hiểu đúng rollback giúp xác định dữ liệu nào đã được lưu, thành phần nào có thể được gọi lại và khi nào cần restart Job. Reader, processor và writer có cách tạo lỗi khác nhau, nhưng đều nằm trong chu trình xử lý chunk. Cần phân biệt rollback của database với tác dụng phụ ở hệ thống ngoài như file, message queue hoặc HTTP API, vì các tác dụng phụ đó không tự động được hoàn tác bởi một transaction JDBC thông thường.

## 1. Transaction boundary trong chunk processing

Một chunk Step đọc, xử lý và ghi một nhóm item trước khi commit. Ví dụ, với `chunk(100, transactionManager)`, Spring Batch xử lý tối đa 100 item trong một chunk rồi commit transaction. Chunk cuối có thể nhỏ hơn nếu reader đã hết dữ liệu.

```text
Chunk 1                         Chunk 2
BEGIN                           BEGIN
  Reader                           Reader
  Processor                        Processor
  Writer                           Writer
COMMIT                          Writer throws exception
                                ROLLBACK
                                (Chunk 2 chưa được commit)

Chunk 3 (nếu Step tiếp tục theo chính sách)
BEGIN
  Reader / Processor / Writer
COMMIT
```

Mỗi chunk có transaction boundary riêng. Vì vậy:

- Nếu chunk 1 đã commit, dữ liệu của chunk 1 vẫn tồn tại khi chunk 2 rollback.
- Nếu chunk 2 chưa commit, các thay đổi database tham gia transaction chunk 2 được hoàn tác.
- Sau khi lỗi được xử lý bằng skip/retry hoặc Job được restart, Spring Batch có thể tiếp tục theo chính sách và trạng thái đã lưu.
- Rollback không có nghĩa toàn bộ Job được đưa về trạng thái ban đầu.

Transaction manager được truyền vào khi cấu hình chunk Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Trong ví dụ, transaction manager điều phối transaction cho mỗi chunk. Nếu writer dùng cùng datasource và transaction manager, các thao tác ghi database của writer có thể tham gia transaction đó.

## 2. Điều gì xảy ra khi reader, processor hoặc writer lỗi?

Lỗi có thể phát sinh ở bất kỳ giai đoạn nào của chu trình:

```text
ItemReader
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
ItemProcessor
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
ItemWriter
   |
   +-- exception --> rollback chunk / skip / retry / fail
   |
   v
Commit
```

Hành vi cụ thể phụ thuộc vào transaction manager, rollback rules, cấu hình fault tolerance và loại exception. Nếu exception được phép retry hoặc skip, framework có thể thực hiện thêm thao tác để tiếp tục. Nếu lỗi không được xử lý theo chính sách, Step thường kết thúc ở trạng thái `FAILED`.

| Thành phần | Ví dụ lỗi | Ảnh hưởng thường gặp |
|---|---|---|
| Reader | Không parse được dòng CSV, mất kết nối nguồn dữ liệu | Chunk hiện tại có thể rollback; exception được skip/retry hoặc làm Step thất bại. |
| Processor | Dữ liệu thiếu trường bắt buộc, lỗi tính toán hoặc dịch vụ tham chiếu timeout | Chunk hiện tại có thể rollback; item có thể được skip/retry theo cấu hình. |
| Writer | Database timeout, vi phạm constraint hoặc lỗi ghi batch | Các thay đổi trong transaction ghi hiện tại có thể rollback; writer có thể được gọi lại khi xử lý lỗi. |

Không nên giả định mọi exception đều có cùng chính sách. Cần phân loại lỗi dữ liệu có thể skip, lỗi tạm thời có thể retry và lỗi nghiêm trọng phải làm Step thất bại.

## 3. Rollback khi ItemReader lỗi

`ItemReader` chịu trách nhiệm lấy item từ nguồn dữ liệu. Reader có thể đọc từ CSV, database, message queue, API hoặc nguồn khác. Khi reader ném exception, chunk đang được xử lý có thể rollback theo transaction và rollback rules của Step.

Ví dụ reader đọc file gặp một dòng không đúng định dạng:

```java
@Bean
FlatFileItemReader<OrderInput> orderReader(
        Resource inputResource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .build();
}
```

Nếu dòng dữ liệu không parse được, reader có thể ném `FlatFileParseException`. Nếu exception này được cấu hình skip và reader có thể tiếp tục đọc, Step có thể bỏ qua dòng lỗi. Nếu không được skip, lỗi có thể làm Step thất bại.

### Reader có thể được gọi lại sau rollback

Với nhiều reader không phải nguồn transactional, việc rollback transaction database không thể đưa nguồn đọc trở về trạng thái trước đó. Ví dụ, rollback JDBC không làm một file vật lý “quay ngược” về dòng trước hoặc hoàn tác một request GET đã gửi đến API.

Spring Batch có cơ chế buffering item đã đọc trong chunk để hỗ trợ rollback/retry. Theo mặc định, item đã đọc có thể được giữ lại để không phải đọc lại từ nguồn khi transaction rollback. Với nguồn có tính transactional như một số message queue, có thể cấu hình reader theo mô hình transactional queue để việc rollback trả message về queue thay vì dựa vào buffer mặc định.

Khi sử dụng reader tùy chỉnh, cần hiểu rõ nó có hỗ trợ `ItemStream` hay không, có lưu trạng thái và có thể khôi phục vị trí đọc không. Không nên giả định mọi nguồn dữ liệu đều có thể rollback thao tác đọc.

### Lỗi read và skip

Read skip xảy ra khi reader ném exception được cấu hình cho phép bỏ qua:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(50)
```

`SkipListener.onSkipInRead` nhận exception nhưng không nhận item vì reader có thể chưa tạo được item hoàn chỉnh. Nếu cần ghi nhận vị trí lỗi, có thể sử dụng thông tin dòng hoặc nguồn dữ liệu mà exception cung cấp.

Không nên skip một exception mất kết nối database hoặc lỗi hạ tầng chung chỉ để Job tiếp tục. Nếu reader không thể đảm bảo đọc đúng phần dữ liệu tiếp theo, Step nên thất bại để có thể điều tra hoặc restart.

## 4. Rollback khi ItemProcessor lỗi

`ItemProcessor` kiểm tra hoặc biến đổi một item. Khi `process` ném exception, chunk step xử lý exception theo rollback rules và chính sách skip/retry đã cấu hình.

Ví dụ:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return toOrder(item);
    }
}
```

Nếu `InvalidOrderException` được phép skip, Spring Batch có thể bỏ qua item lỗi và tiếp tục. Nếu exception không được skip và không thể retry thành công, Step có thể thất bại. Nếu exception được retry, processor có thể được gọi lại cho item đó.

### Processor nên hạn chế tác dụng phụ

Processor thường nên tập trung vào tính toán và chuyển đổi object. Nếu processor gửi email, ghi file hoặc gọi API bên ngoài, các thao tác đó không tự rollback khi transaction database rollback.

Ví dụ không an toàn:

```java
@Override
public Order process(OrderInput item) {
    notificationClient.send("Processing order " + item.orderId());
    return toOrder(item);
}
```

Nếu chunk rollback và processor được gọi lại, thông báo có thể được gửi nhiều lần. Cách an toàn hơn là tạo kết quả trong processor, sau đó phát thông báo qua outbox hoặc một Step riêng có cơ chế chống gửi trùng.

### noRollback cho một số exception

Trong một số trường hợp, ứng dụng có thể xác định một exception không cần rollback transaction. Spring Batch hỗ trợ cấu hình `noRollback(...)` cho chunk step:

```java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
```

Chỉ dùng tùy chọn này khi đã hiểu rõ trạng thái transaction và tác dụng phụ của exception. Nếu exception xảy ra sau khi một phần công việc đã thay đổi dữ liệu mà không rollback, Step phải tiếp tục trong trạng thái nhất quán. Không nên dùng `noRollback` để che lỗi ghi database hoặc tránh rollback mà không có phân tích.

## 5. Rollback khi ItemWriter lỗi

`ItemWriter` nhận các item đã được đọc và xử lý trong chunk. Writer thường ghi nhiều item trong một lần gọi, chẳng hạn batch insert hoặc batch update. Nếu writer ném exception, transaction chunk thường bị rollback.

Ví dụ writer ghi vào database:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount)
                    VALUES
                        (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

Nếu writer ghi một số bản ghi rồi gặp lỗi và tất cả thao tác ghi tham gia cùng transaction, database rollback sẽ hoàn tác các thay đổi trong transaction đó. Các chunk trước đã commit vẫn tồn tại.

### Writer có thể được gọi lại

Khi có lỗi ghi và cấu hình skip/retry, Spring Batch có thể rollback chunk, thử lại thao tác hoặc phân tích các item để xác định item gây lỗi. Trong một số đường xử lý write skip, writer có thể được gọi lại với các nhóm item nhỏ hơn hoặc từng item để tìm bản ghi lỗi.

Do đó, writer phải được thiết kế để chịu được việc gọi lại. Với JDBC writer tham gia transaction, rollback có thể hoàn tác lần ghi trước. Nhưng nếu writer gọi API, ghi file hoặc gửi message bên ngoài transaction, tác dụng phụ có thể đã xảy ra và lần gọi lại có thể tạo kết quả trùng.

### Write skip

Nếu exception từ writer được cấu hình skip, Spring Batch có thể bỏ qua item gây lỗi nếu framework xác định được item đó và việc tiếp tục là an toàn:

```java
.faultTolerant()
.skip(DuplicateOrderException.class)
.skipLimit(100)
```

Writer lỗi do constraint có thể là một lỗi dữ liệu riêng của item hoặc có thể phản ánh một vấn đề rộng hơn như schema sai, database mất kết nối hoặc transaction timeout. Chỉ skip các exception mà nghiệp vụ cho phép bỏ qua. Không nên skip mọi `DataAccessException` vì điều đó có thể làm Job hoàn tất với dữ liệu thiếu do sự cố hệ thống.

## 6. Chunk hiện tại rollback, chunk trước vẫn commit

Một Job xử lý 1.000 item với chunk size 100 thường có nhiều transaction. Giả sử bốn chunk đầu commit thành công và chunk thứ năm gặp lỗi writer:

| Chunk | Trạng thái | Dữ liệu database |
|---|---|---|
| 1 (item 1–100) | `COMMITTED` | Được giữ lại. |
| 2 (item 101–200) | `COMMITTED` | Được giữ lại. |
| 3 (item 201–300) | `COMMITTED` | Được giữ lại. |
| 4 (item 301–400) | `COMMITTED` | Được giữ lại. |
| 5 (item 401–500) | `ROLLED BACK` | Các thay đổi thuộc transaction chunk 5 được hoàn tác. |
| 6 trở đi | Chưa chạy | Chờ Step tiếp tục hoặc được restart. |

Rollback không xóa dữ liệu của bốn chunk đã commit. Nếu Step thất bại, Job có thể được restart theo chính sách và checkpoint đã lưu. Reader/writer cần hỗ trợ restart và các thao tác ghi cần an toàn khi chạy lại.

Đây là một lý do quan trọng để chọn chunk size phù hợp. Chunk quá lớn có thể làm tăng lượng công việc trong một transaction và số item cần xử lý lại. Chunk quá nhỏ có thể tăng chi phí commit và metadata.

## 7. Cấu hình skip và retry khi reader, processor hoặc writer lỗi

Spring Batch cho phép phân loại exception và áp dụng skip/retry ở chunk step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Trong ví dụ:

- Dòng CSV sai định dạng có thể bị skip nếu reader tiếp tục an toàn.
- Item sai quy tắc nghiệp vụ có thể bị skip theo chính sách.
- Lỗi database tạm thời có thể được retry tối đa theo giới hạn.
- Lỗi không thuộc skip/retry policy có thể làm Step thất bại.

Retry phù hợp với lỗi có khả năng tự phục hồi, ví dụ timeout tạm thời hoặc deadlock. Skip phù hợp với lỗi item đã biết là có thể bỏ qua. Lỗi cấu hình, mất kết nối kéo dài hoặc dữ liệu nguồn không đáng tin cậy thường cần làm Step thất bại.

Khi retry hết giới hạn, exception vẫn có thể làm Step thất bại nếu không có chính sách skip phù hợp. Cần tránh cấu hình skip và retry quá rộng cho cùng một nhóm exception mà không hiểu rõ hành vi cuối cùng.

## 8. Rollback và skip listener

`SkipListener` cung cấp callback để ghi nhận item bị skip ở các giai đoạn:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Read skip: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }
}
```

Listener hữu ích để tạo báo cáo reject hoặc log business key. Tuy nhiên, khi lưu item lỗi vào database, cần hiểu transaction và thời điểm callback. Không nên giả định một thao tác ghi reject độc lập luôn được commit cùng transaction của chunk hoặc không bao giờ được gọi lại. Có thể dùng một transaction manager/repository phù hợp, outbox hoặc cơ chế audit idempotent để tránh bản ghi lỗi trùng và giữ tính nhất quán.

## 9. Reader buffering, ItemStream và checkpoint

Rollback transaction không nhất thiết đưa reader về đúng trạng thái nguồn ban đầu. Spring Batch thường buffer các item đã đọc trong chunk để có thể xử lý lại sau rollback mà không cần đọc lại nguồn. Với transactional queue, có thể cấu hình `readerIsTransactionalQueue()` khi reader sử dụng nguồn mà message được trả lại queue bởi rollback.

Các reader/writer có thể triển khai `ItemStream` để quản lý trạng thái qua các callback:

- `open(ExecutionContext)`: khôi phục trạng thái khi Step bắt đầu hoặc restart.
- `update(ExecutionContext)`: ghi checkpoint cần lưu.
- `close()`: giải phóng tài nguyên.

Checkpoint thường được lưu trong Step `ExecutionContext` thông qua JobRepository tại các điểm cập nhật phù hợp với chunk. Khi restart, reader có thể tiếp tục từ vị trí cuối cùng đã commit.

Ví dụ về ý tưởng lưu vị trí đọc:

```java
public class StatefulReader implements ItemStreamReader<OrderInput> {

    private int currentIndex;

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt("currentIndex", 0);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt("currentIndex", currentIndex);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader đang giữ resource.
    }

    @Override
    public OrderInput read() {
        // Đọc item ở currentIndex và tăng chỉ số khi có item.
        return readNextItem();
    }
}
```

Đây là khung minh họa; reader thực tế cần xử lý nguồn dữ liệu, trạng thái kết thúc, thread safety và quy tắc cập nhật index chính xác. Không nên cập nhật checkpoint trước khi công việc tương ứng đã được commit nếu điều đó có thể khiến restart bỏ qua item chưa ghi.

## 10. Transaction chỉ rollback tài nguyên tham gia transaction

Một transaction manager JDBC thường điều phối transaction trên datasource được cấu hình. Nó không tự tạo transaction phân tán giữa mọi tài nguyên mà Step sử dụng.

Ví dụ:

| Tác vụ trong chunk | Có thể rollback cùng JDBC transaction? |
|---|---|
| `INSERT` qua cùng datasource/transaction manager | Có, nếu thao tác tham gia transaction đó. |
| `UPDATE` trên cùng database connection transaction | Có. |
| Ghi sang database khác với transaction manager khác | Không tự động. |
| Gửi HTTP request đến service ngoài | Không. |
| Gửi email | Không. |
| Ghi file trên filesystem | Không. |
| Publish message đến broker không tham gia transaction | Không tự động. |

Nếu writer thực hiện cả ghi database và gọi API, transaction rollback chỉ có thể hoàn tác phần database được quản lý. API có thể đã xử lý yêu cầu. Khi chunk được retry, API có thể nhận cùng yêu cầu lần nữa.

Các cách xử lý thường dùng:

- Thiết kế API nhận idempotency key để nhận diện request lặp.
- Ghi dữ liệu nghiệp vụ và outbox event trong cùng transaction, sau đó publish outbox bằng một thành phần riêng.
- Tách tác dụng phụ bên ngoài thành Step riêng sau khi dữ liệu chính đã commit.
- Dùng business key và quy trình đối soát để phát hiện kết quả đã được xử lý.

## 11. Rollback rules và checked exception

Hành vi rollback chịu ảnh hưởng của transaction attribute và rollback rules. Trong hệ sinh thái Spring, mặc định chung của transaction attribute thường rollback với `RuntimeException` và `Error`; checked exception có thể cần rollback rule rõ ràng tùy cách exception được truyền qua lớp transaction và cấu hình Step.

Khi thiết kế exception cho reader, processor hoặc writer:

- Dùng exception cụ thể để phân biệt lỗi dữ liệu và lỗi hệ thống.
- Xác định exception nào phải rollback transaction.
- Xác định exception nào có thể retry hoặc skip.
- Chỉ dùng `noRollback` cho trường hợp đã hiểu rõ tính nhất quán của dữ liệu.
- Kiểm tra transaction manager và transaction attribute thực tế trong cấu hình ứng dụng.

Không nên suy ra rollback chỉ từ việc exception là checked hay unchecked mà không xem đường đi của exception qua Spring Batch và transaction manager. Hãy kiểm thử với transaction manager thực tế, đặc biệt nếu writer có thao tác nhiều bước.

## 12. Theo dõi rollback trong StepExecution

`StepExecution` lưu các bộ đếm hữu ích để chẩn đoán:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readCount` | Số item đọc thành công. |
| `writeCount` | Số item đã được writer ghi theo thống kê Step. |
| `filterCount` | Số item processor lọc bằng cách trả về `null`. |
| `readSkipCount` | Số item bị skip khi đọc. |
| `processSkipCount` | Số item bị skip khi xử lý. |
| `writeSkipCount` | Số item bị skip khi ghi. |
| `commitCount` | Số lần transaction commit. |
| `rollbackCount` | Số lần transaction rollback. |

Ví dụ, `rollbackCount` tăng liên tục có thể cho thấy writer gặp lỗi, database deadlock hoặc timeout. `processSkipCount` tăng có thể cho thấy dữ liệu nguồn không hợp lệ. Cần kết hợp bộ đếm với failure exception, log, reader position và kết quả dữ liệu đích.

Các bộ đếm không thay thế audit nghiệp vụ. Một Step có thể có `COMPLETED` nhưng vẫn có item bị filter hoặc skip theo chính sách. Muốn hiểu dữ liệu nào bị loại, cần lưu business key và lý do theo cơ chế audit phù hợp.

## 13. Restart sau khi chunk rollback

Nếu exception không được xử lý bằng skip/retry và Step thất bại, Job có thể được restart nếu JobInstance và cấu hình cho phép. Spring Batch tạo `JobExecution` mới cho lần chạy lại, còn lịch sử execution trước vẫn được lưu.

Khi restart:

- Các chunk đã commit trước đó thường không được xử lý lại trong cùng Step restart.
- Chunk chưa commit không được xem là đã hoàn tất.
- Reader có thể khôi phục checkpoint từ ExecutionContext nếu hỗ trợ restart.
- Writer cần tránh ghi trùng nếu có tác dụng phụ đã xảy ra ngoài transaction.
- Step đã hoàn tất thường được bỏ qua; `allowStartIfComplete(true)` có thể cho phép Step đã hoàn tất chạy lại trong một lần restart phù hợp.

Không nên xóa metadata hoặc sửa trực tiếp trạng thái `BATCH_STEP_EXECUTION` để ép restart. Trước khi restart, cần xác định chunk nào đã commit, nguồn đọc có checkpoint ổn định hay không và hệ thống ngoài đã nhận tác dụng phụ nào.

## 14. Ví dụ: writer lỗi và chunk rollback

Giả sử một Step đọc 300 đơn hàng, chunk size là 100. Hai chunk đầu ghi thành công. Trong chunk thứ ba, writer gặp lỗi do một bản ghi vi phạm unique constraint.

Nếu exception không được skip:

1. Writer ném exception trong transaction của chunk thứ ba.
2. Transaction manager rollback các thao tác ghi thuộc chunk thứ ba.
3. Step ghi nhận lỗi và có thể kết thúc `FAILED`.
4. Hai chunk đã commit vẫn còn trong database.
5. Nếu Job được restart, reader tiếp tục từ checkpoint đã lưu phù hợp và Step xử lý phần chưa hoàn tất.

Nếu exception được cấu hình skip và framework xác định được item lỗi:

1. Chunk có thể rollback để xử lý lại theo cơ chế fault tolerance.
2. Item gây lỗi được bỏ qua theo skip policy.
3. Các item còn lại được ghi nếu writer và transaction cho phép.
4. Skip count được cập nhật và `SkipListener` có thể ghi nhận item.
5. Step tiếp tục cho đến khi hết dữ liệu hoặc có lỗi khác.

Điều này cho thấy write skip có thể phức tạp hơn process skip vì writer nhận cả chunk. Writer cần có hành vi nhất quán khi được gọi lại và không tạo tác dụng phụ ngoài transaction không kiểm soát.

## 15. Những lỗi thường gặp khi xử lý rollback

### Nghĩ rằng rollback sẽ xóa cả dữ liệu của chunk trước

Mỗi chunk có transaction riêng. Rollback chỉ tác động đến transaction chưa commit hiện tại và các tài nguyên tham gia transaction đó. Các chunk trước đã commit vẫn tồn tại.

### Nghĩ rằng reader luôn quay lại nguồn đúng vị trí cũ

Nguồn đọc có thể không transactional. Spring Batch có thể buffer item đã đọc; reader tùy chỉnh cần hỗ trợ `ItemStream` và checkpoint nếu muốn restart ổn định. Hãy kiểm tra loại nguồn và cách reader quản lý state.

### Writer ghi một phần rồi exception nhưng không có transaction phù hợp

Nếu thao tác ghi không tham gia transaction hoặc writer gọi hệ thống ngoài, một phần tác dụng phụ có thể còn lại sau rollback. Dùng transaction manager đúng tài nguyên, idempotency hoặc outbox.

### Processor gọi API rồi chunk rollback

Database rollback không hoàn tác API call. Processor có thể được gọi lại khi retry, gây request trùng. Hạn chế side effect trong processor hoặc dùng idempotency key.

### Skip mọi exception để Job luôn hoàn tất

Lỗi database, lỗi cấu hình hoặc lỗi lập trình không phải lúc nào cũng có thể bỏ qua. Chỉ skip exception item-level đã được hiểu và được nghiệp vụ cho phép.

### Dùng noRollback để tránh mọi rollback

Không rollback có thể giữ lại thay đổi một phần và khiến trạng thái dữ liệu không nhất quán. Chỉ cấu hình noRollback cho exception cụ thể khi đã phân tích rõ tác động.

### Restart mà không kiểm tra tác dụng phụ ngoài transaction

Một file có thể đã được chuyển, message đã publish hoặc API đã nhận request dù Step chưa kịp ghi trạng thái hoàn tất. Kiểm tra dữ liệu thực tế và bảo đảm idempotency trước khi restart.

## 16. Quy trình chẩn đoán lỗi reader, processor hoặc writer

Khi một chunk rollback, có thể điều tra theo trình tự:

1. Xác định JobExecution và StepExecution bị lỗi.
2. Đọc failure exception và stack trace để biết lỗi xuất hiện ở reader, processor hay writer.
3. Xem `rollbackCount`, `commitCount`, read/write/skip count và thời điểm cập nhật.
4. Xác định chunk hiện tại chưa commit và các chunk trước đã commit.
5. Kiểm tra transaction manager, datasource và tài nguyên có tham gia transaction hay không.
6. Xem reader có buffering, `ItemStream` và checkpoint ổn định không.
7. Kiểm tra writer hoặc processor có tác dụng phụ ngoài transaction đã xảy ra không.
8. Quyết định lỗi nên retry, skip hay làm Step thất bại.
9. Trước khi restart, đối chiếu dữ liệu nghiệp vụ và thiết kế chống ghi/gửi trùng.

## Kết luận

Khi reader, processor hoặc writer lỗi trong chunk Step, transaction của chunk hiện tại thường được rollback theo rollback rules và transaction manager. Những chunk đã commit trước đó vẫn được giữ lại. Reader có thể cần buffering hoặc checkpoint để phục hồi vị trí; processor nên hạn chế tác dụng phụ vì có thể được gọi lại; writer cần tham gia transaction hoặc có cơ chế idempotency khi ghi sang hệ thống ngoài. Skip và retry cho phép xử lý một số lỗi có kiểm soát, còn lỗi không thể tiếp tục an toàn nên làm Step thất bại để điều tra hoặc restart.
