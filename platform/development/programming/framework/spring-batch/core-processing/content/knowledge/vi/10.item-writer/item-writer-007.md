# Writer flush và close resource

Trong Spring Batch, **ItemWriter** ghi các item đã được reader đọc và processor xử lý. Với writer làm việc trên file, socket, stream hoặc tài nguyên bên ngoài, việc quản lý bộ đệm và đóng tài nguyên là một phần của vòng đời Step.

Hai thao tác thường bị nhầm lẫn là **flush** và **close**:

- **Flush** đẩy dữ liệu đang nằm trong bộ đệm của ứng dụng xuống lớp ghi bên dưới. Dữ liệu có thể đã được chuyển tới hệ điều hành nhưng chưa chắc đã được ghi vật lý bền vững xuống thiết bị lưu trữ.
- **Close** hoàn tất việc ghi, thường flush phần dữ liệu còn lại rồi giải phóng tài nguyên như file handle, stream hoặc connection mà writer sở hữu.

Trong Spring Batch, writer có trạng thái thường tham gia vòng đời **ItemStream**: mở tài nguyên khi Step bắt đầu, ghi qua nhiều chunk, cập nhật trạng thái tại checkpoint và đóng tài nguyên khi Step kết thúc. Cần hiểu vòng đời này để tránh đóng writer quá sớm, làm mất dữ liệu trong buffer, rò rỉ file handle hoặc tạo output không nhất quán khi Job bị lỗi và restart.

## 1. ItemWriter và ItemStream

Hợp đồng cơ bản của ItemWriter tập trung vào việc ghi một chunk:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

ItemWriter không định nghĩa trực tiếp các phương thức flush() hay close(). Một writer cần quản lý trạng thái hoặc tài nguyên thường triển khai thêm **ItemStream**.

ItemStream cung cấp ba phương thức vòng đời:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Trong API thực tế, các phương thức vòng đời có thể khai báo ItemStreamException. Interface kết hợp cả hai hợp đồng thường được gọi là **ItemStreamWriter**:

~~~java
public interface ItemStreamWriter<T>
        extends ItemStream, ItemWriter<T> {
}
~~~

Ý nghĩa của từng phương thức:

| Phương thức | Vai trò |
|---|---|
| open(ExecutionContext) | Mở tài nguyên và khôi phục trạng thái nếu đây là lần restart |
| write(Chunk) | Ghi các item của chunk hiện tại |
| update(ExecutionContext) | Lưu trạng thái cần thiết để tiếp tục ở checkpoint |
| close() | Flush phần còn lại và giải phóng tài nguyên |

Ví dụ, một writer ghi file cần mở file trước khi nhận chunk đầu tiên, ghi dữ liệu trong nhiều lần gọi write(), rồi đóng file khi Step kết thúc.

## 2. Vòng đời writer trong một Step

Spring Batch quản lý các ItemStream được đăng ký với Step. Ở mức khái niệm, vòng đời của một writer như sau:

~~~text
Job bắt đầu Step
       |
       v
writer.open(executionContext)
       |
       v
   Chunk 1
       |
       +--> writer.write(chunk)
       |
       +--> writer.update(executionContext)
       |
       +--> transaction commit
       |
       v
   Chunk 2
       |
       +--> writer.write(chunk)
       |
       +--> writer.update(executionContext)
       |
       +--> transaction commit
       |
       v
  ... các chunk tiếp theo ...
       |
       v
writer.close()
       |
       v
Step kết thúc
~~~

Một số điểm quan trọng:

- open() được gọi khi Step mở các stream trước khi xử lý dữ liệu.
- write() có thể được gọi nhiều lần, thường một lần cho mỗi chunk được ghi.
- update() lưu trạng thái của stream tại checkpoint để hỗ trợ restart.
- close() được gọi khi Step kết thúc hoặc đi qua đường dọn dẹp sau lỗi.

Writer không nên tự đóng tài nguyên sau mỗi lần write(). Step có thể cần writer cho chunk tiếp theo. Việc đóng sớm khiến lần ghi kế tiếp gặp lỗi như stream đã đóng hoặc file handle không còn hợp lệ.

Cũng không nên giả định close() luôn chạy trong mọi tình huống. Nếu tiến trình bị kill cưỡng bức, máy chủ mất điện hoặc JVM crash, code dọn dẹp trong ứng dụng có thể không được thực thi. Cần dựa vào cơ chế lưu trữ và khả năng phục hồi của hệ điều hành, đồng thời thiết kế Job để có thể kiểm tra và xử lý output chưa hoàn chỉnh.

## 3. Flush khác commit transaction như thế nào?

Flush và commit có liên quan nhưng không đồng nghĩa.

**Flush** là thao tác của tầng ghi dữ liệu. Nó đẩy dữ liệu khỏi buffer của ứng dụng tới stream hoặc hệ điều hành bên dưới.

**Commit** là thao tác của transaction manager, xác nhận các thay đổi thuộc transaction đã hoàn tất. Với database, commit làm cho các thay đổi transaction trở thành dữ liệu đã được xác nhận theo cơ chế của database.

Có thể hình dung:

~~~text
Ứng dụng ghi dữ liệu
       |
       v
Buffer trong writer
       |
       | flush()
       v
Stream / hệ điều hành
       |
       | commit transaction (nếu tài nguyên tham gia transaction)
       v
Trạng thái được xác nhận
~~~

Một lời gọi flush() không tự commit database transaction. Ngược lại, commit database cũng không có nghĩa mọi file hoặc HTTP request được gọi trong cùng chunk đã được commit theo cùng một cơ chế.

Ngay cả khi flush file thành công, dữ liệu vẫn có thể nằm trong cache của hệ điều hành. Nếu yêu cầu cần đồng bộ dữ liệu file xuống thiết bị lưu trữ, cần cơ chế như forceSync hoặc FileChannel.force tùy loại writer và mức bảo đảm mong muốn.

Vì vậy, khi nói “writer đã flush”, chỉ có thể kết luận buffer ở tầng writer đã được đẩy xuống tầng thấp hơn theo hợp đồng của stream. Không nên suy ra ngay rằng toàn bộ Job đã commit hoặc dữ liệu đã bền vững vật lý.

## 4. Khi nào cần flush?

Flush thường cần thiết khi:

- Writer giữ dữ liệu trong buffer để giảm số lần ghi hệ thống.
- Ứng dụng cần output có thể được đọc sớm bởi một tiến trình khác.
- Writer cần đẩy dữ liệu còn lại trước khi đóng tài nguyên.
- Cần đồng bộ dữ liệu tại một ranh giới do ứng dụng kiểm soát.

Tuy nhiên, flush quá thường xuyên có thể làm giảm hiệu năng vì tăng số lần ghi xuống stream hoặc hệ điều hành.

Với writer do Spring Batch quản lý, hãy để writer thực hiện flush theo cơ chế và cấu hình của nó. Không nên tìm cách truy cập buffer nội bộ hoặc gọi flush tùy tiện sau mỗi item nếu writer không cung cấp API phù hợp.

Đối với file writer dựng sẵn, Spring Batch có cơ chế buffer và phối hợp với transaction. Hãy cấu hình writer thay vì tự lấy stream nội bộ để flush.

## 5. FlatFileItemWriter quản lý flush và close

**FlatFileItemWriter** là writer dựng sẵn để ghi dữ liệu thành các dòng trong file. Nó quản lý việc mở file, ghi các chunk, lưu trạng thái và đóng tài nguyên theo vòng đời ItemStream.

Ví dụ cấu hình với Spring Batch 5:

~~~java
@Bean
public FlatFileItemWriter<Customer> customerFileWriter(
        Resource outputResource,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileWriter")
            .resource(outputResource)
            .lineAggregator(customerLineAggregator)
            .encoding("UTF-8")
            .saveState(true)
            .transactional(true)
            .forceSync(false)
            .build();
}
~~~

Các cấu hình đáng chú ý:

| Cấu hình | Ý nghĩa |
|---|---|
| name(...) | Tên ổn định để nhận diện trạng thái writer trong ExecutionContext |
| resource(...) | Tài nguyên file đầu ra |
| lineAggregator(...) | Chuyển một item thành một dòng |
| encoding(...) | Encoding của file |
| saveState(true) | Cho phép lưu trạng thái writer để restart |
| transactional(true) | Dùng cơ chế buffer giao dịch của writer để phối hợp với rollback |
| forceSync(false) | Không yêu cầu đồng bộ file descriptor xuống thiết bị sau mỗi lần ghi |

Các giá trị trên là ví dụ cấu hình. Hãy chọn forceSync, transactional và saveState theo yêu cầu đầu ra, phiên bản Spring Batch và loại resource thực tế.

### Writer ghi theo dòng

LineAggregator chuyển item thành chuỗi. Ví dụ có thể dùng một aggregator riêng để định dạng Customer thành dòng CSV:

~~~java
public class CustomerLineAggregator
        implements LineAggregator<Customer> {

    @Override
    public String aggregate(Customer customer) {
        return customer.id() + "," +
                customer.name() + "," +
                customer.email();
    }
}
~~~

Ví dụ này chỉ minh họa việc ánh xạ trường thành dòng. Nếu dữ liệu có dấu phẩy, dấu nháy kép hoặc ký tự xuống dòng trong trường, cần dùng bộ serialize CSV có quy tắc escaping đúng. Nối chuỗi đơn giản không đủ để tạo CSV an toàn cho mọi input.

Sau khi nhận chunk, FlatFileItemWriter ghi các dòng theo thứ tự. Writer giữ quyền sở hữu tài nguyên file và tự quản lý buffer, flush, close theo vòng đời Step.

## 6. Transactional buffer của FlatFileItemWriter

Một điểm quan trọng của FlatFileItemWriter là cơ chế ghi có thể phối hợp với transaction của chunk. Khi transactional được bật, writer dùng buffer giao dịch để nội dung của chunk được ghi ra file theo trạng thái commit/rollback.

Ở mức khái niệm:

~~~text
Chunk bắt đầu
     |
     v
writer.write(chunk)
     |
     v
Dòng output nằm trong transactional buffer
     |
     +---- Chunk commit
     |          |
     |          v
     |    Đẩy nội dung chunk ra file
     |
     +---- Chunk rollback
                |
                v
          Loại nội dung chưa commit
~~~

Điều này giúp tránh trường hợp writer ghi một phần chunk ra file rồi transaction database rollback nhưng file vẫn giữ các dòng đó, trong phạm vi cơ chế transactional buffer của writer.

Cần phân biệt cơ chế này với một giao dịch phân tán giữa file và database. Nó giúp writer phối hợp việc ghi file với transaction của Step, nhưng không tự biến filesystem thành một database transaction có đầy đủ mọi thuộc tính ACID. Nếu nhiều tài nguyên độc lập tham gia cùng một chunk, vẫn cần xem xét lỗi giữa các tài nguyên và khả năng đối soát.

Nếu cấu hình transactional(false), writer không dùng cùng cơ chế buffer giao dịch. Khi đó, nội dung có thể được ghi ra file trước khi transaction của Step commit. Nếu chunk rollback, các dòng đã ghi trực tiếp có thể vẫn tồn tại. Chỉ dùng chế độ này khi ứng dụng đã có cách xử lý output không hoàn tất hoặc không cần rollback file theo transaction.

## 7. forceSync và độ bền dữ liệu file

Cấu hình **forceSync** điều khiển việc đồng bộ dữ liệu file sau khi ghi. Khi bật, writer yêu cầu đồng bộ nội dung qua file descriptor xuống thiết bị lưu trữ theo cơ chế của nền tảng.

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator)
        .forceSync(true)
        .build();
~~~

forceSync có thể tăng độ bền của dữ liệu khi hệ điều hành hoặc máy chủ gặp sự cố, nhưng thường làm giảm hiệu năng do yêu cầu đồng bộ vật lý tốn chi phí hơn.

Hãy phân biệt ba tầng:

1. **Writer buffer**: dữ liệu còn trong bộ đệm của ứng dụng.
2. **OS buffer/cache**: dữ liệu đã được chuyển cho hệ điều hành.
3. **Thiết bị lưu trữ**: dữ liệu đã được đồng bộ theo cơ chế phần cứng và hệ điều hành.

Flush thường đẩy dữ liệu từ tầng 1 xuống tầng 2. forceSync yêu cầu đồng bộ sâu hơn từ tầng 2. Mức bảo đảm thực tế vẫn phụ thuộc filesystem, thiết bị, cấu hình hệ điều hành và nền tảng chạy.

Không nên bật forceSync chỉ vì muốn “an toàn hơn” mà không đo đạc. Hãy bật khi yêu cầu độ bền đầu ra xứng đáng với chi phí hiệu năng.

## 8. Close resource có trách nhiệm gì?

Khi Step kết thúc, writer cần giải phóng mọi tài nguyên mà nó sở hữu:

- Flush dữ liệu còn lại trong buffer nếu hợp đồng writer yêu cầu.
- Đóng BufferedWriter, OutputStream hoặc file handle.
- Giải phóng cursor hoặc resource được mở trực tiếp.
- Đóng client hoặc session chỉ khi writer sở hữu vòng đời của đối tượng đó.
- Xóa tham chiếu nội bộ để tránh sử dụng nhầm sau khi đóng.

Close nên an toàn khi được gọi trong quá trình dọn dẹp sau lỗi. Nếu writer mở một phần tài nguyên rồi gặp exception, cần giải phóng phần đã mở được.

Một quy tắc quan trọng là **chỉ đóng tài nguyên mà writer sở hữu**. Nếu writer nhận một DataSource, HTTP client singleton hoặc connection pool được Spring quản lý, không được đóng toàn bộ đối tượng dùng chung đó trong close(). Với JDBC, nên dùng JdbcTemplate hoặc cơ chế quản lý connection của Spring thay vì tự giữ connection xuyên suốt vòng đời writer.

## 9. Writer tự viết cần triển khai ItemStream

Nếu writer tự mở file hoặc resource khác, hãy triển khai ItemStreamWriter để Spring Batch quản lý vòng đời.

Ví dụ dưới đây minh họa một writer ghi text bằng BufferedWriter:

~~~java
public class BufferedTextItemWriter
        implements ItemStreamWriter<String> {

    private final Path outputPath;
    private BufferedWriter writer;

    public BufferedTextItemWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        try {
            writer = Files.newBufferedWriter(
                    outputPath,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    StandardOpenOption.WRITE
            );
        } catch (IOException ex) {
            throw new ItemStreamException(
                    "Cannot open output file", ex);
        }
    }

    @Override
    public void write(Chunk<? extends String> chunk)
            throws Exception {

        if (writer == null) {
            throw new IllegalStateException(
                    "Writer has not been opened");
        }

        for (String line : chunk) {
            writer.write(line);
            writer.newLine();
        }
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Ví dụ này không lưu checkpoint riêng.
    }

    @Override
    public void close() {
        if (writer == null) {
            return;
        }

        try {
            writer.close();
        } catch (IOException ex) {
            throw new ItemStreamException(
                    "Cannot close output file", ex);
        } finally {
            writer = null;
        }
    }
}
~~~

Ví dụ này minh họa cách mở tài nguyên trong open(), sử dụng nó trong write() và giải phóng trong close(). close() kiểm tra null để có thể được gọi khi tài nguyên chưa mở hoặc đã được giải phóng.

**Đây là ví dụ quản lý resource, không phải một writer file có rollback và restart hoàn chỉnh.** Writer trên ghi trực tiếp vào file, không lưu vị trí và không có transactional buffer. TRUNCATE_EXISTING cũng sẽ xóa nội dung cũ khi mở file. Nếu Step rollback hoặc Job restart, file có thể chứa dữ liệu không phù hợp với checkpoint. Với output file cần transaction và restart, hãy ưu tiên FlatFileItemWriter hoặc thiết kế cơ chế ghi tạm, checkpoint và publish riêng.

## 10. Không đóng writer trong write()

Một lỗi thường gặp là mở và đóng file ngay trong mỗi lần ghi:

~~~java
@Override
public void write(Chunk<? extends String> chunk) throws Exception {
    try (BufferedWriter writer = Files.newBufferedWriter(outputPath)) {
        for (String line : chunk) {
            writer.write(line);
            writer.newLine();
        }
    }
}
~~~

Đoạn code này đóng writer sau mỗi chunk. Nó có thể gây ra một số vấn đề:

- Nếu không cấu hình APPEND, file có thể bị ghi đè ở mỗi chunk.
- Việc mở/đóng file liên tục làm tăng chi phí I/O.
- Không thể dùng một stream ổn định để quản lý trạng thái và checkpoint.
- Các tùy chọn restart và transactional của Step không được tận dụng đúng cách.

Một writer quản lý tài nguyên theo ItemStream nên mở tài nguyên một lần trong open(), dùng nó qua nhiều lần write() và đóng trong close().

Cũng không nên gọi close() từ processor hoặc listener sau một chunk nếu writer vẫn cần được dùng ở chunk tiếp theo.

## 11. Wrapper và delegate writer phải chuyển tiếp vòng đời

Trong một số cấu hình, writer thực tế được bọc bởi wrapper, decorator hoặc composite writer. Nếu delegate cần open/update/close nhưng wrapper không chuyển tiếp các lời gọi ItemStream, delegate có thể không được khởi tạo hoặc giải phóng đúng cách.

Ví dụ một wrapper triển khai ItemStreamWriter và ủy quyền:

~~~java
public class LoggingItemWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public LoggingItemWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
~~~

Nếu wrapper không triển khai ItemStream, Step có thể chỉ nhận biết wrapper là ItemWriter thông thường. Khi đó, hãy đăng ký delegate như một stream riêng bằng cơ chế stream(...) của Step builder:

~~~java
new StepBuilder("exportCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(loggingWriter)
        .stream(delegateWriter)
        .build();
~~~

Khi dùng composite hoặc decorator có sẵn, hãy kiểm tra xem nó có quản lý stream của delegate tự động hay không. Tránh đăng ký hoặc đóng cùng một stream nhiều lần theo những cách gây xung đột vòng đời.

## 12. append, shouldDeleteIfExists và restart file

Khi ghi file, cần xác định điều gì xảy ra nếu output đã tồn tại.

FlatFileItemWriterBuilder cung cấp các tùy chọn thường gặp:

- **append(true)**: ghi tiếp vào file hiện có.
- **shouldDeleteIfExists(true)**: xóa file hiện có khi bắt đầu một lần ghi mới theo điều kiện của writer.
- **saveState(true)**: lưu trạng thái writer để hỗ trợ restart.

Ví dụ cấu hình ghi một output mới:

~~~java
new FlatFileItemWriterBuilder<Customer>()
        .name("customerFileWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator)
        .append(false)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .transactional(true)
        .build();
~~~

Với một lần restart, writer cần nhận ra trạng thái cũ trong ExecutionContext để tiếp tục đúng file và vị trí đã lưu. Không nên xem restart như một lần chạy mới rồi xóa output đã tạo từ các chunk commit trước đó.

Nếu bật append hoặc thay đổi đường dẫn output giữa lần chạy đầu và restart, có thể dẫn tới dữ liệu bị nối lặp, ghi sai file hoặc không khôi phục được vị trí mong đợi. Hãy giữ resource ổn định cho cùng JobInstance và kiểm tra trạng thái restart trước khi quyết định xóa hoặc nối file.

Một cách an toàn cho báo cáo là ghi vào file tạm theo execution ID, chỉ publish hoặc đổi tên thành file chính sau khi Job hoàn tất thành công. Như vậy, người dùng không đọc nhầm một file đang được tạo dở. Việc publish cần có chính sách xử lý nếu thao tác đổi tên thất bại hoặc Job bị dừng.

## 13. Close và lỗi ghi dữ liệu

Không phải mọi lỗi writer đều xảy ra trong write(). Một số lỗi chỉ xuất hiện khi flush hoặc close, ví dụ:

- Hết dung lượng đĩa.
- Quyền ghi bị thu hồi.
- Thiết bị lưu trữ gặp lỗi.
- File handle bị đóng từ bên ngoài.
- Stream hoặc connection đã mất.
- Lỗi đồng bộ dữ liệu khi forceSync.

Điều này có nghĩa các chunk trước đó có thể đã được xử lý mà Step vẫn thất bại ở giai đoạn đóng writer. Khi điều tra, hãy xem cả lỗi trong write() lẫn lỗi trong close() và log của hệ điều hành.

Không nên bắt rồi bỏ qua IOException trong close(). Nếu không thể hoàn tất việc ghi hoặc giải phóng resource, Step cần được thông báo về lỗi đó để ứng dụng không đánh dấu Job thành công khi output chưa hoàn chỉnh.

Khi cần vừa báo lỗi flush vừa cố gắng đóng resource, hãy giữ lỗi gốc và xử lý lỗi đóng như suppressed exception hoặc ghi log phù hợp. Tránh để một exception cleanup che mất nguyên nhân ghi ban đầu.

## 14. Writer ghi database và việc giải phóng connection

Không phải writer nào cũng cần tự quản lý file hoặc stream. Với JdbcBatchItemWriter, Spring Batch sử dụng hạ tầng JDBC và transaction manager để thực hiện ghi.

Ví dụ:

~~~java
@Bean
public JdbcBatchItemWriter<Customer> customerDatabaseWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO customer (id, name, email)
                VALUES (:id, :name, :email)
                """)
            .beanMapped()
            .build();
}
~~~

Trong trường hợp này:

- Writer không cần tự mở một connection lâu dài trong open().
- Connection được lấy và trả lại theo cơ chế Spring JDBC và transaction hiện hành.
- Không được đóng DataSource hoặc connection pool trong close() của writer.
- Transaction manager chịu trách nhiệm commit/rollback connection tham gia transaction.

Nếu tự viết writer dùng JDBC, hãy dùng JdbcTemplate, NamedParameterJdbcTemplate hoặc DataSourceUtils để tham gia transaction do Spring quản lý. Chỉ tự đóng connection khi chính code đã lấy và sở hữu connection theo đúng cách; không đóng connection đang được transaction manager giữ.

## 15. Kiểm thử flush và close

Vòng đời writer cần được kiểm thử, đặc biệt với writer tự viết hoặc writer bọc delegate.

Các tình huống nên kiểm tra:

| Tình huống | Điều cần xác nhận |
|---|---|
| Mở Step | open() được gọi và resource sẵn sàng |
| Ghi nhiều chunk | write() được gọi nhiều lần trên cùng writer |
| Kết thúc bình thường | close() giải phóng resource và phần buffer còn lại được xử lý |
| Writer gặp lỗi | Step vẫn đi qua quá trình cleanup |
| open() thất bại giữa chừng | Resource đã mở một phần được giải phóng |
| close() được gọi khi chưa mở | Không phát sinh lỗi ngoài ý muốn |
| Wrapper có delegate | open/update/close được chuyển tiếp đúng |
| Restart | Writer khôi phục trạng thái và tiếp tục đúng output |
| Rollback | Dữ liệu chưa commit không xuất hiện ngoài output nếu writer hỗ trợ transactional behavior |

### Kiểm thử writer tự viết bằng Mockito

Có thể dùng writer giả để xác nhận lifecycle được gọi:

~~~java
@Test
void delegatesItemStreamLifecycle() throws Exception {
    @SuppressWarnings("unchecked")
    ItemStreamWriter<String> delegate =
            mock(ItemStreamWriter.class);

    LoggingItemWriter<String> writer =
            new LoggingItemWriter<>(delegate);

    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    writer.write(new Chunk<>(List.of("A", "B")));
    writer.update(context);
    writer.close();

    verify(delegate).open(context);
    verify(delegate).write(any());
    verify(delegate).update(context);
    verify(delegate).close();
}
~~~

Test này xác nhận wrapper chuyển tiếp lời gọi. Để kiểm tra file thực tế, dùng thư mục tạm và đọc nội dung sau khi writer đóng. Với transactional behavior và restart, nên chạy Step integration test với JobRepository và transaction manager phù hợp.

### Kiểm thử lỗi trong close()

Nếu writer tự viết, hãy tạo một resource giả có thể ném IOException khi flush hoặc close. Xác nhận Step nhận được lỗi và không báo COMPLETED giả tạo.

Với writer file thật, các lỗi như disk full khó mô phỏng ổn định trong unit test. Có thể kiểm tra logic xử lý exception bằng abstraction hoặc mock, sau đó có kiểm thử môi trường cho filesystem nếu yêu cầu vận hành cần thiết.

## 16. Những lỗi quản lý resource thường gặp

### Đóng writer sau mỗi chunk

Writer bị đóng quá sớm và không thể tiếp tục nhận chunk. Hãy để Step quản lý vòng đời qua ItemStream.

### Không triển khai ItemStream cho writer có trạng thái

Framework không biết khi nào mở, lưu trạng thái hoặc đóng resource. Hãy triển khai ItemStreamWriter hoặc đăng ký delegate stream.

### Wrapper không chuyển tiếp open/update/close

Delegate có thể không được khởi tạo, không lưu checkpoint hoặc rò rỉ resource. Hãy chuyển tiếp lifecycle hoặc đăng ký delegate với Step.

### Nhầm flush với commit

Flush đẩy buffer xuống tầng ghi thấp hơn; commit xác nhận transaction. Hai thao tác có phạm vi khác nhau.

### Nhầm flush với đồng bộ vật lý

Dữ liệu đã flush có thể vẫn nằm trong cache của hệ điều hành. Khi cần mức bảo đảm cao hơn, cân nhắc forceSync và đo hiệu năng.

### Nuốt lỗi trong close()

Job có thể bị báo thành công trong khi output chưa hoàn chỉnh. Hãy để lỗi ghi/đóng được truyền tới Step hoặc được xử lý theo chính sách rõ ràng.

### Đóng tài nguyên dùng chung

Đóng DataSource, connection pool hoặc HTTP client singleton trong close() có thể làm hỏng các thành phần khác. Chỉ đóng tài nguyên writer sở hữu.

### Ghi file trực tiếp mà không có cơ chế rollback

Nếu chunk thất bại, file có thể giữ dữ liệu chưa commit. Dùng FlatFileItemWriter với transactional buffer hoặc thiết kế output tạm và publish sau khi Job hoàn tất.

## 17. Quy trình thiết kế writer quản lý resource an toàn

Khi tạo writer có tài nguyên bên ngoài, hãy xác định rõ ai sở hữu tài nguyên và khi nào dữ liệu được xem là hoàn tất.

1. Chọn writer dựng sẵn nếu nó đã hỗ trợ đúng loại output.
2. Nếu tự viết, triển khai ItemStreamWriter cho resource có vòng đời.
3. Mở resource trong open() và khôi phục trạng thái từ ExecutionContext nếu cần restart.
4. Dùng write() để ghi chunk; không đóng resource tại đây.
5. Cập nhật checkpoint trong update() nếu writer có trạng thái.
6. Để close() flush và giải phóng resource mà writer sở hữu.
7. Không đóng resource do Spring hoặc một component dùng chung quản lý.
8. Phân biệt flush, transaction commit và forceSync.
9. Xác định hành vi khi chunk rollback, Job restart hoặc close() gặp lỗi.
10. Kiểm thử wrapper, delegate và các đường cleanup sau lỗi.

Khi đọc một cấu hình ItemWriter, hãy tìm xem writer có triển khai ItemStream không, resource được mở ở đâu, ai chịu trách nhiệm đóng, buffer được flush tại thời điểm nào và transaction có thể rollback output hay không. Nếu trả lời được những câu hỏi này, bạn sẽ tránh được phần lớn lỗi mất dữ liệu, ghi trùng, file handle bị rò rỉ và Job báo thành công khi output chưa hoàn chỉnh.
