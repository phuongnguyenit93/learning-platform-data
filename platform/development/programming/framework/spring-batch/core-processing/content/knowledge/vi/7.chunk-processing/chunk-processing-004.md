# Đọc, xử lý và ghi trong một transaction

Trong Spring Batch, một **chunk-oriented Step** đọc dữ liệu, xử lý từng item và ghi kết quả theo từng nhóm. Mỗi chunk thường được thực hiện trong **một transaction riêng**: transaction bắt đầu khi xử lý chunk, bao gồm các thao tác đọc/xử lý/ghi do Step điều phối, rồi commit khi chunk hoàn tất thành công. Nếu xảy ra lỗi khiến chunk phải rollback, các thay đổi thuộc transaction đó được hoàn tác và chunk có thể được thử lại hoặc xử lý lại theo cấu hình.

Điểm quan trọng là transaction thường bao quanh **một chunk**, không bao quanh toàn bộ Step. Với chunk size bằng 100, một Step xử lý 10.000 bản ghi có thể tạo ra khoảng 100 transaction. Những chunk đã commit vẫn được giữ lại khi chunk sau thất bại.

Cách tổ chức này giúp xử lý tập dữ liệu lớn mà không cần giữ toàn bộ dữ liệu trong bộ nhớ hoặc mở một transaction rất dài. Để hiểu chính xác điều gì được rollback, cần phân biệt transaction database với những thao tác đọc file, gọi API hoặc ghi tài nguyên bên ngoài.

## 1. Ba thành phần trong chunk processing

Chunk-oriented processing có ba thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| **ItemReader** | Đọc từng item từ nguồn dữ liệu và trả về item tiếp theo |
| **ItemProcessor** | Kiểm tra, lọc hoặc chuyển đổi item |
| **ItemWriter** | Ghi tập item đã được xử lý trong chunk |

Ví dụ nhập dữ liệu khách hàng:

~~~text
Nguồn dữ liệu
     |
     v
 ItemReader
 đọc từng khách hàng
     |
     v
 ItemProcessor
 kiểm tra và chuyển đổi
     |
     v
 Danh sách item của chunk
     |
     v
 ItemWriter
 ghi vào database
     |
     v
 COMMIT transaction
~~~

Một vòng xử lý cơ bản:

1. Reader đọc từng item.
2. Processor nhận item và tạo kết quả tương ứng.
3. Các kết quả hợp lệ được gom thành chunk.
4. Writer nhận chunk và ghi dữ liệu.
5. Khi các thao tác trong chunk hoàn tất, transaction được commit.
6. Step bắt đầu chunk tiếp theo cho đến khi reader báo hết dữ liệu.

Reader thường trả về **null** khi không còn item. Processor có thể trả về **null** để loại một item khỏi kết quả ghi. Vì vậy, số item đọc được có thể khác số item writer nhận.

## 2. Một transaction cho mỗi chunk

Chunk size, còn gọi là commit interval, xác định số item tối đa được gom trong một chunk trước khi commit.

Ví dụ:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

**chunk(100, transactionManager)** cấu hình chunk size là 100 và transaction manager được dùng để quản lý transaction của Step.

Giả sử nguồn có 250 item:

| Chunk | Item được đọc | Thời điểm commit |
|---|---:|---|
| Chunk 1 | 1–100 | Sau khi writer ghi thành công |
| Chunk 2 | 101–200 | Sau khi writer ghi thành công |
| Chunk 3 | 201–250 | Chunk cuối, commit sau khi ghi thành công |

Chunk cuối có thể nhỏ hơn chunk size vì nguồn dữ liệu đã hết.

Với 250 item, Step không mở một transaction duy nhất cho toàn bộ 250 item. Nó tạo ba transaction chunk. Nếu chunk 3 thất bại, hai chunk đầu đã commit vẫn được giữ lại, còn thay đổi trong transaction chunk 3 có thể được rollback.

### Các giai đoạn trong transaction

Ở mức khái niệm, một chunk thường diễn ra như sau:

~~~text
Bắt đầu transaction
        |
        v
Reader đọc item
        |
        v
Processor xử lý từng item
        |
        v
Writer ghi chunk
        |
        v
Cập nhật trạng thái stream và metadata
        |
        v
COMMIT
~~~

Nếu có exception cần rollback:

~~~text
Bắt đầu transaction
        |
        v
Reader -> Processor -> Writer
                         |
                         v
                       ERROR
                         |
                         v
                      ROLLBACK
                         |
                         v
           Retry / Skip / Kết thúc Step
~~~

Spring Batch điều phối vòng lặp chunk và transaction. Khi writer hoàn tất, framework cập nhật trạng thái của các thành phần **ItemStream** và metadata thực thi trước khi transaction kết thúc. Với cấu hình transaction phù hợp, trạng thái checkpoint và dữ liệu nghiệp vụ có thể được commit nhất quán.

## 3. Reader đọc item trong transaction như thế nào?

Reader được gọi để lấy từng item cho chunk hiện tại. Tuy nhiên, cần phân biệt **lời gọi read() diễn ra trong phạm vi xử lý chunk** với việc nguồn dữ liệu có hỗ trợ rollback hay không.

Nếu reader đọc từ database qua cùng transaction manager, thao tác đọc có thể tham gia transaction database theo cấu hình và loại reader. Nếu reader đọc file CSV, việc tăng vị trí đọc trong file không phải một thao tác database có thể rollback.

Ví dụ:

- **FlatFileItemReader** đọc một dòng từ file.
- **JdbcCursorItemReader** đọc kết quả từ cursor database.
- **JdbcPagingItemReader** lấy dữ liệu theo từng trang.
- Một reader dùng JMS có thể nhận message từ hàng đợi có hỗ trợ transaction.

Với nguồn không có khả năng rollback như file, Spring Batch có thể buffer các item đã đọc để tránh đọc lại nguồn vật lý trong một số tình huống rollback trong cùng lần chạy. Với reader dựa trên hàng đợi giao dịch, rollback có thể trả message về hàng đợi; cách xử lý reader khi rollback vì vậy khác với file reader.

Không nên giả định con trỏ file, cursor database và message queue có cùng hành vi khi transaction rollback. Hãy xem tài liệu và cấu hình của reader cụ thể.

### Reader có trạng thái và checkpoint

Nhiều reader hỗ trợ **ItemStream**, cho phép lưu trạng thái đọc vào **ExecutionContext**:

- **open(ExecutionContext)**: khôi phục hoặc khởi tạo vị trí đọc.
- **update(ExecutionContext)**: lưu trạng thái tại checkpoint.
- **close()**: giải phóng tài nguyên.

Với reader có trạng thái, checkpoint thường được cập nhật khi chunk hoàn tất. Khi Job restart, reader có thể tiếp tục từ trạng thái đã lưu ở lần commit gần nhất.

Nếu reader tự viết, không lưu trạng thái hoặc bị wrapper che mất hợp đồng ItemStream, Spring Batch không thể tự suy ra vị trí đọc an toàn. Khi đó, reader có thể bắt đầu lại từ đầu hoặc cần cơ chế khôi phục riêng.

## 4. Processor xử lý item trong chunk

**ItemProcessor<I, O>** nhận một item đầu vào và trả về item đầu ra. Processor thường thực hiện:

- Kiểm tra dữ liệu đầu vào.
- Chuẩn hóa chuỗi, ngày tháng hoặc mã định danh.
- Ánh xạ DTO sang entity.
- Áp dụng quy tắc nghiệp vụ.
- Loại bỏ item không cần ghi.

Ví dụ:

~~~java
@Bean
public ItemProcessor<RawCustomer, Customer> customerProcessor() {
    return raw -> {
        if (raw.email() == null || raw.email().isBlank()) {
            return null;
        }

        return new Customer(
                raw.id(),
                raw.name().trim(),
                raw.email().trim().toLowerCase()
        );
    };
}
~~~

Nếu processor trả về một đối tượng **Customer**, item đó được chuyển tới writer. Nếu processor trả về **null**, item bị filter và không được chuyển tới writer.

Ví dụ một chunk đọc 100 item, trong đó 5 item không có email:

~~~text
Reader:      100 item
                 |
                 v
Processor:   95 kết quả hợp lệ
              5 item trả về null
                 |
                 v
Writer:       95 item
                 |
                 v
Commit transaction
~~~

Processor thường nên tập trung vào logic biến đổi và kiểm tra dữ liệu. Tránh gửi email, gọi API có tác dụng phụ hoặc thực hiện một thao tác không thể rollback bên trong processor. Nếu chunk bị retry hoặc rollback, processor có thể được gọi lại cho cùng item.

Một processor có thể đọc dữ liệu từ database hoặc gọi service, nhưng các thao tác đó chỉ được rollback nếu chúng tham gia cùng transaction phù hợp. Lời gọi HTTP hoặc ghi file thông thường không tự động được hoàn tác cùng transaction database của Step.

## 5. Writer ghi cả chunk

Writer nhận tập item đầu ra của chunk và ghi chúng. Với Spring Batch 5, API **ItemWriter** nhận một **Chunk**:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Ví dụ dùng JDBC batch writer:

~~~java
@Bean
public JdbcBatchItemWriter<Customer> customerWriter(
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

Writer nhận một chunk và ghi các item trong chunk đó. Với JDBC writer dùng cùng DataSource và transaction manager của Step, các câu lệnh ghi tham gia transaction chunk. Nếu một lỗi làm transaction rollback, những thay đổi database thuộc transaction đó được hoàn tác.

Writer cũng có thể ghi ra file, gọi dịch vụ hoặc gửi dữ liệu sang hệ thống khác. Nhưng các loại tài nguyên này không nhất thiết tham gia transaction database. Cần hiểu rõ transaction boundary của từng writer trước khi dựa vào rollback để bảo vệ dữ liệu.

### Writer ghi một phần rồi gặp lỗi

Giả sử writer thực hiện nhiều câu lệnh insert trong một chunk:

~~~text
Chunk chứa 100 khách hàng
       |
       v
INSERT khách hàng 1  -> thành công
INSERT khách hàng 2  -> thành công
...
INSERT khách hàng 60 -> lỗi
       |
       v
Exception được ném ra
       |
       v
ROLLBACK transaction
       |
       v
Các insert trong transaction bị hoàn tác
~~~

Khi tất cả câu lệnh ghi tham gia cùng transaction database, các insert đã thực hiện trước khi lỗi cũng được rollback. Nếu writer dùng một transaction khác, **REQUIRES_NEW**, một database khác hoặc một API bên ngoài, kết quả có thể khác. Không nên coi mọi thao tác writer thực hiện đều được rollback tự động.

## 6. Transaction manager quyết định phạm vi rollback

Khi xây dựng Step, transaction manager được truyền vào builder:

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
~~~

Transaction manager xác định transaction mà Step sử dụng. Với ứng dụng JDBC, thường dùng transaction manager gắn với DataSource chứa dữ liệu nghiệp vụ.

Để dữ liệu nghiệp vụ và checkpoint metadata được commit nhất quán, cần xem xét:

- Writer và JobRepository có dùng cùng database hay không.
- Chúng có tham gia cùng transaction manager hay không.
- Có sử dụng transaction propagation khác như **REQUIRES_NEW** hay không.
- Có nhiều DataSource hoặc tài nguyên bên ngoài hay không.

Nếu dữ liệu nghiệp vụ và metadata nằm trong cùng transaction được quản lý, một lần commit có thể xác nhận cả hai. Nếu chúng nằm ở các transaction hoặc tài nguyên độc lập, có thể xảy ra tình huống dữ liệu nghiệp vụ đã ghi nhưng checkpoint chưa được lưu, hoặc ngược lại. Khi đó cần thiết kế idempotency, đối soát hoặc cơ chế phối hợp transaction phù hợp.

**Transaction manager không tự biến mọi tài nguyên mà Java gọi tới thành tài nguyên transactional.** Nó chỉ quản lý các tài nguyên tham gia transaction tương ứng.

## 7. Điều gì xảy ra khi chunk thành công?

Giả sử một chunk có 100 item và tất cả đều hợp lệ:

1. Step bắt đầu transaction.
2. Reader đọc 100 item.
3. Processor xử lý từng item.
4. Writer ghi các kết quả được tạo ra.
5. Framework cập nhật trạng thái của các stream và metadata Step.
6. Transaction commit.
7. Step chuyển sang chunk tiếp theo.

Sau commit, dữ liệu được ghi trong transaction đã được xác nhận. Checkpoint tương ứng có thể được sử dụng khi restart nếu Job gặp lỗi ở chunk sau.

Nếu tất cả item bị processor filter, không có item tương ứng được chuyển tới writer. Chunk vẫn cần được xử lý và trạng thái đọc/checkpoint được cập nhật theo cơ chế của Step.

Không nên chỉ nhìn số item ghi để kết luận chunk đã xử lý bao nhiêu dữ liệu. Hãy đối chiếu read count, filter count, skip count, write count và commit count.

## 8. Điều gì xảy ra khi chunk rollback?

Giả sử chunk size là 100 và Step đã xử lý:

~~~text
Chunk 1: 1   - 100  -> COMMIT
Chunk 2: 101 - 200  -> COMMIT
Chunk 3: 201 - 300  -> Writer gặp lỗi
                         |
                         v
                       ROLLBACK
~~~

Kết quả:

- Dữ liệu đã commit trong chunk 1 và 2 vẫn được giữ lại.
- Các thay đổi trong transaction chunk 3 được rollback nếu chúng thuộc cùng transaction.
- Step có thể kết thúc FAILED nếu exception không được xử lý bằng retry hoặc skip.
- Khi restart JobInstance, Step có thể tiếp tục từ checkpoint gần nhất đã lưu, thường là sau chunk 2.

Trong cùng lần chạy, hành vi sau rollback còn phụ thuộc vào cấu hình retry/skip và loại reader. Spring Batch có thể buffer item đã đọc để xử lý lại mà không đọc lại nguồn vật lý. Với nguồn dữ liệu transactional như message queue, việc rollback có thể trả item về nguồn để được nhận lại.

Đối với một nguồn không có checkpoint hoặc không hỗ trợ khôi phục, ứng dụng có thể phải đọc lại từ đầu. Vì vậy, khả năng restart phụ thuộc cả vào cách lưu trạng thái của reader.

## 9. Retry và skip trong chunk transaction

Không phải exception nào cũng buộc toàn bộ Job kết thúc ngay lập tức. Spring Batch hỗ trợ cấu hình retry và skip để xử lý lỗi tạm thời hoặc bản ghi không hợp lệ theo chính sách nghiệp vụ.

### Retry lỗi tạm thời

Retry phù hợp với lỗi có khả năng biến mất khi thử lại, chẳng hạn deadlock hoặc lỗi truy cập tài nguyên tạm thời.

Ví dụ cấu hình minh họa:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Ở đây, lỗi thuộc nhóm **TransientDataAccessException** có thể được thử lại theo giới hạn đã cấu hình. Cách framework khởi động lại transaction và gọi lại thành phần phụ thuộc vào vị trí exception, chính sách retry và loại reader/writer.

Không nên retry mọi exception. Lỗi dữ liệu không hợp lệ hoặc lỗi cấu hình thường không tự hết khi thử lại.

### Skip item không hợp lệ

Skip phù hợp khi nghiệp vụ cho phép bỏ qua một số item lỗi và tiếp tục xử lý các item còn lại.

~~~java
.faultTolerant()
.skip(InvalidCustomerException.class)
.skipLimit(100)
.build();
~~~

Trong ví dụ, Step cho phép bỏ qua tối đa 100 item thuộc loại **InvalidCustomerException**. Khi vượt giới hạn, Step thất bại.

Skip count được ghi nhận trong StepExecution. Nên có listener hoặc cơ chế ghi nhận bản ghi bị bỏ qua để có thể điều tra và xử lý lại sau này.

Retry và skip không thay đổi ý nghĩa của transaction chunk: những thay đổi chỉ được xác nhận khi transaction tương ứng commit. Cần thử nghiệm chính sách lỗi với reader và writer thực tế, đặc biệt khi writer có tác dụng phụ ngoài database.

## 10. Retry, rollback và tính idempotent

Một chunk có thể được xử lý lại sau rollback hoặc retry. Vì thế, những thao tác trong reader, processor và writer cần được thiết kế để chịu được việc gọi lại.

Ví dụ không an toàn:

~~~java
public Customer process(RawCustomer raw) {
    notificationService.sendWelcomeEmail(raw.email());
    return convert(raw);
}
~~~

Nếu writer sau đó gặp lỗi và chunk bị retry, email có thể được gửi lần nữa. Database rollback không thu hồi được email đã gửi.

Cách thiết kế an toàn hơn là:

- Giữ processor tập trung vào chuyển đổi dữ liệu.
- Ghi dữ liệu nghiệp vụ và yêu cầu gửi thông báo trong cùng transaction nếu có thể, chẳng hạn thông qua outbox table.
- Một worker riêng đọc outbox và gửi thông báo.
- Dùng mã định danh duy nhất để bên nhận chống xử lý trùng.

Với API bên ngoài, có thể dùng idempotency key gắn với mã nghiệp vụ. Nếu cùng một yêu cầu được gửi lại, hệ thống đích nhận ra đây là cùng thao tác và không tạo thêm tác dụng phụ.

**Rollback chỉ hoàn tác những thay đổi được quản lý trong transaction đó.** Nó không tự động hoàn tác HTTP request, email, file đã ghi hoặc thay đổi ở database khác.

## 11. Transaction và các listener của chunk

Spring Batch cung cấp listener để quan sát từng giai đoạn xử lý:

- **ItemReadListener**: theo dõi đọc item và lỗi đọc.
- **ItemProcessListener**: theo dõi xử lý item, kết quả hoặc lỗi.
- **ItemWriteListener**: theo dõi ghi chunk và lỗi ghi.
- **ChunkListener**: theo dõi vòng đời chunk.

Ví dụ:

~~~java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.info("Starting a chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.info("Chunk completed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.error("Chunk failed");
    }
}
~~~

Đăng ký listener:

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .listener(importChunkListener)
        .build();
~~~

Listener hữu ích cho logging, metrics và giám sát. Tuy nhiên, cần phân biệt callback của listener với transaction commit. Ví dụ, một callback sau chunk không có nghĩa mọi thao tác bên ngoài đã được commit bền vững. Hãy chọn đúng callback và cơ chế lưu sự kiện nếu cần bảo đảm thông báo sau commit.

Không nên đặt tác dụng phụ quan trọng vào listener mà không xem xét retry, rollback và khả năng listener được gọi lại.

## 12. Đọc và ghi giữa nhiều tài nguyên

Một Step có thể đọc từ một nguồn và ghi sang một nguồn khác, ví dụ:

- Đọc CSV và ghi database.
- Đọc database và ghi file.
- Đọc REST API và ghi database.
- Đọc message queue và ghi sang hệ thống nghiệp vụ.

Trong các trường hợp này, transaction không nhất thiết bao phủ cả nguồn đọc lẫn đích ghi.

Ví dụ đọc CSV và ghi database:

~~~text
CSV file
   |
   v
ItemReader
   |
   v
ItemProcessor
   |
   v
JdbcBatchItemWriter
   |
   v
Database transaction
   |
   v
COMMIT / ROLLBACK
~~~

Database writer có thể tham gia transaction. Nhưng vị trí đọc trong file không được database transaction quản lý trực tiếp. Spring Batch cần lưu checkpoint của reader để khôi phục tiến độ.

Ví dụ đọc message queue và ghi database:

~~~text
Message Queue
      |
      v
ItemReader
      |
      v
Processor
      |
      v
Database Writer
      |
      v
Transaction resources
~~~

Nếu message queue và database cùng tham gia một transaction được hỗ trợ, chúng có thể phối hợp commit/rollback theo cấu hình. Nếu không, cần cân nhắc khả năng message được nhận lại trong khi database đã ghi, hoặc database rollback nhưng message đã được xác nhận. Cơ chế idempotency và đối soát rất quan trọng trong trường hợp này.

## 13. Chọn chunk size phù hợp

Chunk size ảnh hưởng đến:

- Số lần transaction bắt đầu và commit.
- Lượng dữ liệu giữ trong bộ nhớ.
- Thời gian mỗi transaction mở.
- Khối lượng công việc cần retry hoặc xử lý lại khi lỗi.
- Tải lên database và hệ thống đích.

| Chunk size | Đặc điểm thường gặp |
|---|---|
| Nhỏ | Transaction ngắn hơn, commit thường xuyên, ít item trong mỗi lần rollback |
| Lớn | Ít transaction hơn, có thể tăng hiệu suất ghi theo lô, nhưng giữ nhiều item hơn và transaction dài hơn |

Không có một chunk size phù hợp cho mọi ứng dụng. Hãy bắt đầu với kích thước vừa phải, đo thời gian xử lý, thời gian commit, mức sử dụng bộ nhớ và tải database. Sau đó điều chỉnh theo dữ liệu thực tế.

Nếu writer có thể ghi theo batch, chunk size phù hợp có thể giúp tận dụng hiệu quả batch insert/update. Nhưng tăng chunk size quá mức có thể làm transaction kéo dài, giữ lock lâu và tăng chi phí rollback khi gặp lỗi.

## 14. Theo dõi transaction và kết quả xử lý

**StepExecution** cung cấp các số liệu giúp quan sát tiến trình:

| Thuộc tính | Ý nghĩa |
|---|---|
| **readCount** | Số item đã đọc |
| **writeCount** | Số item đã ghi |
| **filterCount** | Số item bị processor loại bỏ |
| **readSkipCount** | Số item bị skip khi đọc |
| **processSkipCount** | Số item bị skip khi xử lý |
| **writeSkipCount** | Số item bị skip khi ghi |
| **commitCount** | Số lần commit |
| **rollbackCount** | Số lần rollback |

Ví dụ một Step có kết quả:

~~~text
readCount        = 1000
writeCount       = 940
filterCount      = 40
processSkipCount = 10
writeSkipCount   = 10
commitCount      = 10
rollbackCount    = 1
~~~

Các con số này giúp phát hiện chênh lệch giữa dữ liệu đọc và ghi. Tuy nhiên, chúng không thay thế log chi tiết hoặc báo cáo lỗi theo từng bản ghi.

Khi một chunk rollback rồi retry thành công, số lần đọc, xử lý hoặc rollback có thể phản ánh các lần thử tùy vào thành phần và cách framework ghi nhận. Đừng diễn giải một counter riêng lẻ như bằng chứng đầy đủ về số lần một item đã được xử lý.

## 15. Những nhầm lẫn thường gặp

### Nghĩ rằng toàn bộ Step chạy trong một transaction

Với chunk-oriented Step, mỗi chunk thường có transaction riêng. Những chunk đã commit vẫn tồn tại nếu chunk sau thất bại.

### Nghĩ rằng đọc file có thể rollback như database

Vị trí đọc trong file không tự động quay lại khi database transaction rollback. Reader cần hỗ trợ buffering hoặc checkpoint để khôi phục đúng trạng thái.

### Nghĩ rằng processor trả về null là lỗi

Trả về null là cách hợp lệ để filter item. Item đó không được chuyển tới writer.

### Nghĩ rằng writer ghi thành công nghĩa là dữ liệu đã commit

Writer hoàn tất trước khi transaction commit. Một lỗi xảy ra sau đó trong cùng transaction vẫn có thể khiến dữ liệu bị rollback.

### Nghĩ rằng mọi thao tác trong Java đều rollback

Transaction manager chỉ rollback các tài nguyên tham gia transaction. Email, HTTP request hoặc file ghi ra ngoài không tự động được hoàn tác.

### Nghĩ rằng chunk size bằng số bản ghi writer chắc chắn ghi

Processor có thể filter item và skip policy có thể bỏ qua item lỗi. Số lượng đọc và ghi vì vậy có thể khác nhau.

### Nghĩ rằng retry luôn đọc lại từ nguồn

Spring Batch có thể buffer item đã đọc để xử lý lại sau rollback. Reader transactional như message queue có hành vi khác. Cần xem cấu hình và loại reader thực tế.

## 16. Quy trình thiết kế một chunk transaction an toàn

Khi xây dựng Step đọc, xử lý và ghi dữ liệu, hãy xác định rõ nguồn, đích và ranh giới transaction.

1. Chọn reader phù hợp với nguồn dữ liệu và khả năng lưu trạng thái.
2. Viết processor tập trung vào kiểm tra và chuyển đổi item.
3. Chọn writer có thể ghi theo batch và tham gia transaction của Step nếu cần rollback cùng dữ liệu nghiệp vụ.
4. Cấu hình chunk size dựa trên đo đạc hiệu năng và tài nguyên.
5. Chọn transaction manager đúng với DataSource hoặc tài nguyên cần bảo vệ.
6. Quyết định loại exception nào cần retry, loại nào được skip và giới hạn tương ứng.
7. Lưu checkpoint của reader để hỗ trợ restart sau lỗi.
8. Thiết kế các thao tác bên ngoài transaction có tính idempotent.
9. Theo dõi read/write/filter/skip count, commit và rollback.
10. Kiểm tra tình huống lỗi giữa lúc writer đang ghi để hiểu chính xác phần nào được rollback.

Khi đọc một cấu hình chunk Step, hãy lần theo **chunk(size, transactionManager)**, **reader(...)**, **processor(...)** và **writer(...)**. Sau đó xác định writer dùng tài nguyên nào, tài nguyên đó có tham gia transaction không và reader lưu checkpoint ra sao. Như vậy bạn sẽ biết rõ dữ liệu nào được commit cùng nhau, dữ liệu nào có thể bị rollback và điều gì sẽ xảy ra khi chunk phải chạy lại.
