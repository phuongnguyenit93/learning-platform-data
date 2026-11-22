# Rollback khi writer thất bại

Trong Spring Batch, một chunk-oriented Step thường xử lý mỗi chunk bên trong một transaction. Khi **ItemWriter** ném exception trong lúc ghi chunk, Spring Batch áp dụng rollback policy của Step. Nếu exception được phân loại là lỗi cần rollback, transaction của chunk bị hủy và các thay đổi trên những tài nguyên tham gia transaction đó được hoàn tác.

Điều này bảo vệ dữ liệu database khi writer đã ghi được một phần rồi mới gặp lỗi. Ví dụ writer thực hiện 100 lệnh insert, 60 lệnh đầu chạy thành công nhưng lệnh thứ 61 thất bại. Nếu tất cả lệnh dùng cùng transaction database của chunk, rollback sẽ hoàn tác cả 60 lệnh trước đó.

Tuy nhiên, rollback chỉ hoàn tác tài nguyên thực sự tham gia transaction. Email đã gửi, HTTP request đã được server xử lý hoặc file được ghi trực tiếp không tự động được khôi phục. Vì vậy, khi writer thất bại, cần xác định rõ transaction manager, tài nguyên ghi, loại exception và chính sách retry/skip trước khi kết luận dữ liệu nào đã được hoàn tác.

## 1. Transaction bao quanh lời gọi writer như thế nào?

Với chunk processing, transaction được mở cho từng chunk. Reader đọc item, processor tạo kết quả và writer ghi chunk trong phạm vi thực thi do Step quản lý.

~~~text
Bắt đầu transaction chunk
          |
          v
ItemReader đọc item
          |
          v
ItemProcessor xử lý item
          |
          v
ItemWriter.write(chunk)
          |
          +---- Thành công
          |         |
          |         v
          |    Cập nhật checkpoint
          |         |
          |         v
          |       COMMIT
          |
          +---- Ném exception
                    |
                    v
              Rollback policy
                    |
                    v
                 ROLLBACK
                    |
                    v
           Retry / Skip / Step FAILED
~~~

Transaction manager được truyền vào cấu hình chunk:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong ví dụ, mỗi chunk tối đa 100 item là một đơn vị transaction của Step. Khi writer trả về thành công, framework còn cập nhật trạng thái stream và metadata trước khi transaction commit. Vì vậy, writer hoàn tất không có nghĩa chunk đã commit; lỗi ở giai đoạn sau vẫn có thể khiến transaction rollback.

## 2. Điều gì xảy ra khi writer ghi được một phần rồi thất bại?

Giả sử chunk chứa 100 đơn hàng. Writer ghi lần lượt các đơn hàng vào cùng database:

~~~text
Chunk gồm 100 đơn hàng
          |
          v
INSERT order 1   -> thành công
INSERT order 2   -> thành công
...
INSERT order 60  -> thành công
INSERT order 61  -> lỗi
          |
          v
Exception thoát khỏi writer
          |
          v
Transaction rollback
          |
          v
Các thay đổi trong transaction
được hoàn tác
~~~

Nếu tất cả câu lệnh insert tham gia cùng một transaction database, các lệnh đã chạy trước khi lỗi cũng bị rollback. Sau rollback, database không giữ lại 60 đơn hàng đầu của chunk đó.

Các chunk trước đã commit vẫn tồn tại. Ví dụ Step có chunk size 100 và đã commit hai chunk đầu, nhưng chunk thứ ba thất bại:

| Chunk | Kết quả | Dữ liệu |
|---|---|---|
| Chunk 1 | COMMIT | Được giữ |
| Chunk 2 | COMMIT | Được giữ |
| Chunk 3 | ROLLBACK | Thay đổi của chunk bị hoàn tác |
| Chunk 4 | Chưa chạy | Chưa được xử lý |

Rollback của chunk 3 không đảo ngược những transaction đã commit ở chunk 1 và 2. Khi Job restart, Step có thể tiếp tục từ checkpoint đã lưu ở commit gần nhất nếu reader hỗ trợ khôi phục trạng thái.

## 3. Điều kiện để dữ liệu writer thực sự được rollback

Để rollback có hiệu lực với dữ liệu writer đã ghi, cần xem xét các điều kiện sau:

1. Writer sử dụng tài nguyên transactional, chẳng hạn database hỗ trợ transaction.
2. Writer tham gia transaction đang được Step quản lý.
3. Writer và Step dùng đúng transaction manager và resource tương ứng.
4. Exception được truyền ra ngoài writer để framework nhận biết.
5. Rollback policy phân loại exception là lỗi cần rollback.
6. Không có transaction độc lập đã commit trước đó chứa cùng thay đổi.

Ví dụ với JDBC:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO orders (id, order_number, amount)
                VALUES (:id, :orderNumber, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Nếu DataSource của writer là cùng DataSource được transaction manager của Step quản lý, các câu lệnh ghi có thể tham gia transaction chunk thông qua Spring JDBC.

Nếu writer dùng một DataSource khác hoặc tự mở connection độc lập rồi commit, transaction của Step không tự động rollback các thay đổi đó. Hãy kiểm tra cách connection được lấy và quản lý; không chỉ dựa vào việc writer được gọi bên trong một Step có transaction.

## 4. Ví dụ writer dùng cùng transaction database

Một cấu hình JDBC thường có transaction manager gắn với DataSource nghiệp vụ:

~~~java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Writer dùng cùng DataSource:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO orders (id, order_number, amount)
                VALUES (:id, :orderNumber, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Khi một lệnh ghi thất bại và transaction rollback, các thay đổi database trong chunk được hoàn tác theo transaction semantics của database.

Không nên tự lấy connection mới trong writer rồi gọi commit riêng:

~~~java
// Ví dụ không phù hợp khi muốn writer tham gia transaction chunk.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    // Ghi dữ liệu...
    connection.commit();
}
~~~

Đoạn code này tạo một transaction do writer tự quản lý. Nếu writer commit độc lập, transaction manager của Step không thể hoàn tác thay đổi đó khi chunk thất bại sau này.

Với custom JDBC writer, ưu tiên JdbcTemplate, NamedParameterJdbcTemplate hoặc DataSourceUtils để dùng connection gắn với transaction Spring hiện tại. Tránh tự commit trong writer khi mục tiêu là rollback toàn bộ chunk.

## 5. Writer ném exception và writer nuốt exception

Spring Batch chỉ có thể áp dụng chính sách lỗi khi lỗi được truyền tới framework.

Cách xử lý không an toàn:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException ex) {
        log.error("Cannot write orders", ex);
        // Không ném lại exception.
    }
}
~~~

Trong trường hợp này, writer đã bắt exception rồi trả về bình thường. Spring Batch có thể coi lời gọi write thành công và tiếp tục cập nhật checkpoint/commit. Nếu một phần dữ liệu đã được ghi, kết quả có thể không như mong đợi.

Cách phù hợp hơn:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException ex) {
        log.error("Cannot write order chunk", ex);
        throw ex;
    }
}
~~~

Nếu cần chuyển exception sang loại riêng, hãy giữ nguyên nguyên nhân gốc:

~~~java
throw new OrderWriteException(
        "Cannot persist the current order chunk",
        ex);
~~~

Đừng bắt exception rồi chỉ ghi log nếu Step cần biết thao tác ghi đã thất bại. Cũng không nên biến mọi exception thành một loại chung mà làm mất thông tin để retry/skip classifier phân loại đúng.

## 6. Rollback policy và loại exception

Rollback phụ thuộc rollback classifier và transaction attribute của Step. Cần xem loại exception, cấu hình fault-tolerant và transaction policy của phiên bản Spring Batch/Spring đang dùng.

Trong cấu hình thông thường, lỗi ghi không được xử lý sẽ làm chunk thất bại và transaction được rollback theo chính sách mặc định của Step. Với exception tùy chỉnh, đặc biệt checked exception, hãy kiểm tra rollback rule thực tế thay vì giả định mọi loại Throwable đều có cùng hành vi.

Có thể cấu hình transaction attribute của Step để kiểm soát isolation, propagation và timeout:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();

transactionAttribute.setTimeout(60);

Step step = new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Không nên dùng cấu hình rollback rộng hoặc noRollback chỉ để làm Step tiếp tục chạy. Trước tiên cần hiểu dữ liệu nào writer đã thay đổi và liệu các thay đổi đó có thể để lại trạng thái một phần hay không.

## 7. Retry khi writer thất bại

Nếu writer gặp lỗi có khả năng tạm thời, Step có thể retry theo fault-tolerant policy. Mỗi lần thử cần tuân theo transaction semantics phù hợp; một lần ghi thất bại thường khiến transaction hiện tại rollback trước khi framework thực hiện lần thử tiếp theo.

Ví dụ retry database deadlock:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Retry phù hợp khi lần thực hiện tiếp theo có khả năng thành công, chẳng hạn:

- Database deadlock.
- Lock tạm thời không lấy được.
- Lỗi kết nối có khả năng phục hồi.
- Một số lỗi timeout từ dịch vụ bên ngoài.

Không nên retry mọi lỗi ghi. Vi phạm constraint do dữ liệu không hợp lệ thường không tự hết khi thử lại. Lỗi SQL sai hoặc schema không tương thích cũng cần được sửa thay vì lặp vô ích.

Retry limit phải hữu hạn. Nếu cần backoff, cấu hình chính sách chờ giữa các lần thử để giảm áp lực lên database đang quá tải.

## 8. Skip khi writer thất bại

Skip có thể được dùng khi writer thất bại vì một item cụ thể và nghiệp vụ cho phép loại item đó khỏi kết quả của lần chạy.

Ví dụ một đơn hàng vi phạm quy tắc ghi và có thể được đưa vào danh sách rejected:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Với write skip, Spring Batch có thể cần xác định item gây lỗi bằng cách thực hiện lại việc ghi với các nhóm nhỏ hơn hoặc từng item, tùy cơ chế fault-tolerant. Vì vậy writer có thể được gọi nhiều lần cho các tập item khác nhau.

Điều này có một hệ quả quan trọng: **writer phải chịu được việc được gọi lại**. Không đặt side effect không idempotent trong writer rồi giả định write() chỉ được gọi đúng một lần cho mỗi chunk.

Skip không phù hợp nếu lỗi làm database không thể ghi, chẳng hạn database down hoặc hết dung lượng. Bỏ qua từng item trong tình huống đó chỉ che giấu sự cố và có thể làm mất một lượng lớn dữ liệu.

## 9. Kết hợp retry và skip cho lỗi ghi

Một exception có thể được cấu hình vừa retryable vừa skippable. Khi đó, Spring Batch có thể thử lại trước; nếu retry hết giới hạn và exception vẫn thuộc nhóm được phép skip, item có thể bị bỏ qua nếu skip limit còn.

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Chính sách cần được phân loại rõ:

| Loại lỗi | Hướng xử lý |
|---|---|
| Deadlock | Retry |
| Lỗi kết nối tạm thời | Retry có giới hạn |
| Một order vi phạm constraint do dữ liệu | Skip nếu nghiệp vụ cho phép |
| SQL sai hoặc schema sai | Fail |
| Database không còn dung lượng | Fail và xử lý sự cố |
| Không xác định được item gây lỗi trong một batch bên ngoài | Thường fail hoặc dùng quy trình đối soát riêng |

Khi retry hết giới hạn mà exception không skippable, Step thất bại. Khi exception skippable nhưng tổng skip vượt skipLimit, Step cũng thất bại.

## 10. Write skip và việc xác định item gây lỗi

Khác với processor, writer thường nhận cả chunk. Nếu một câu lệnh batch ghi thất bại, exception có thể chỉ cho biết batch không thành công mà không xác định rõ item nào gây lỗi.

Spring Batch có thể dùng cơ chế fault-tolerant để phân tích lại việc ghi và xác định item lỗi. Điều này có thể khiến writer được gọi với các chunk nhỏ hơn trong quá trình xử lý write skip.

Ví dụ chunk ban đầu:

~~~text
[A, B, C, D]
      |
      v
Writer ghi cả chunk -> lỗi
      |
      v
Framework xác định item lỗi
      |
      +--> [A] -> thành công
      +--> [B] -> lỗi -> skip nếu được phép
      +--> [C] -> thành công
      +--> [D] -> thành công
~~~

Sơ đồ chỉ minh họa ý tưởng. Cách chia nhóm, số lần gọi writer và thứ tự thử lại phụ thuộc cấu hình và phiên bản framework.

Nếu writer gửi một request duy nhất cho cả chunk tới API ngoài, server trả lỗi chung mà không chỉ ra item lỗi, framework không thể tự suy ra bản ghi nào nên skip một cách an toàn. Khi đó, cần thiết kế giao thức trả lỗi theo item, hoặc chủ động chia batch và đối soát.

## 11. SkipListener ghi nhận item bị writer từ chối

Khi item bị skip ở giai đoạn ghi, SkipListener có thể lưu bản ghi và nguyên nhân để xử lý sau.

~~~java
@Component
public class OrderWriteSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedRepository;

    public OrderWriteSkipListener(
            RejectedOrderRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        // Ghi nhận lỗi đọc nếu có thông tin nguồn.
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Ghi nhận item bị skip khi xử lý.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {

        rejectedRepository.save(
                RejectedOrder.from(item, exception.getMessage()));
    }
}
~~~

Đăng ký listener với Step:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderWriteSkipListener)
        .build();
~~~

SkipListener được gọi ở giai đoạn phù hợp để việc ghi nhận lỗi có thể tham gia transaction chunk. Nếu rejectedRepository dùng cùng transaction manager và database, bản ghi lỗi có thể được commit cùng chunk. Nếu listener gửi dữ liệu tới hệ thống ngoài, rollback database không thể thu hồi tác động đó.

## 12. Writer ghi file: rollback không giống database

File thông thường không tham gia transaction JDBC. Nếu writer ghi trực tiếp vào file rồi database transaction rollback, các byte đã ghi ra file không tự động bị xóa.

Ví dụ:

~~~text
Chunk transaction bắt đầu
        |
        v
Writer ghi 50 dòng vào file
        |
        v
Writer gặp lỗi ở dòng tiếp theo
        |
        v
Database transaction rollback
        |
        v
File vẫn có thể chứa 50 dòng đã ghi
~~~

Với FlatFileItemWriter, Spring Batch có cơ chế transactional buffering để phối hợp output file với transaction của chunk khi cấu hình transactional phù hợp. Hãy dùng writer dựng sẵn và kiểm tra cấu hình thay vì tự quản lý stream mà không có checkpoint/rollback.

Một custom writer ghi file trực tiếp cần có chiến lược rõ ràng:

- Ghi vào file tạm và chỉ publish sau khi Job hoàn tất.
- Lưu vị trí hoặc checkpoint để restart.
- Có thể truncate hoặc khôi phục phần chưa commit.
- Dùng output theo execution ID để tránh ghi đè nhầm.
- Đối soát file nếu tiến trình dừng bất thường.

Không được mặc định một file writer có cùng semantics rollback như JdbcBatchItemWriter.

## 13. Writer gọi API hoặc hệ thống bên ngoài

Nếu writer gửi dữ liệu tới HTTP API, message broker hoặc dịch vụ khác, transaction database của Step không tự động rollback tác động đã xảy ra ở hệ thống đích.

Ví dụ:

~~~text
Chunk bắt đầu
    |
    v
Gửi order A tới API -> thành công
    |
    v
Gửi order B tới API -> thành công
    |
    v
Gửi order C tới API -> timeout
    |
    v
Chunk rollback ở database
~~~

Hai request đầu có thể đã được hệ thống ngoài xử lý. Nếu Job retry chunk, các request đó có thể được gửi lại.

Các cách giảm rủi ro:

- Dùng idempotency key ổn định theo mã đơn hàng.
- Yêu cầu API đích hỗ trợ kiểm tra request đã xử lý.
- Ghi yêu cầu gửi ra vào outbox trong cùng transaction database.
- Dùng worker riêng gửi outbox và retry độc lập.
- Lưu response hoặc mã giao dịch ngoài để đối soát.
- Thiết kế thao tác bù trừ nếu hệ thống đích không hỗ trợ idempotency.

Không thể bảo đảm exactly-once giữa database và một API tùy ý chỉ bằng cách đặt lời gọi HTTP bên trong ItemWriter.

## 14. Composite writer và lỗi giữa các delegate

Một writer có thể chuyển cùng chunk tới nhiều delegate, ví dụ một delegate ghi database và một delegate ghi file.

~~~text
Composite writer
       |
       +--> Database writer
       |
       +--> File writer
       |
       +--> Audit writer
~~~

Nếu database writer thành công nhưng file writer thất bại, kết quả phụ thuộc vào tài nguyên và transaction của từng delegate:

- Database có thể rollback nếu tham gia transaction chunk.
- File có thể vẫn giữ nội dung đã ghi nếu không có transactional buffer phù hợp.
- Audit writer dùng REQUIRES_NEW có thể đã commit độc lập.
- API ngoài có thể đã xử lý request.

Composite writer không tự tạo distributed transaction cho mọi delegate. Hãy kiểm tra từng writer, thứ tự gọi, resource ownership và rollback semantics.

Nếu nhiều đích phải nhất quán, cân nhắc outbox hoặc một quy trình publish có trạng thái rõ ràng thay vì ghi trực tiếp nhiều tài nguyên không có transaction chung.

## 15. noRollback không phải cách sửa lỗi writer

Spring Batch cho phép cấu hình một số exception không buộc rollback bằng noRollback(...). Cấu hình này thay đổi rollback classification; nó không tự động bỏ qua item và cũng không sửa dữ liệu đã ghi một phần.

Ví dụ:

~~~java
.faultTolerant()
.noRollback(ValidationWarningException.class)
~~~

Chỉ dùng khi exception thực sự biểu thị tình huống mà transaction vẫn có thể hoàn tất an toàn. Nếu writer đã thực hiện một số thao tác ghi rồi ném exception, bỏ rollback có thể khiến chunk commit trạng thái một phần.

Phân biệt ba cơ chế:

| Cơ chế | Ý nghĩa |
|---|---|
| Retry | Thực hiện lại thao tác thất bại |
| Skip | Bỏ qua item theo chính sách và giới hạn |
| noRollback | Không rollback transaction cho exception được chỉ định |

Nếu writer thất bại vì lỗi ghi thật sự, rollback thường là hành vi cần thiết. Không dùng noRollback để ép Job chạy tiếp khi chưa biết trạng thái dữ liệu.

## 16. Exception xảy ra trong write và exception xảy ra khi commit

Hai tình huống này cần được phân biệt.

**Write failure** xảy ra khi ItemWriter.write() đang thực hiện và ném exception. Spring Batch có thể áp dụng retry/skip policy, rollback transaction và xử lý lại theo cấu hình.

**Commit failure** xảy ra sau khi writer trả về thành công, trong lúc transaction manager commit. Ví dụ connection bị mất trong quá trình commit hoặc database từ chối commit.

Với commit failure, kết quả thực tế đôi khi không rõ ràng nếu kết nối bị đứt đúng thời điểm database xử lý commit. Ứng dụng có thể không biết chắc transaction đã commit hay chưa chỉ từ exception phía client.

Trong tình huống không xác định kết quả commit:

- Không giả định rollback chắc chắn đã xảy ra.
- Không gửi lại thao tác không idempotent một cách mù quáng.
- Dùng business key hoặc unique constraint để kiểm tra dữ liệu đã tồn tại.
- Truy vấn trạng thái từ database sau khi kết nối phục hồi.
- Thiết kế writer có thể chạy lại an toàn.

Đây là một lý do quan trọng để writer có tính idempotent.

## 17. Retry làm writer được gọi lại: cần idempotency

Khi một chunk rollback rồi được retry, writer có thể được gọi lại với cùng dữ liệu. Với database writer tham gia transaction, lần ghi trước đã rollback nên lần thử lại có thể an toàn theo transaction semantics.

Nhưng nếu writer có tác động ngoài transaction, gọi lại có thể tạo bản ghi trùng hoặc gửi cùng thông báo nhiều lần.

Ví dụ dùng business key để chống ghi trùng:

~~~sql
INSERT INTO orders (order_id, order_number, amount)
VALUES (:orderId, :orderNumber, :amount)
ON CONFLICT (order_id)
DO UPDATE SET
    order_number = EXCLUDED.order_number,
    amount = EXCLUDED.amount
~~~

Cú pháp upsert phụ thuộc database. Mục tiêu là cùng một yêu cầu nghiệp vụ có thể được áp dụng lại mà không tạo thêm một bản ghi mới ngoài ý muốn.

Với API, dùng idempotency key. Với event, dùng event ID. Với file, dùng file tạm theo JobExecution và publish theo quy tắc xác định.

## 18. Theo dõi writer failure và rollback

Các listener của Spring Batch giúp quan sát lỗi ghi:

- ItemWriteListener.onWriteError: được gọi khi writer ném exception.
- ChunkListener.afterChunkError: quan sát chunk đi qua nhánh lỗi sau rollback.
- SkipListener.onSkipInWrite: ghi nhận item bị skip ở giai đoạn ghi.
- StepExecutionListener.afterStep: tổng hợp trạng thái Step sau khi kết thúc.

Ví dụ log lỗi ghi:

~~~java
@Component
public class OrderWriteListener
        implements ItemWriteListener<Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderWriteListener.class);

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.debug("Writer returned for {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {

        log.error(
                "Writing chunk failed, itemCount={}",
                items.size(),
                exception);
    }
}
~~~

afterWrite chỉ cho biết lời gọi writer trả về thành công; không phải bằng chứng transaction đã commit. Hãy dùng log transaction và trạng thái StepExecution để phân biệt write failure với commit failure.

Các counter hữu ích:

| Counter | Ý nghĩa |
|---|---|
| writeCount | Số item được ghi theo thống kê Step |
| writeSkipCount | Số item bị skip ở giai đoạn ghi |
| rollbackCount | Số lần rollback được ghi nhận |
| commitCount | Số lần commit |
| status | Trạng thái cuối của Step |
| exitStatus | Mã kết quả của Step |

Counter không thay thế log exception. Để điều tra, nên gắn JobExecution ID, StepExecution ID, partition name nếu có và business key vào log.

## 19. Kiểm thử rollback khi writer thất bại

Một integration test có giá trị nên dùng database transactional thực tế hoặc embedded database, chạy Step và xác nhận dữ liệu sau khi writer ném exception.

Ví dụ ý tưởng:

~~~java
@Test
void rollsBackAllRowsWhenWriterFailsMidChunk() throws Exception {
    ItemWriter<Order> failingWriter = chunk -> {
        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                1L, "A");

        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                2L, "B");

        throw new OrderWriteException("Simulated write failure");
    };

    JobExecution execution = launchJobWith(failingWriter);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    assertEquals(0, countOrders());
}
~~~

Test minh họa giả định hai lệnh JDBC dùng cùng DataSource và transaction manager với Step. Sau rollback, cả hai hàng không còn trong bảng.

Để kiểm tra đúng ranh giới transaction, cần bảo đảm test không tự mở transaction bao ngoài theo cách làm thay đổi hành vi quan sát. Có thể truy vấn database sau khi Job kết thúc bằng connection độc lập.

### Các trường hợp nên kiểm thử

- Writer thất bại trước khi ghi item đầu tiên.
- Writer ghi một phần rồi ném exception.
- Writer lỗi do deadlock và retry thành công.
- Retry hết giới hạn và Step thất bại.
- Item lỗi được skip và các item hợp lệ vẫn được ghi.
- Skip limit bị vượt.
- Writer dùng tài nguyên ngoài transaction.
- Composite writer có delegate thất bại ở giữa.
- Commit thất bại hoặc kết quả commit không xác định.
- Job restart sau rollback và tiếp tục từ checkpoint đúng.

## 20. Những lỗi thường gặp

### Writer bắt exception rồi không ném lại

Framework không biết việc ghi đã thất bại và có thể tiếp tục commit. Hãy truyền exception ra ngoài hoặc chuyển thành exception có nguyên nhân gốc.

### Nghĩ mọi thao tác writer đều rollback

Chỉ tài nguyên tham gia transaction tương ứng mới được rollback. File, email, HTTP và database độc lập có thể giữ side effect.

### Tự commit connection trong writer

Transaction độc lập đã commit không thể bị transaction chunk bên ngoài hoàn tác. Dùng hạ tầng Spring JDBC để tham gia transaction hiện tại.

### Retry writer không idempotent

Writer có thể được gọi lại sau rollback hoặc khi xác định write skip. Side effect có thể bị lặp. Dùng business key, idempotency key hoặc outbox.

### Skip lỗi database diện rộng

Database down hoặc hết dung lượng không phải lỗi của một item. Skip có thể làm mất dữ liệu trên diện rộng. Hãy để Step thất bại và xử lý sự cố hạ tầng.

### Dùng noRollback để tránh Step thất bại

noRollback không có nghĩa item được skip. Nếu writer đã ghi một phần, transaction có thể commit trạng thái không mong muốn.

### Nhầm afterWrite với commit thành công

afterWrite xảy ra sau lời gọi writer nhưng trước khi chunk transaction hoàn tất. Dữ liệu vẫn có thể rollback sau callback này.

### Không kiểm tra writer.close()

Lỗi trong close/finalization có thể làm Step thất bại sau khi các chunk trước đã commit. Những transaction đã commit không thể được rollback chỉ vì close thất bại.

## 21. Quy trình xử lý writer failure

Khi writer thất bại, hãy lần theo các câu hỏi sau:

1. Exception phát sinh trong write() hay trong transaction commit?
2. Writer đã ghi được bao nhiêu dữ liệu trước khi lỗi?
3. Các thao tác ghi có cùng transaction manager và tài nguyên với Step không?
4. Writer có tự mở connection hoặc commit transaction riêng không?
5. Exception có được ném ra ngoài writer không?
6. Rollback classifier có xem exception là lỗi cần rollback không?
7. Exception có thuộc retryable set không?
8. Nếu retry hết giới hạn, exception có được phép skip không?
9. Nếu write skip, framework có thể xác định item gây lỗi không?
10. Writer có side effect ngoài transaction cần idempotency không?
11. StepExecution ghi nhận bao nhiêu rollback, commit và write skip?
12. Sau restart, reader/writer có khôi phục từ checkpoint phù hợp không?

Khi writer dùng tài nguyên transactional đúng cách và exception được truyền tới Spring Batch, rollback giúp hoàn tác toàn bộ thay đổi của chunk trên tài nguyên đó. Với file, API hoặc hệ thống độc lập, cần thêm cơ chế transactional buffer, idempotency, outbox hoặc đối soát. Phân biệt được write failure, commit failure và side effect ngoài transaction là nền tảng để thiết kế Job có thể phục hồi mà không mất hoặc ghi trùng dữ liệu.
