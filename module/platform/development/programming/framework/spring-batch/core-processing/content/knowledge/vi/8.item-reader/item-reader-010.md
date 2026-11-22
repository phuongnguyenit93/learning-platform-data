# Reader thread safety

Trong Spring Batch, `ItemReader` thường giữ trạng thái để biết item tiếp theo cần đọc. Trạng thái đó có thể là vị trí hiện tại trong file, cursor của truy vấn, số trang đã đọc hoặc một iterator đang tiến dần qua tập dữ liệu. Khi một Step chạy trên nhiều thread, nhiều lời gọi `read()` có thể diễn ra đồng thời. Nếu reader không được thiết kế an toàn cho truy cập đồng thời, các thread có thể đọc trùng item, bỏ sót item hoặc làm hỏng trạng thái nội bộ.

Vì vậy, khi bật xử lý đa luồng, cần xác định reader được dùng theo cách nào: mỗi thread có reader riêng, tất cả thread dùng chung reader đã đồng bộ, hay việc đọc vẫn diễn ra tuần tự trong một thread. Việc chọn chiến lược ảnh hưởng đến tính đúng đắn, thứ tự xử lý, hiệu năng và khả năng restart.

## 1. Vì sao ItemReader có thể không thread-safe?

`ItemReader<T>` cung cấp phương thức `read()` để trả về item kế tiếp hoặc `null` khi hết dữ liệu. Interface này không bảo đảm mọi implementation đều thread-safe. Nhiều reader có trạng thái thay đổi sau mỗi lần đọc.

Ví dụ một reader tự quản lý vị trí trong danh sách:

```java
public class SimpleListReader implements ItemReader<String> {

    private final List<String> items;
    private int index = 0;

    public SimpleListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public String read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }
}
```

Trong một thread, `index` được tăng lần lượt và reader có thể trả về các item theo thứ tự. Nhưng nếu hai thread gọi `read()` cùng lúc, thao tác kiểm tra `index` và tăng `index` không phải một thao tác nguyên tử. Cả hai thread có thể cùng đọc một vị trí trước khi một thread cập nhật index, dẫn đến trả về cùng item hoặc làm sai vị trí tiếp theo.

Với reader đọc từ file, database hoặc API, trạng thái nội bộ có thể phức tạp hơn:

- File reader có thể giữ line number, buffer và trạng thái stream.
- Cursor reader có thể giữ cursor và vị trí hiện tại trong `ResultSet`.
- Paging reader có thể giữ số trang, sort key hoặc thông tin truy vấn trang tiếp theo.
- Reader tùy chỉnh có thể giữ iterator, cache, bộ đếm hoặc dữ liệu tạm.

Nếu nhiều thread cùng thay đổi các trạng thái này mà không có đồng bộ phù hợp, kết quả đọc có thể không xác định. Việc một reader chạy đúng trong test tuần tự không chứng minh nó an toàn khi chạy đồng thời.

## 2. Khi nào Spring Batch gọi reader từ nhiều thread?

Một trường hợp thường gặp là multi-threaded Step. Step được cấu hình với `TaskExecutor` có thể xử lý các chunk trên những thread khác nhau. Tùy cách cấu hình và loại Step, các thao tác đọc, xử lý và ghi có thể được thực hiện bởi các thread worker.

Ví dụ cấu hình khái quát:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .taskExecutor(taskExecutor)
        .build();
```

Khi nhiều chunk được thực hiện đồng thời, reader được chia sẻ bởi Step có thể nhận các lời gọi `read()` từ nhiều thread. Nếu reader có trạng thái mutable và không hỗ trợ truy cập đồng thời, đây là một điểm có nguy cơ gây lỗi.

Sơ đồ minh họa:

```text
                  Multi-threaded Step
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Thread 1    Thread 2    Thread 3
             |           |           |
             +-----------+-----------+
                         |
                         v
                Shared ItemReader
                  read() đồng thời
```

Các triệu chứng thường gặp gồm:

- Một bản ghi xuất hiện hai lần trong kết quả.
- Một số bản ghi không được xử lý dù nguồn có đủ dữ liệu.
- Lỗi kiểu `ConcurrentModificationException`, lỗi cursor hoặc lỗi truy cập stream.
- Thứ tự item ở Writer khác thứ tự nguồn.
- Lỗi chỉ xuất hiện khi tăng số thread hoặc tăng tốc độ xử lý.
- Kết quả khác nhau giữa các lần chạy cùng dữ liệu.

## 3. Cách 1: đồng bộ lời gọi read bằng SynchronizedItemStreamReader

Nếu nhiều thread cần dùng chung một reader, có thể bọc reader bằng `SynchronizedItemStreamReader`. Decorator này đồng bộ lời gọi `read()` để tại một thời điểm chỉ có một thread thực hiện thao tác đọc trên delegate.

Ví dụ với `FlatFileItemReader`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.support.SynchronizedItemStreamReader;
import org.springframework.core.io.FileSystemResource;

@Bean
public SynchronizedItemStreamReader<Customer> customerReader() {
    FlatFileItemReader<Customer> delegate =
            new FlatFileItemReaderBuilder<Customer>()
                    .name("customerFileReader")
                    .resource(new FileSystemResource("data/customers.csv"))
                    .delimited()
                    .names("id", "name")
                    .targetType(Customer.class)
                    .build();

    SynchronizedItemStreamReader<Customer> reader =
            new SynchronizedItemStreamReader<>();
    reader.setDelegate(delegate);
    return reader;
}
```

Sau khi bọc, Step dùng `customerReader` như một `ItemStreamReader` bình thường. Các thread có thể cùng yêu cầu item, nhưng thao tác `read()` trên delegate được thực hiện lần lượt.

```text
Thread 1 ----+
             |
Thread 2 ----+----> SynchronizedItemStreamReader
             |          |
Thread 3 ----+          v
                    lock / read()
                         |
                         v
                    Delegate Reader
```

### Ưu điểm và giới hạn

- Dễ áp dụng khi cần bảo vệ một reader dùng chung mà chưa thể tách nguồn thành nhiều phần.
- Tránh các lời gọi `read()` đồng thời trên delegate.
- Các phần xử lý sau khi đọc vẫn có thể chạy đồng thời tùy cấu hình Step.
- Việc đọc bị tuần tự hóa, vì vậy reader có thể trở thành nút thắt hiệu năng.
- Decorator không tự làm cho `ItemProcessor`, `ItemWriter`, cache hoặc các trạng thái mutable khác trở nên thread-safe.

`SynchronizedItemStreamReader` chủ yếu đồng bộ lời gọi `read()`. Không nên giả định nó biến toàn bộ delegate và mọi trạng thái liên quan thành thread-safe trong mọi tình huống. Cần xem xét cách delegate quản lý `open`, `update`, `close` và checkpoint theo loại reader đang dùng.

Một giới hạn quan trọng là khả năng restart. Tài liệu của Spring Batch lưu ý rằng việc dùng synchronized reader có thể làm Job không restartable nếu việc đọc lại một item đã được xử lý là vấn đề. Khi các thread đọc item theo thứ tự nhưng xử lý và commit không theo thứ tự đó, checkpoint có thể không đại diện đơn giản cho một vị trí liên tục trong nguồn. Hãy cân nhắc kỹ trước khi dùng cách này cho một Job yêu cầu restart chính xác.

## 4. Cách 2: partitioning để mỗi worker có reader riêng

Với dữ liệu lớn và cần xử lý song song thực sự, partitioning thường là cách phù hợp hơn. Thay vì để nhiều thread cùng truy cập một reader, Spring Batch chia nguồn dữ liệu thành các partition. Mỗi partition chạy một worker StepExecution riêng và có reader riêng, chỉ đọc phần dữ liệu được giao.

Ví dụ chia khách hàng theo khoảng ID:

```text
Manager Step
    |
    +--> Partition 1: customerId 1 - 1000
    |        Worker StepExecution 1
    |        Reader instance 1
    |
    +--> Partition 2: customerId 1001 - 2000
    |        Worker StepExecution 2
    |        Reader instance 2
    |
    +--> Partition 3: customerId 2001 - 3000
             Worker StepExecution 3
             Reader instance 3
```

Mỗi reader chỉ truy cập một phạm vi dữ liệu, nên không cần chia sẻ cursor hoặc index giữa các worker. Các partition cần không chồng lấn và phải bao phủ đúng tập dữ liệu cần xử lý.

Với partitioning, có thể dùng `@StepScope` để tạo reader theo từng worker StepExecution và lấy giới hạn từ `stepExecutionContext`:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Customer> partitionReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("partitionCustomerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "name")
            .targetType(Customer.class)
            .build();
}
```

Trong ví dụ, mỗi partition có `inputFile` riêng trong `ExecutionContext`. Khi worker StepExecution được tạo, Spring Batch cung cấp giá trị tương ứng để reader mở đúng nguồn. Với dữ liệu database, có thể truyền `minId` và `maxId` rồi tạo truy vấn giới hạn theo khoảng đó.

`@StepScope` giúp bean được tạo theo phạm vi StepExecution và hỗ trợ late binding tham số. Tuy nhiên, chỉ thêm `@StepScope` vào một reader trong multi-threaded Step không tự tạo một reader cho mỗi thread: các thread trong cùng StepExecution vẫn có thể dùng chung target của bean. Việc cô lập reader đến từ các StepExecution riêng trong partitioning.

## 5. Cách 3: giữ đọc tuần tự, chạy xử lý bất đồng bộ

Nếu phần tốn thời gian chủ yếu nằm trong xử lý nghiệp vụ, có thể giữ `ItemReader` ở một luồng đọc tuần tự và chuyển công việc xử lý sang các thread khác. Cách này tránh nhiều thread cùng gọi reader.

Một lựa chọn trong hệ sinh thái Spring Batch là `AsyncItemProcessor` kết hợp `AsyncItemWriter` (thuộc module Spring Batch Integration). Reader đọc item theo thứ tự, processor xử lý các item bất đồng bộ, writer nhận kết quả tương ứng để ghi.

```text
Single Reader
     |
     v
Đọc item tuần tự
     |
     v
AsyncItemProcessor
     |
     +----> Worker thread 1: process item A
     +----> Worker thread 2: process item B
     +----> Worker thread 3: process item C
     |
     v
AsyncItemWriter
     |
     v
Ghi kết quả
```

Cách này phù hợp khi reader cần duy trì thứ tự hoặc có state không thread-safe, còn processor có thể chạy độc lập. Cần lưu ý rằng kết quả xử lý bất đồng bộ có thể hoàn thành theo thứ tự khác thứ tự đọc. Nếu nghiệp vụ yêu cầu thứ tự đầu ra, cần cơ chế giữ thứ tự hoặc gắn sequence number để sắp xếp trước khi ghi.

Async processor cũng không tự làm cho các dependency được gọi bên trong processor thread-safe. Nếu processor dùng chung một client, cache hoặc mutable service, các thành phần đó vẫn phải hỗ trợ truy cập đồng thời hoặc được tạo theo phạm vi thích hợp.

## 6. @StepScope có giải quyết thread safety không?

`@StepScope` thường được dùng với reader cần nhận JobParameters hoặc `ExecutionContext` tại thời điểm Step bắt đầu. Nó giúp tạo bean theo phạm vi một StepExecution, thay vì tạo một instance chung từ lúc khởi động application context.

Điều quan trọng là phạm vi này gắn với StepExecution, không phải tự động gắn với từng thread:

| Cấu hình | Hành vi |
|---|---|
| Một singleton reader dùng trong multi-threaded Step | Nhiều thread có thể cùng truy cập một instance. |
| Một `@StepScope` reader trong một multi-threaded Step | Các thread của cùng StepExecution vẫn có thể dùng chung target reader đó. |
| Một `@StepScope` reader trong partitioned Step | Mỗi worker StepExecution có thể có target reader riêng và dữ liệu phạm vi riêng. |

Vì vậy, `@StepScope` giải quyết vòng đời và late binding của bean. Nó không thay thế đồng bộ hóa hoặc thiết kế phân vùng dữ liệu.

## 7. Những thành phần khác cũng cần an toàn khi chạy đồng thời

Mặc dù bài học tập trung vào reader, thread safety phải được xem xét cho toàn bộ pipeline:

- **ItemProcessor:** tránh dùng biến instance mutable chung nếu nhiều thread cùng gọi `process()`. Các dependency được chia sẻ phải hỗ trợ concurrent access.
- **ItemWriter:** bảo đảm writer và các tài nguyên nó sử dụng an toàn khi nhiều thread ghi. Transaction và thứ tự ghi cần được thiết kế rõ.
- **Listeners:** listener có thể được gọi từ nhiều thread; bộ đếm hoặc bộ sưu tập dùng chung cần đồng bộ phù hợp.
- **ExecutionContext:** không dùng chung key hoặc mutable object giữa các partition theo cách gây ghi đè trạng thái.
- **Nguồn dữ liệu:** connection, cursor, file stream hoặc API client phải được dùng theo giới hạn thread safety của implementation.

Không nên giả định rằng một reader thread-safe đồng nghĩa toàn bộ Step thread-safe. Tương tự, dùng `synchronized` trên `read()` không bảo đảm thứ tự hoàn tất của chunk hoặc thứ tự ghi.

## 8. Chọn chiến lược nào?

| Nhu cầu | Chiến lược phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Reader dùng chung, cần bảo vệ nhanh lời gọi đọc | `SynchronizedItemStreamReader` | Đọc bị tuần tự hóa; đánh giá khả năng restart và thứ tự xử lý. |
| Dữ liệu có thể chia thành các phần độc lập | Partitioning với reader riêng cho mỗi StepExecution | Cần thiết kế partition không chồng lấn và xử lý đủ dữ liệu. |
| Reader cần chạy tuần tự, Processor mới là phần chậm | Async processor/writer | Cần quản lý thứ tự kết quả và thread safety của processor. |
| Dữ liệu nhỏ, không cần song song | Step tuần tự | Đơn giản nhất, tránh phức tạp đồng bộ không cần thiết. |

Ưu tiên chiến lược phản ánh cấu trúc dữ liệu. Nếu có thể chia dữ liệu thành các phạm vi độc lập, partitioning thường giúp tăng song song mà không bắt nhiều thread tranh chấp một cursor. Nếu không thể chia nguồn và cần dùng chung reader, synchronized wrapper là một lựa chọn, nhưng phải chấp nhận giới hạn hiệu năng và đánh giá restart.

## 9. Kiểm tra reader trong môi trường concurrent

Một reader chạy tuần tự đúng chưa đủ để chứng minh nó an toàn khi nhiều thread cùng sử dụng. Khi thiết kế hoặc chọn reader cho Step concurrent, nên kiểm tra các tình huống sau:

1. **Không mất item:** tổng số item được xử lý khớp với số item đủ điều kiện trong nguồn.
2. **Không đọc trùng:** mỗi khóa nghiệp vụ chỉ xuất hiện đúng số lần dự kiến.
3. **Không hỏng state:** không có lỗi cursor, stream, iterator hoặc race condition khi tải tăng.
4. **Restart được:** dừng Job giữa chừng, khởi động lại cùng JobInstance và xác nhận checkpoint không làm mất hoặc xử lý trùng dữ liệu.
5. **Thứ tự được hiểu rõ:** nếu thứ tự quan trọng, xác nhận kết quả ghi tuân thủ quy tắc thứ tự cần thiết.
6. **Tài nguyên được đóng đúng:** reader, stream và connection được đóng sau khi Step kết thúc hoặc thất bại.

Nên dùng dữ liệu thử có khóa duy nhất và đủ lớn để các thread thực sự chạy chồng lấn. Kiểm tra cả trường hợp lỗi giữa chừng, vì race condition hoặc checkpoint không chính xác có thể chỉ lộ ra khi có rollback và restart.

## 10. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Item bị trùng hoặc mất | Nhiều thread cùng thay đổi cursor/index không có đồng bộ. | Dùng reader thread-safe, synchronized wrapper hoặc partitioning. |
| Chỉ thêm `@StepScope` nhưng race condition vẫn còn | Nhiều thread vẫn dùng chung reader trong cùng StepExecution. | Phân biệt scope theo StepExecution với thread safety; cô lập reader theo partition hoặc đồng bộ read. |
| Tốc độ không tăng khi dùng synchronized reader | Các thread phải chờ lock để đọc tuần tự. | Đánh giá partitioning hoặc giữ reader tuần tự và chỉ chạy processor bất đồng bộ. |
| Job không restart an toàn | Checkpoint và thứ tự commit không tương thích với cách nhiều thread đọc/ghi. | Kiểm tra `ExecutionContext`, khả năng restart của delegate và thứ tự xử lý; cân nhắc partitioning. |
| Reader an toàn nhưng writer vẫn lỗi | Writer hoặc dependency dùng chung không thread-safe. | Đánh giá toàn bộ pipeline, không chỉ reader. |
| Kết quả đầu ra sai thứ tự | Chunk hoặc processor hoàn thành theo thứ tự khác thứ tự đọc. | Dùng partition key, sequence number hoặc cơ chế sắp xếp nếu nghiệp vụ yêu cầu. |

## Kết luận

Thread safety của `ItemReader` quan trọng khi Spring Batch xử lý chunk trên nhiều thread vì nhiều lời gọi `read()` có thể cùng thay đổi trạng thái nội bộ của reader. Reader không thread-safe có thể làm mất, lặp hoặc đảo thứ tự item. Có thể đồng bộ `read()` bằng `SynchronizedItemStreamReader`, chia dữ liệu bằng partitioning để mỗi worker có reader riêng, hoặc giữ reader tuần tự và chạy processor bất đồng bộ. `@StepScope` tạo bean theo StepExecution nhưng không tự tạo instance riêng cho từng thread trong cùng Step. Khi chọn giải pháp, cần xem xét cả hiệu năng, transaction, checkpoint, restartability và thread safety của processor, writer cùng các dependency được chia sẻ.
