# Reader lỗi giữa chừng trong Spring Batch

Trong chunk-oriented processing, `ItemReader` cung cấp từng item cho step. Reader có thể đọc từ file, database, message queue, API hoặc một nguồn dữ liệu tùy chỉnh. Trong lúc đọc, nguồn có thể gặp lỗi: một dòng file sai định dạng, kết nối database bị mất, API timeout hoặc dữ liệu không thể giải mã. Khi lỗi xảy ra giữa chừng, Spring Batch phải quyết định có thể thử lại thao tác đọc, bỏ qua bản ghi lỗi hay dừng step.

Điều quan trọng là phân biệt **lỗi đọc** với **kết thúc input**. `ItemReader.read()` trả về `null` có nghĩa là không còn item; ném exception có nghĩa thao tác đọc gặp lỗi. Nếu biến một lỗi thành `null`, job có thể kết thúc thành công dù dữ liệu phía sau chưa được đọc hết.

## 1. Hợp đồng của ItemReader và lỗi giữa chừng

Hợp đồng cơ bản của `ItemReader<T>` rất đơn giản:

- Trả về một item khi đọc được dữ liệu tiếp theo.
- Trả về `null` khi nguồn đã hết dữ liệu.
- Ném exception khi không thể hoàn tất thao tác đọc.

Ví dụ một reader đọc đơn hàng từ nguồn dữ liệu:

```java
public class OrderReader implements ItemReader<Order> {

    private final Iterator<Order> orders;

    public OrderReader(List<Order> source) {
        this.orders = source.iterator();
    }

    @Override
    public Order read() {
        if (!orders.hasNext()) {
            return null; // EOF: không còn item
        }
        return orders.next();
    }
}
```

Với reader thực tế, lỗi có thể xuất hiện sau khi đã đọc thành công một số item. Ví dụ, file có 1.000 dòng nhưng dòng 501 không đúng định dạng. Reader đã cung cấp các dòng trước đó, sau đó ném `FlatFileParseException` khi phân tích dòng lỗi.

```text
Dòng 1..500     -> đọc thành công
Dòng 501        -> lỗi parse
Dòng 502..1000  -> chưa được đọc
```

Spring Batch không thể tự suy luận lỗi đó là dữ liệu xấu có thể bỏ qua hay lỗi hạ tầng cần dừng. Ứng dụng phải cấu hình chính sách phù hợp với loại exception và yêu cầu nghiệp vụ.

## 2. Phân biệt lỗi đọc, EOF và dữ liệu không hợp lệ

Ba tình huống sau có ý nghĩa khác nhau:

| Tình huống | Hành vi của reader | Ý nghĩa |
| --- | --- | --- |
| Hết dữ liệu | Trả về `null` | Kết thúc input bình thường. |
| Đọc được item | Trả về object | Chuyển item sang processor nếu có cấu hình. |
| Không thể đọc hoặc phân tích | Ném exception | Có lỗi cần được retry, skip hoặc làm step thất bại. |

Ví dụ với file CSV:

- File đã đọc đến cuối: reader trả về `null`.
- Một dòng có đủ cột và đúng định dạng: reader trả về object `Order`.
- Một dòng thiếu cột bắt buộc hoặc chứa giá trị không thể chuyển đổi: reader có thể ném `FlatFileParseException`.
- File không thể mở do quyền truy cập hoặc đường dẫn sai: reader có thể ném exception về I/O. Đây thường là lỗi cấu hình hoặc môi trường, không nên tự động xem như một dòng dữ liệu có thể bỏ qua.

Không nên viết reader kiểu `catch (Exception e) { return null; }`. Cách đó biến lỗi giữa nguồn thành tín hiệu EOF, khiến các item còn lại bị bỏ qua và step có thể được đánh dấu hoàn tất. Hãy để exception được truyền ra hoặc chuyển đổi sang exception có ý nghĩa để chính sách fault tolerance xử lý.

## 3. Các loại lỗi thường gặp khi đọc

### Lỗi định dạng dữ liệu

Nguồn có thể chứa một bản ghi sai cấu trúc, thiếu trường, sai kiểu dữ liệu hoặc không thỏa quy tắc parse. Với file reader, Spring Batch có thể cung cấp thông tin như dòng lỗi thông qua `FlatFileParseException`. Đây thường là ứng viên cho skip nếu nghiệp vụ cho phép tiếp tục mà không xử lý bản ghi đó.

### Lỗi kết nối tạm thời

Database connection reset, socket timeout hoặc dịch vụ từ xa tạm thời không phản hồi có thể là lỗi nhất thời. Nếu thao tác có thể được thực hiện lại an toàn, retry có thể phù hợp hơn skip. Bỏ qua lỗi kết nối có thể khiến một đoạn dữ liệu lớn không được đọc mà job vẫn chạy tiếp.

### Lỗi xác thực hoặc cấu hình

Credential hết hạn, quyền truy cập bị thu hồi, tên file sai hoặc schema không tồn tại thường không được giải quyết bằng việc thử lại liên tục hay bỏ qua một bản ghi. Đây thường là lỗi cần dừng job để sửa cấu hình hoặc quyền truy cập.

### Lỗi dữ liệu hoặc trạng thái nguồn

Một reader tùy chỉnh có thể gặp dữ liệu bị hỏng, cursor không còn hợp lệ, token phân trang hết hạn hoặc nguồn thay đổi trong khi đọc. Cần xác định lỗi thuộc một item riêng lẻ hay làm mất khả năng tiếp tục duyệt nguồn.

## 4. Chọn giữa retry, skip và fail

Spring Batch cung cấp fault-tolerant chunk step để xử lý các lỗi có thể phục hồi. Quyết định thường dựa trên bản chất của lỗi:

| Chiến lược | Dùng khi | Kết quả mong muốn |
| --- | --- | --- |
| Retry | Lỗi tạm thời và thao tác đọc có thể thử lại an toàn. | Thử lại thao tác theo giới hạn cấu hình. |
| Skip | Một bản ghi cụ thể không hợp lệ, có thể loại khỏi lần xử lý này theo quy tắc nghiệp vụ. | Bỏ qua item lỗi và tiếp tục đọc các item tiếp theo. |
| Fail | Lỗi hạ tầng, cấu hình hoặc dữ liệu khiến tiếp tục có thể làm sai kết quả. | Dừng step/job để xử lý nguyên nhân. |

Ví dụ:

- Một dòng CSV sai định dạng nhưng các dòng khác vẫn độc lập: có thể skip nếu nghiệp vụ chấp nhận.
- Một API tạm thời trả về timeout nhưng có thể gọi lại cùng cursor/token: có thể retry.
- Không thể xác thực với database hoặc không đọc được file đầu vào bắt buộc: thường nên fail.

Không nên cấu hình `skip(Exception.class)` một cách rộng rãi. Exception quá rộng có thể khiến lỗi kết nối, lỗi lập trình hoặc lỗi dữ liệu nghiêm trọng bị bỏ qua. Hãy phân loại exception cụ thể và chỉ skip những trường hợp mà ứng dụng có thể chứng minh là an toàn để bỏ qua.

## 5. Cấu hình skip cho lỗi đọc

Với chunk step, có thể bật fault tolerance và khai báo exception được phép skip:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> orderReader,
                      ItemProcessor<Order, Order> orderProcessor,
                      ItemWriter<Order> orderWriter) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
```

Trong ví dụ này, step cho phép bỏ qua tối đa số lỗi theo `skipLimit` được cấu hình, với `FlatFileParseException` là loại exception có thể skip. Nếu vượt quá giới hạn, step thất bại. Giới hạn skip được tính chung cho lỗi đọc, xử lý và ghi trong step, không phải một hạn mức độc lập cho từng phase.

Khi reader gặp một dòng parse lỗi, Spring Batch có thể áp dụng skip policy, ghi nhận read skip và tiếp tục với dữ liệu tiếp theo nếu reader có thể tiếp tục an toàn. Với `FlatFileItemReader`, exception parse thường mang thông tin dòng và nội dung lỗi, giúp log hoặc ghi nhận bản ghi cần xử lý lại.

Skip chỉ nên dùng khi item lỗi có thể được loại bỏ mà không phá vỡ tính đúng đắn của toàn bộ lô. Nếu một bản ghi sai khiến các bản ghi sau không thể diễn giải đúng, hoặc dữ liệu đầu vào bị lệch cấu trúc từ một vị trí trở đi, fail có thể là lựa chọn phù hợp hơn.

## 6. Cấu hình retry cho lỗi đọc tạm thời

Với lỗi có khả năng tự hết sau một khoảng thời gian, có thể cấu hình retry:

```java
@Bean
Step readRemoteOrdersStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager,
                          ItemReader<Order> remoteOrderReader,
                          ItemWriter<Order> orderWriter) {
    return new StepBuilder("readRemoteOrdersStep", jobRepository)
        .<Order, Order>chunk(50, transactionManager)
        .reader(remoteOrderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Ở đây, `TransientDataAccessException` đại diện cho nhóm lỗi truy cập dữ liệu có thể tạm thời. `retryLimit` giới hạn số lần thử theo chính sách của Spring Batch. Khi không thể phục hồi trong giới hạn đó và không có chính sách skip phù hợp, step sẽ thất bại.

Retry chỉ có ích nếu lần gọi lại có cơ hội thành công và không gây tác dụng phụ không mong muốn. Reader cần được thiết kế để một lần đọc thất bại không làm mất hoặc nhảy qua item một cách âm thầm. Với API phân trang, cần biết token trang hiện tại có được giữ nguyên sau timeout hay không. Với cursor, cần biết kết nối và vị trí đọc có thể phục hồi ra sao.

Có thể kết hợp retry và skip, nhưng cần hiểu thứ tự cũng như tương tác của retry policy, skip policy và rollback. Một lỗi nhất thời có thể được retry; nếu sau đó vẫn lỗi, chỉ được skip khi loại exception đó cũng được cho phép và việc bỏ qua phù hợp nghiệp vụ. Không dùng skip như phương án dự phòng cho mọi lỗi retry đã cạn lượt.

## 7. Không phải lỗi đọc nào cũng có thể skip

Một exception xảy ra trong `read()` không phải lúc nào cũng đại diện cho một item riêng biệt. Ví dụ:

- `FlatFileParseException` có thể xác định một dòng cụ thể bị lỗi.
- Lỗi chuyển đổi một trường có thể chỉ ảnh hưởng đến một bản ghi.
- Lỗi mất kết nối database có thể khiến reader không biết cursor đang ở vị trí nào.
- Lỗi xác thực hoặc schema có thể khiến toàn bộ nguồn không thể đọc.

Với lỗi theo bản ghi, skip có thể tiếp tục từ item kế tiếp nếu reader hỗ trợ điều đó. Với lỗi nguồn hoặc kết nối, việc skip có thể không có ý nghĩa vì reader không thể xác định bản ghi tiếp theo. Nếu không chắc reader còn ở vị trí hợp lệ, hãy fail và phục hồi nguồn thay vì giả định có thể bỏ qua.

Khi cần kiểm soát theo điều kiện phức tạp, có thể cung cấp `SkipPolicy` riêng thay vì chỉ khai báo một lớp exception. Chính sách nên giới hạn loại lỗi, giới hạn số lần bỏ qua và ghi nhận lý do để người vận hành biết dữ liệu nào không được xử lý.

## 8. Theo dõi lỗi bằng ItemReadListener

`ItemReadListener<T>` cung cấp callback để quan sát quá trình đọc:

- `beforeRead()` chạy trước một lần gọi reader.
- `afterRead(T item)` chạy sau khi đọc được item.
- `onReadError(Exception ex)` chạy khi reader ném exception.

Ví dụ ghi log khi reader gặp lỗi:

```java
public class OrderReadListener implements ItemReadListener<Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        // Có thể ghi nhận metric hoặc trace trước thao tác đọc.
    }

    @Override
    public void afterRead(Order item) {
        // Không ghi toàn bộ dữ liệu nhạy cảm của item vào log.
    }

    @Override
    public void onReadError(Exception ex) {
        log.warn("Cannot read the next order", ex);
    }
}
```

Đăng ký listener với step:

```java
.listener(new OrderReadListener())
```

Listener giúp quan sát lỗi, nhưng không tự quyết định retry hay skip. Chính sách fault tolerance mới quyết định cách framework xử lý exception. Tránh thực hiện thao tác nghiệp vụ không idempotent trong `onReadError()`, vì callback có thể được gọi lại khi thao tác đọc được retry.

## 9. Ghi nhận bản ghi bị bỏ qua bằng SkipListener

Khi một lỗi đọc được chấp nhận skip, `SkipListener` có callback `onSkipInRead(Throwable t)`. Khác với skip trong processor hoặc writer, callback đọc không nhận item đầu vào vì reader đã không tạo được item hợp lệ.

```java
public class OrderSkipListener implements SkipListener<Order, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable t) {
        log.error("An input record was skipped", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.error("Order {} was skipped during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        log.error("Order {} was skipped during writing", item.getId(), t);
    }
}
```

Đăng ký listener:

```java
.listener(new OrderSkipListener())
```

Với read skip, exception có thể chứa thông tin dòng hoặc bản ghi lỗi, tùy reader. Nếu cần lưu dữ liệu lỗi vào bảng quarantine, hãy trích xuất thông tin an toàn từ exception và thực hiện trong một cơ chế có transaction, idempotency và khả năng retry phù hợp. `SkipListener` được gọi khi framework xác định item bị skip; tránh giả định exception luôn chứa toàn bộ nội dung đầu vào.

Spring Batch thiết kế callback skip để thông báo item bị bỏ qua đúng một lần trong phạm vi xử lý skip của chunk. Khi ghi dữ liệu lỗi vào hệ thống ngoài transaction, vẫn cần chống ghi trùng và xử lý trường hợp transaction chunk rollback.

## 10. Reader lỗi giữa chunk ảnh hưởng đến transaction như thế nào?

Chunk-oriented processing quản lý một nhóm item trong ranh giới transaction. Nếu reader ném exception và exception không được xử lý bằng retry hoặc skip, chunk hiện tại không thể hoàn tất như một chunk thành công; transaction sẽ được xử lý theo rollback behavior của step.

Ví dụ với commit interval 100:

```text
Đọc item 1..60
       |
       v
Reader gặp exception ở lần đọc tiếp theo
       |
       +---- Nếu lỗi được retry và đọc lại thành công
       |          -> tiếp tục gom chunk
       |
       +---- Nếu lỗi được skip và reader tiếp tục được
       |          -> ghi nhận read skip, tiếp tục xử lý
       |
       +---- Nếu lỗi không retry/skip được
                  -> rollback theo transaction
                  -> step/job thất bại
```

Khi rollback, các thay đổi transactional trong chunk chưa commit được hoàn tác. Những chunk trước đã commit vẫn còn hiệu lực. Vì vậy, lỗi giữa chừng thường không có nghĩa toàn bộ job quay về trạng thái ban đầu; nó thường dừng tại ranh giới commit gần nhất.

Nếu reader đọc từ tài nguyên không tham gia transaction của database đích, rollback database không tự đưa reader về đúng vị trí trước khi đọc. Framework có cơ chế buffering và các reader có trạng thái riêng, nhưng reader tùy chỉnh vẫn phải bảo đảm hành vi đọc có thể phục hồi. Không nên giả định mọi nguồn file, API hay queue tự động rollback cùng transaction database.

## 11. Restart sau khi reader gặp lỗi

Khi job thất bại và được restart, Spring Batch dùng metadata trong `JobRepository` cùng `ExecutionContext` để xác định tiến độ đã commit. Các reader hỗ trợ restart thường triển khai `ItemStream`:

- `open(ExecutionContext)` khôi phục trạng thái trước đó hoặc khởi tạo reader.
- `update(ExecutionContext)` ghi trạng thái hiện tại để lưu checkpoint.
- `close()` giải phóng tài nguyên.

Với `FlatFileItemReader`, trạng thái đọc có thể được lưu để khi restart reader tiếp tục từ vị trí phù hợp. Nên đặt tên reader ổn định và bật lưu state nếu cần restart. Nhiều reader có sẵn hỗ trợ cơ chế này; reader tùy chỉnh phải tự triển khai checkpoint đúng cách.

Checkpoint thường được lưu tại ranh giới commit. Nếu lỗi xảy ra trước khi chunk hiện tại commit, lần restart thường dựa trên checkpoint của chunk trước. Điều đó có nghĩa một số item đã được đọc trong lần chạy trước có thể được đọc lại. Writer và thao tác nghiệp vụ nên có cơ chế idempotency hoặc khóa duy nhất khi việc chạy lại có thể tạo tác dụng phụ trùng lặp.

Một reader không lưu trạng thái có thể bắt đầu lại từ đầu hoặc không thể khôi phục chính xác vị trí đọc. Không nên bật restart cho một reader tùy chỉnh nếu chưa xác định rõ cách nó khôi phục vị trí và xử lý các item đã đọc nhưng chưa commit.

## 12. Reader tùy chỉnh cần thiết kế thế nào để phục hồi an toàn?

Một reader tùy chỉnh nên có ranh giới rõ giữa lấy item, xác nhận item đã được tiêu thụ và lưu checkpoint. Nếu nguồn là API phân trang, cần lưu token hoặc khóa trang phù hợp. Nếu nguồn là bảng database, có thể dùng khóa tăng dần hoặc truy vấn theo cửa sổ ổn định. Nếu nguồn là file, có thể lưu vị trí đọc hoặc dùng reader có sẵn.

Các nguyên tắc quan trọng:

- Không cập nhật checkpoint bền vững trước khi chunk chứa item đó được commit.
- Có khả năng khôi phục từ checkpoint cuối đã commit.
- Không biến lỗi tạm thời thành EOF.
- Nếu một lần đọc thất bại sau khi nguồn đã tiêu thụ item, phải có cách xác định item đó có thể được đọc lại hay đã mất.
- Dùng nguồn có thứ tự ổn định hoặc khóa phân trang ổn định để tránh bỏ sót/đọc trùng khi dữ liệu thay đổi.
- Nếu retry cùng một request, bảo đảm request không làm mất cursor hoặc thay đổi trạng thái nguồn ngoài dự kiến.

Với reader dựa trên API, ví dụ, không nên chỉ tăng page number trong bộ nhớ trước khi xác nhận toàn bộ chunk được commit. Cần thiết kế checkpoint sao cho restart dùng lại page hoặc continuation token cuối cùng đã commit, đồng thời writer chịu được việc xử lý lại nếu có rollback.

## 13. Ví dụ cấu hình file reader có thể restart

`FlatFileItemReader` là reader có sẵn phù hợp cho file dạng dòng. Ví dụ sau minh họa cấu hình tên reader và lưu trạng thái:

```java
@Bean
FlatFileItemReader<Order> orderFileReader(Resource inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
        .name("orderFileReader")
        .resource(inputFile)
        .delimited()
        .names("id", "customerId", "amount")
        .fieldSetMapper(fieldSet -> new Order(
            fieldSet.readString("id"),
            fieldSet.readString("customerId"),
            fieldSet.readBigDecimal("amount")
        ))
        .saveState(true)
        .build();
}
```

Reader này có thể cung cấp thông tin lỗi parse như `FlatFileParseException`, và state của nó được lưu để hỗ trợ restart. Cần bảo đảm file đầu vào vẫn là cùng một nội dung khi restart. Nếu file bị thay thế hoặc chỉnh sửa giữa hai lần chạy, vị trí dòng được khôi phục có thể trỏ đến nội dung khác.

Có thể cấu hình skip lỗi parse như phần trước, đồng thời gắn listener để ghi nhận lỗi. Với file bắt buộc phải đầy đủ, cần cân nhắc fail thay vì skip nếu số lỗi vượt ngưỡng hoặc dữ liệu sai cấu trúc làm cho các dòng sau không đáng tin cậy.

## 14. Kiểm thử reader lỗi giữa chừng

Nên kiểm thử ít nhất các tình huống sau:

1. Reader đọc thành công một số item rồi ném exception không được skip: step phải thất bại.
2. Reader gặp exception được cấu hình skip: step tiếp tục và read skip count tăng.
3. Reader gặp exception tạm thời được retry: thao tác đọc được thử lại theo giới hạn cấu hình.
4. Reader lỗi sau một hoặc nhiều chunk đã commit: restart tiếp tục từ checkpoint đúng.
5. Reader trả về `null`: step kết thúc bình thường, không tăng read skip count.
6. Reader không thể tiếp tục sau lỗi nguồn: step thất bại thay vì âm thầm bỏ qua phần còn lại.

Một reader giả lập có thể ném lỗi tại một vị trí xác định để test tái hiện ổn định:

```java
public class FailingOnceReader implements ItemReader<Integer> {

    private int next = 1;
    private boolean failed;

    @Override
    public Integer read() {
        if (next == 4 && !failed) {
            failed = true;
            throw new IllegalStateException("Simulated read failure");
        }
        if (next > 6) {
            return null;
        }
        return next++;
    }
}
```

Reader này phù hợp để minh họa một lỗi nhất thời trong cùng một instance reader. Trong test retry, cấu hình retry cho `IllegalStateException` và xác nhận reader tiếp tục cung cấp dữ liệu. Với test restart thực sự, trạng thái `failed` và `next` trong ví dụ này chưa được lưu bền vững; cần một reader triển khai `ItemStream` hoặc một reader test được tạo lại từ checkpoint để kiểm tra restart qua execution khác.

Khi dùng `JobLauncherTestUtils`, có thể khởi chạy job test và kiểm tra `JobExecution`, `StepExecution`, `readCount`, `readSkipCount`, `commitCount`, `rollbackCount` và trạng thái cuối. Nếu kiểm thử skip, xác nhận `SkipListener.onSkipInRead()` được gọi và bản ghi lỗi được ghi nhận đúng một lần theo thiết kế.

## 15. Những lỗi thường gặp khi xử lý reader giữa chừng

**Nuốt exception rồi trả về null:** step hiểu đây là EOF và có thể kết thúc thành công dù nguồn còn dữ liệu. Hãy truyền exception ra hoặc phân loại lỗi một cách rõ ràng.

**Skip lỗi kết nối:** bỏ qua exception kết nối có thể khiến cả phần dữ liệu còn lại không được đọc. Chỉ skip lỗi gắn với bản ghi cụ thể và có thể tiếp tục an toàn.

**Retry một thao tác không an toàn:** nếu reader đã tiêu thụ item trước khi ném exception, lần retry có thể đọc item tiếp theo hoặc gây trùng lặp. Hãy thiết kế reader để giữ hoặc khôi phục vị trí đọc.

**Đặt skip limit quá cao:** giới hạn lớn có thể che giấu dữ liệu đầu vào hỏng trên diện rộng. Chọn ngưỡng dựa trên yêu cầu nghiệp vụ và giám sát số lượng skip.

**Không lưu state của reader:** job có thể không biết phải tiếp tục từ đâu sau restart. Dùng reader hỗ trợ `ItemStream` hoặc tự triển khai checkpoint phù hợp.

**File nguồn thay đổi giữa các lần chạy:** checkpoint có thể không còn tương ứng với nội dung file. Lưu trữ file bất biến hoặc kiểm tra checksum/định danh nguồn trước khi restart.

**Không phân biệt lỗi đọc với lỗi processor:** lỗi trong `read()` có `readSkipCount`; lỗi trong `process()` có `processSkipCount`. Dùng listener và bộ đếm đúng phase để điều tra.

**Không kiểm tra dữ liệu đã commit:** restart có thể đọc lại một phần item. Đối chiếu hệ thống đích và thiết kế writer idempotent để tránh ghi trùng.

## 16. Cách lựa chọn chiến lược xử lý trong production

Khi triển khai reader, trước tiên hãy phân loại các lỗi có thể phát sinh. Lỗi dữ liệu riêng lẻ có thể skip nếu nghiệp vụ cho phép; lỗi hạ tầng tạm thời có thể retry nếu thao tác đọc có thể thực hiện lại an toàn; lỗi cấu hình, xác thực hoặc mất khả năng xác định vị trí đọc thường nên làm step thất bại.

Tiếp theo, cấu hình `skip`, `skipLimit`, `retry` và `retryLimit` có chủ đích. Gắn `ItemReadListener` để quan sát lỗi đọc và `SkipListener` để ghi nhận các bản ghi thực sự bị bỏ qua. Theo dõi số lần retry, read skip, rollback và trạng thái job để phát hiện nguồn dữ liệu đang xuống cấp.

Cuối cùng, thiết kế reader có khả năng phục hồi từ checkpoint cuối đã commit. Kiểm thử lỗi giữa chunk, restart và tình huống dữ liệu nguồn thay đổi. Đối với hệ thống bên ngoài transaction database, bảo đảm writer có idempotency hoặc quy trình đối soát để việc xử lý lại không làm sai dữ liệu.

Reader lỗi giữa chừng là một tình huống vận hành bình thường cần được dự liệu trong batch processing. Khi phân biệt đúng EOF với exception, lựa chọn retry/skip/fail theo bản chất lỗi và lưu trạng thái đọc có thể phục hồi, job Spring Batch có thể xử lý dữ liệu lỗi có kiểm soát mà vẫn bảo vệ tính đầy đủ và nhất quán của kết quả.
