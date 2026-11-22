# Write transaction và commit trong Spring Batch

Trong Spring Batch, **ItemWriter** ghi các item đã được đọc và xử lý vào đích dữ liệu. Với một chunk-oriented Step, writer thường chạy bên trong transaction của chunk. Khi writer và các tài nguyên ghi cùng tham gia transaction đó, Spring Batch có thể commit toàn bộ thay đổi khi chunk thành công hoặc rollback khi chunk thất bại.

Hiểu đúng ranh giới transaction giúp tránh các lỗi như ghi được một phần dữ liệu, commit quá sớm, ghi trùng khi retry hoặc tưởng rằng rollback database có thể hoàn tác một request HTTP. Bài học này giải thích cách Spring Batch quản lý transaction cho writer, thời điểm commit, điều gì xảy ra khi lỗi, cách cấu hình transaction và cách thiết kế thao tác ghi an toàn khi Job restart.

## 1. Transaction trong chunk-oriented Step

Một chunk-oriented Step chia dữ liệu thành từng nhóm. Framework đọc các item, chuyển chúng qua processor nếu có, rồi chuyển nhóm kết quả cho writer. Mỗi chunk là một đơn vị xử lý gắn với transaction.

Ví dụ cấu hình:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("writeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Tham số 100 là commit interval. Spring Batch gom tối đa 100 item đầu vào cho một chunk trước khi thực hiện ghi và hoàn tất transaction của chunk đó. Chunk cuối có thể ít item hơn khi reader hết dữ liệu. Nếu processor lọc item bằng cách trả về null, số item writer nhận sẽ nhỏ hơn số item đã đọc.

~~~mermaid
flowchart TD
    A["Bắt đầu chunk transaction"] --> B["Đọc item"]
    B --> C["Xử lý item"]
    C --> D{"Đạt commit interval hoặc EOF?"}
    D -- "Chưa" --> B
    D -- "Rồi" --> E["ItemWriter.write(chunk)"]
    E --> F{"Ghi thành công?"}
    F -- "Có" --> G["Commit"]
    F -- "Không" --> H["Rollback"]
    G --> I["Chunk tiếp theo"]
    H --> J["Xử lý lỗi / retry / fail"]
~~~

Một Step có thể xử lý hàng nghìn chunk. Vì vậy, transaction của chunk thường ngắn hơn nhiều so với toàn bộ thời gian chạy Job. Các chunk đã commit được giữ lại nếu một chunk sau đó thất bại.

### Vì sao cần transaction cho writer?

Giả sử writer ghi 100 đơn hàng vào database. Nếu ghi thành công 40 đơn rồi gặp lỗi ở đơn thứ 41, transaction giúp rollback các thay đổi của chunk hiện tại nếu tất cả thao tác ghi đó tham gia cùng transaction. Database không để lại 40 dòng đã ghi dở trong chunk.

Nếu không có transaction phù hợp, hệ thống có thể lưu một phần kết quả. Khi Job chạy lại, ứng dụng phải phân biệt dữ liệu đã ghi và dữ liệu chưa ghi, làm tăng độ phức tạp của logic idempotency và đối soát.

## 2. Ranh giới transaction và thứ tự thực thi

Ở mức khái niệm, một chunk được xử lý theo trình tự:

1. Spring Batch bắt đầu transaction của chunk.
2. Reader cung cấp các item đầu vào.
3. Processor xử lý từng item nếu được cấu hình.
4. Writer nhận chunk đầu ra và thực hiện ghi.
5. Framework cập nhật thông tin thực thi và checkpoint theo cơ chế của Step và JobRepository.
6. Transaction commit nếu mọi thao tác cần thiết thành công.

Nếu một exception làm chunk thất bại và được cấu hình để rollback, các thay đổi trong transaction hiện tại được hoàn tác. Spring Batch xử lý lỗi theo chính sách của Step: có thể retry, skip trong giới hạn cho phép hoặc đánh dấu Step thất bại.

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant TM as TransactionManager
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant DB as Database

    S->>TM: Begin transaction
    loop Đọc đến commit interval
        S->>R: read()
        R-->>S: Item
        S->>P: process(item)
        P-->>S: Item đầu ra hoặc null
    end
    S->>W: write(chunk)
    W->>DB: Insert / update theo batch
    DB-->>W: Thành công
    S->>TM: Commit
    TM-->>S: Transaction hoàn tất
~~~

Sơ đồ mô tả luồng điển hình. Chi tiết thời điểm reader được gọi, buffering và checkpoint phụ thuộc loại reader, cấu hình Step và tài nguyên nguồn. Điểm cốt lõi là writer của chunk được thực thi trong phạm vi transaction mà Step quản lý.

### Commit không phải là một lần cho toàn bộ Job

Nếu Job xử lý 1.000.000 item với commit interval 1.000, Job có thể tạo khoảng 1.000 chunk. Mỗi chunk thành công có transaction commit riêng.

Khi chunk thứ 700 thất bại:

- Các chunk từ 1 đến 699 đã commit vẫn tồn tại.
- Chunk hiện tại được rollback nếu lỗi thuộc loại cần rollback và tài nguyên tham gia transaction.
- Các chunk tiếp theo chưa được xử lý.
- Khi restart, Spring Batch dùng metadata và checkpoint để tiếp tục theo trạng thái đã lưu.

Đây là lý do cần phân biệt trạng thái của Job, Step và từng chunk. Một Job FAILED không có nghĩa mọi dữ liệu đã ghi trong Job đều bị rollback.

## 3. Transaction manager được truyền vào Step

Spring Batch sử dụng PlatformTransactionManager để điều khiển transaction. Khi cấu hình chunk-oriented Step, truyền transaction manager vào phương thức chunk:

~~~java
new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
~~~

Transaction manager phải quản lý đúng tài nguyên mà writer sử dụng. Ví dụ:

- JdbcTransactionManager hoặc DataSourceTransactionManager quản lý transaction JDBC cho một DataSource.
- JpaTransactionManager quản lý transaction JPA cho EntityManagerFactory tương ứng.
- JtaTransactionManager có thể phối hợp transaction trên nhiều tài nguyên khi hạ tầng và cấu hình hỗ trợ distributed transaction.

Trong nhiều ứng dụng, Spring Batch metadata và dữ liệu nghiệp vụ dùng chung một database hoặc cùng một transaction manager. Khi đó có thể phối hợp cập nhật metadata và dữ liệu trong cùng ranh giới transaction theo cấu hình. Nếu chúng dùng các datasource hoặc transaction manager khác nhau, không được giả định rằng một commit sẽ tự động làm cả hai bên nguyên tử.

### Ví dụ cấu hình JDBC

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(
        DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Tên lớp transaction manager cụ thể phụ thuộc phiên bản Spring và cấu hình ứng dụng. Điều quan trọng là transaction manager phải gắn với DataSource mà writer dùng để ghi.

### Writer cần dùng cùng tài nguyên được quản lý

Ví dụ JdbcBatchItemWriter:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO processed_order
                (order_id, customer_id, amount)
            VALUES
                (:orderId, :customerId, :amount)
            """)
        .beanMapped()
        .build();
}
~~~

Nếu writer dùng cùng DataSource được transaction manager quản lý, các lệnh JDBC có thể tham gia transaction của chunk. Spring quản lý connection gắn với transaction hiện tại; writer không nên tự mở connection độc lập rồi commit riêng.

Nếu writer tự tạo connection mới, gọi commit thủ công hoặc dùng datasource khác, thao tác ghi có thể nằm ngoài transaction của Step. Khi đó rollback của chunk không nhất thiết hoàn tác dữ liệu đã ghi qua connection độc lập.

## 4. Commit và rollback hoạt động thế nào?

### Khi chunk thành công

Giả sử chunk chứa 100 item và writer ghi tất cả thành công:

1. Các thao tác ghi được thực hiện trên tài nguyên tham gia transaction.
2. Writer kết thúc bình thường.
3. Framework hoàn tất cập nhật trạng thái và checkpoint theo cấu hình.
4. Transaction manager commit.
5. Các thay đổi được commit trở nên bền vững theo đảm bảo của database.

Sau commit, Job có thể chuyển sang chunk tiếp theo.

### Khi writer ném exception

Giả sử writer gặp lỗi constraint khi ghi item thứ 70. Nếu exception làm transaction rollback:

- Các insert hoặc update của chunk hiện tại bị rollback.
- Các thay đổi của chunk trước đó vẫn đã commit.
- Step có thể retry, skip hoặc thất bại theo cấu hình.
- Khi xử lý lại, reader hoặc framework có thể phải cung cấp lại item thuộc chunk chưa commit.

~~~mermaid
flowchart TD
    A["Chunk transaction"] --> B["Writer ghi 100 item"]
    B --> C{"Có lỗi?"}
    C -- "Không" --> D["Commit toàn bộ chunk"]
    C -- "Có" --> E["Rollback chunk hiện tại"]
    E --> F{"Retry / skip được cấu hình?"}
    F -- "Retry" --> G["Thử lại theo policy"]
    F -- "Skip" --> H["Bỏ qua item lỗi theo policy"]
    F -- "Không" --> I["Step FAILED"]
~~~

Rollback chỉ tác động đến các tài nguyên tham gia transaction. Nếu writer đã gửi email hoặc gọi một API bên ngoài, database rollback không thể thu hồi hành động đó.

### Runtime exception và checked exception

Cách Spring transaction xử lý rollback phụ thuộc quy tắc rollback của transaction attribute và loại exception. Theo mặc định của nhiều cấu hình Spring transaction, unchecked exception và Error thường kích hoạt rollback, trong khi checked exception không nhất thiết tự động rollback.

Spring Batch có thể có quy tắc rollback của Step và fault-tolerant configuration. Khi thiết kế writer ném checked exception, cần hiểu transaction attribute đang dùng và kiểm thử hành vi rollback thực tế. Không nên giả định mọi exception đều có cùng hành vi.

Nếu cần quy tắc riêng, có thể cấu hình rollback rules thông qua transaction attribute hoặc chính sách của Step. Chỉ thay đổi quy tắc khi đã hiểu tác động đến dữ liệu của chunk.

## 5. Cấu hình transaction attributes

Ngoài transaction manager, Step có thể sử dụng transaction attributes để điều chỉnh propagation, isolation, timeout và rollback rules.

Ví dụ:

~~~java
@Bean
TransactionAttribute chunkTransactionAttribute() {
    DefaultTransactionAttribute attribute =
        new DefaultTransactionAttribute();

    attribute.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED
    );
    attribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
    );
    attribute.setTimeout(60);

    return attribute;
}
~~~

Gắn transaction attribute vào chunk Step:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        TransactionAttribute chunkTransactionAttribute,
        ItemReader<InputRecord> reader,
        ItemWriter<OutputRecord> writer) {

    return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(200, transactionManager)
        .reader(reader)
        .writer(writer)
        .transactionAttribute(chunkTransactionAttribute)
        .build();
}
~~~

Các thuộc tính có ý nghĩa:

| Thuộc tính | Ý nghĩa |
|---|---|
| Propagation | Quy định cách transaction hiện tại tham gia hoặc tạo transaction khác |
| Isolation | Mức cô lập khi đọc và ghi dữ liệu đồng thời |
| Timeout | Thời gian tối đa transaction được phép chạy theo cấu hình |
| Rollback rules | Quy định loại exception nào làm transaction rollback |

### Propagation

PROPAGATION_REQUIRED là lựa chọn phổ biến: tham gia transaction hiện có hoặc tạo transaction mới nếu chưa có.

PROPAGATION_REQUIRES_NEW tạo transaction độc lập. Nếu một service writer gọi phương thức REQUIRES_NEW, thao tác bên trong có thể commit ngay cả khi transaction chunk bên ngoài rollback. Điều này đôi khi hữu ích cho audit hoặc ghi nhận lỗi, nhưng phải được dùng có chủ đích vì nó phá vỡ giả định mọi thay đổi trong writer đều thuộc cùng một đơn vị commit.

Không nên dùng REQUIRES_NEW cho các thao tác ghi nghiệp vụ chính nếu mong đợi chúng rollback cùng chunk.

### Isolation

Isolation quyết định cách transaction nhìn thấy thay đổi đồng thời từ transaction khác. Ví dụ READ_COMMITTED ngăn đọc dữ liệu chưa commit, nhưng không bảo đảm mọi truy vấn lặp lại trong cùng transaction luôn trả cùng kết quả.

Chọn isolation dựa trên database và nghiệp vụ. Isolation quá cao có thể tăng lock hoặc giảm concurrency; isolation quá thấp có thể gây vấn đề nhất quán trong các truy vấn và cập nhật đồng thời.

### Timeout

Timeout giới hạn thời gian transaction. Giá trị cần phù hợp với kích thước chunk, thời gian ghi batch và tải database. Timeout quá ngắn có thể khiến chunk hợp lệ thất bại; timeout quá dài có thể giữ lock lâu khi có vấn đề.

Không nên tăng timeout để che giấu writer chậm. Hãy đo thời gian xử lý và tối ưu câu SQL, index, batch size hoặc kích thước chunk.

## 6. Commit interval và hiệu năng writer

Commit interval ảnh hưởng trực tiếp đến số lần transaction và lượng dữ liệu trong mỗi chunk.

| Chunk size | Đặc điểm | Đánh đổi |
|---|---|---|
| Nhỏ | Commit thường xuyên, ít item mỗi transaction | Dễ giới hạn phạm vi rollback nhưng tăng chi phí transaction |
| Trung bình | Cân bằng bộ nhớ, batch write và commit | Thường là điểm bắt đầu tốt để đo |
| Lớn | Ít transaction hơn, batch ghi lớn hơn | Tốn bộ nhớ, giữ lock lâu và rollback tốn kém hơn |

Ví dụ:

- 1.000 item với chunk size 100 tạo khoảng 10 chunk.
- 1.000 item với chunk size 500 tạo khoảng 2 chunk.

Số lượng chunk thực tế còn phụ thuộc EOF, filter, skip và cách Step xử lý lỗi.

### Chunk lớn không phải lúc nào cũng nhanh hơn

Chunk lớn có thể cải thiện throughput khi database tối ưu ghi batch, nhưng cũng có thể:

- Giữ transaction và lock lâu hơn.
- Tăng bộ nhớ cần dùng để giữ item.
- Làm rollback tốn nhiều thời gian hơn.
- Tăng lượng dữ liệu cần xử lý lại khi chunk thất bại.
- Gây áp lực lên transaction log hoặc undo log.

Hãy đo thời gian reader, processor, writer, commit và rollback. Nếu writer là nút thắt, có thể tối ưu batch SQL trước khi tăng chunk size.

### Ghi theo batch

JdbcBatchItemWriter sử dụng batch update để gửi nhiều thao tác SQL theo nhóm. Điều này thường hiệu quả hơn gọi một câu insert riêng cho từng item.

Ví dụ SQL có thể dùng named parameters để ánh xạ thuộc tính:

~~~java
.sql("""
    INSERT INTO processed_order
        (order_id, customer_id, amount)
    VALUES
        (:orderId, :customerId, :amount)
    """)
.beanMapped()
~~~

Để batch write có hiệu quả, cần xem xét index, constraint, trigger, network round-trip và cấu hình driver JDBC. Batch size của writer và commit interval của Step có liên quan nhưng không phải lúc nào cũng là một tham số đồng nhất.

## 7. Writer không được tự commit transaction của chunk

Một writer chuẩn nên thực hiện thao tác ghi và để Spring transaction manager quyết định commit hoặc rollback.

Không nên viết:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    Connection connection = dataSource.getConnection();

    try {
        connection.setAutoCommit(false);

        // Ghi dữ liệu...

        connection.commit(); // Commit riêng bên trong writer.
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.close();
    }
}
~~~

Đoạn mã này tự mở connection và commit riêng. Nếu writer commit thành công rồi một thao tác sau đó trong chunk thất bại, transaction bên ngoài không thể rollback dữ liệu đã commit qua connection riêng.

Hãy dùng JdbcTemplate, NamedParameterJdbcTemplate, JdbcBatchItemWriter hoặc DAO sử dụng transaction-bound connection. Để transaction manager của Step quản lý commit.

Ví dụ writer tùy chỉnh dùng JdbcTemplate:

~~~java
public class OrderJdbcWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderJdbcWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        jdbcTemplate.batchUpdate(
            """
            INSERT INTO processed_order(order_id, amount)
            VALUES (?, ?)
            """,
            chunk.getItems(),
            chunk.size(),
            (ps, order) -> {
                ps.setLong(1, order.orderId());
                ps.setBigDecimal(2, order.amount());
            }
        );
    }
}
~~~

JdbcTemplate sử dụng cơ chế quản lý connection của Spring. Khi nó dùng cùng DataSource và transaction manager với Step, các thao tác batch có thể tham gia transaction hiện tại.

## 8. FlatFileItemWriter và transaction

Writer ghi file có hành vi khác writer JDBC. File system không tự tham gia transaction database. Tuy nhiên, FlatFileItemWriter của Spring Batch có cơ chế phối hợp với transaction để quản lý nội dung ghi theo chunk.

Ví dụ:

~~~java
@Bean
FlatFileItemWriter<Order> orderFileWriter() {
    return new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(new FileSystemResource("output/orders.csv"))
        .encoding(StandardCharsets.UTF_8.name())
        .headerCallback(writer ->
            writer.write("orderId,customerId,amount")
        )
        .delimited()
        .delimiter(",")
        .names("orderId", "customerId", "amount")
        .shouldDeleteIfExists(true)
        .build();
}
~~~

Một số điểm cần lưu ý:

- FlatFileItemWriter hỗ trợ cơ chế ghi theo transaction và mặc định phối hợp với transaction của chunk.
- Nếu chunk rollback, phần nội dung đang chờ commit có thể được xử lý theo cơ chế transaction-aware của writer.
- File đã được commit ở các chunk trước vẫn tồn tại nếu chunk sau thất bại.
- File system và database không tự động tạo thành một distributed transaction chỉ vì cùng được gọi trong một writer.
- Nếu dùng writer với transactional behavior bị tắt, cần tự chịu trách nhiệm về việc khôi phục file khi chunk rollback.

Không nên giả định file output và database luôn commit hoặc rollback nguyên tử cùng nhau. Nếu cần tạo file cuối cùng chỉ sau khi toàn bộ Job hoàn tất, có thể ghi vào file tạm theo từng chunk, sau đó dùng một Step hoàn tất để đóng, kiểm tra và đổi tên file. Quy trình cần thiết kế để xử lý được restart và file tạm còn sót.

### Ghi file tạm rồi publish

Một mô hình phổ biến:

~~~mermaid
flowchart TD
    A["Chunk writer ghi file tạm"] --> B["Các chunk commit"]
    B --> C["Step kiểm tra file"]
    C --> D{"Job hoàn tất?"}
    D -- "Có" --> E["Đổi tên / publish file"]
    D -- "Không" --> F["Giữ file tạm để restart hoặc xử lý"]
~~~

Việc đổi tên file thường có tính nguyên tử trong cùng filesystem nếu điều kiện hệ điều hành và filesystem đáp ứng. Khi di chuyển qua filesystem khác hoặc object storage, thao tác có thể không nguyên tử. Hãy dùng tên file có mã lô, kiểm tra file đích và xử lý trường hợp publish bị gọi lại.

## 9. Writer ghi nhiều tài nguyên

Một writer có thể cần ghi cùng dữ liệu vào nhiều đích:

- Database nghiệp vụ.
- File báo cáo.
- Message broker.
- API của hệ thống khác.
- Dịch vụ lưu trữ đối tượng.

Nếu các tài nguyên không dùng chung một transaction manager có khả năng phối hợp distributed transaction, không thể bảo đảm tất cả cùng commit hoặc rollback.

Ví dụ:

1. Writer ghi database thành công.
2. Writer gửi message đến broker thành công.
3. Một thao tác khác thất bại.
4. Transaction database rollback, nhưng message đã được broker nhận.

Hệ thống lúc này có thể ở trạng thái không nhất quán.

### CompositeItemWriter không tạo distributed transaction

CompositeItemWriter giúp gọi nhiều delegate writer trong một luồng:

~~~java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter) {

    return new CompositeItemWriterBuilder<Order>()
        .delegates(databaseWriter, auditWriter)
        .build();
}
~~~

Composite writer chỉ điều phối lời gọi. Nó không tự tạo một transaction phân tán giữa database, file và API. Mỗi delegate cần tham gia transaction phù hợp hoặc có cơ chế bù trừ và idempotency riêng.

### Outbox pattern cho database và message broker

Nếu cần cập nhật database và phát message, có thể ghi cả dữ liệu nghiệp vụ và bản ghi outbox trong cùng một transaction database:

1. Writer cập nhật bảng nghiệp vụ.
2. Writer thêm event vào bảng outbox.
3. Transaction chunk commit.
4. Một publisher riêng đọc outbox và gửi message.
5. Publisher đánh dấu event đã gửi hoặc xử lý retry.

~~~mermaid
flowchart TD
    A["Chunk writer"] --> B["Database transaction"]
    B --> C["Cập nhật dữ liệu nghiệp vụ"]
    B --> D["Thêm bản ghi Outbox"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Message broker"]
~~~

Outbox giúp việc ghi dữ liệu nghiệp vụ và lưu ý định phát message trở nên nguyên tử trong cùng database. Publisher vẫn có thể gửi lặp nếu không nhận được xác nhận, vì vậy consumer cần idempotency hoặc deduplication.

### API bên ngoài và idempotency

Khi writer gọi API, không có transaction database nào tự hoàn tác request đã được hệ thống bên ngoài xử lý. Một số cách giảm rủi ro:

- Gửi idempotency key ổn định theo item hoặc mã lô.
- Lưu trạng thái gửi và kết quả xác nhận.
- Dùng outbox để tách việc commit dữ liệu khỏi việc gửi request.
- Retry có giới hạn và phân loại lỗi tạm thời.
- Có quy trình đối soát khi trạng thái request không rõ ràng.

Không tạo idempotency key mới cho mỗi lần retry nếu muốn hệ thống đích nhận diện đó là cùng một thao tác logic.

## 10. Skip, retry và rollback khi writer gặp lỗi

Writer có thể gặp các loại lỗi khác nhau:

- Vi phạm unique constraint.
- Mất kết nối database.
- Timeout.
- Deadlock.
- Dữ liệu không đáp ứng constraint.
- Lỗi dịch vụ đích.

Không phải lỗi nào cũng nên được xử lý giống nhau.

### Retry cho lỗi tạm thời

Ví dụ lỗi deadlock hoặc một số lỗi truy cập database có thể được retry:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .build();
~~~

Retry thường khiến chunk hoặc một phần thao tác được thực hiện lại tùy loại lỗi và cơ chế fault-tolerant của Step. Writer phải được thiết kế để việc thử lại không gây dữ liệu trùng hoặc side effect lặp không kiểm soát.

### Skip cho lỗi dữ liệu đã xác định

Có thể skip lỗi ghi nếu nghiệp vụ cho phép:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(DuplicateKeyException.class)
    .skipLimit(20)
    .build();
~~~

Tuy nhiên, skip một lỗi writer không đơn giản đồng nghĩa chỉ bỏ qua đúng một dòng. Spring Batch có thể rollback chunk, xác định item gây lỗi và thực hiện lại các thao tác theo cơ chế fault-tolerant để skip đúng item. Writer cần có hành vi phù hợp với quá trình gọi lại.

Chỉ skip lỗi trùng khóa nếu dữ liệu đã tồn tại thực sự tương đương với kết quả mong muốn. Nếu dữ liệu cũ khác dữ liệu mới, bỏ qua duplicate có thể che giấu xung đột nghiệp vụ.

### Phân biệt lỗi tạm thời và lỗi cố định

| Loại lỗi | Cách xử lý thường phù hợp |
|---|---|
| Deadlock tạm thời | Retry có giới hạn |
| Kết nối database gián đoạn | Retry theo chính sách và timeout |
| Dữ liệu sai định dạng | Fail hoặc skip có ghi nhận |
| Vi phạm constraint do dữ liệu sai | Điều tra, fail hoặc skip theo nghiệp vụ |
| API trả lỗi tạm thời | Retry có backoff và idempotency |
| API từ chối do dữ liệu không hợp lệ | Không retry vô hạn |

Không retry lỗi cố định nhiều lần vì thường không làm dữ liệu trở nên hợp lệ. Ngược lại, không skip lỗi hạ tầng tùy tiện vì có thể khiến dữ liệu bị thiếu.

## 11. Giao dịch độc lập bên trong writer

Một số service được gọi từ writer có thể khai báo propagation khác với transaction của chunk.

Ví dụ, một phương thức được đánh dấu REQUIRES_NEW sẽ tạo transaction riêng:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordWriteAttempt(String batchId, String itemId) {
        // Ghi audit trong transaction độc lập.
    }
}
~~~

Nếu audit transaction commit thành công nhưng transaction chunk rollback, audit vẫn tồn tại. Điều này có thể hữu ích để lưu lại sự kiện lỗi hoặc lần thử, nhưng cần hiểu rằng audit đó mô tả một lần thử chứ không phải dữ liệu nghiệp vụ đã commit.

Một số điểm cần cân nhắc:

- REQUIRES_NEW có thể giữ transaction ngoài bị suspend trong khi transaction trong chạy.
- Có thể cần thêm connection từ pool.
- Khi chạy với nhiều item, số transaction độc lập có thể tăng nhanh.
- Audit có thể ghi nhận lần thử nhiều hơn số item cuối cùng được commit.
- Nếu ghi reject record, cần có khóa hoặc mã lô để tránh duplicate khi retry.

Không dùng REQUIRES_NEW chỉ để né lỗi transaction hoặc để bảo đảm một phần writer luôn commit. Hãy xác định rõ dữ liệu nào phải tồn tại độc lập và dữ liệu nào phải rollback cùng chunk.

## 12. Transaction của Tasklet Step và chunk Step

Tasklet Step cũng chạy trong transaction, nhưng đơn vị transaction khác với chunk-oriented Step.

| Loại Step | Đơn vị transaction điển hình |
|---|---|
| Tasklet Step | Mỗi lần gọi Tasklet |
| Chunk-oriented Step | Mỗi chunk |

Nếu Tasklet thực hiện một thao tác cập nhật database và trả về FINISHED, transaction của lần gọi đó được hoàn tất theo cấu hình Step.

Nếu Tasklet trả về CONTINUABLE, framework có thể gọi lại Tasklet theo cơ chế repeat. Mỗi lần gọi có thể có transaction riêng theo cấu hình.

Với chunk-oriented Step, một Job lớn được chia thành nhiều transaction nhỏ. Đây là mô hình phù hợp cho nhập, chuyển đổi và ghi tập dữ liệu lớn.

Không nên đặt một Job xử lý hàng triệu item trong một Tasklet với một transaction duy nhất nếu không có lý do đặc biệt. Transaction dài có thể giữ lock, tăng transaction log và làm restart khó khăn.

## 13. Transaction metadata và dữ liệu nghiệp vụ

Spring Batch lưu metadata trong JobRepository, còn writer thường ghi dữ liệu nghiệp vụ. Hai phần có thể dùng cùng database hoặc các datasource khác nhau.

Nếu JobRepository và writer dùng cùng database, cùng transaction manager và được cấu hình phù hợp, việc cập nhật dữ liệu nghiệp vụ và metadata checkpoint có thể phối hợp trong cùng transaction. Điều này giúp tránh tình huống dữ liệu đã commit nhưng checkpoint chưa được lưu, hoặc ngược lại.

Nếu metadata và dữ liệu nghiệp vụ dùng hai transaction manager độc lập, commit của bên này không tự động commit bên kia. Khi có lỗi giữa hai lần commit, hệ thống có thể cần đối soát hoặc xử lý lặp.

Cần xem xét:

- JobRepository đang dùng datasource nào?
- Writer đang dùng datasource nào?
- Step nhận transaction manager nào?
- Các DAO hoặc service được gọi có tham gia transaction hiện tại không?
- Có propagation REQUIRES_NEW hoặc connection độc lập không?
- Transaction manager có hỗ trợ phối hợp nhiều tài nguyên không?

Không nên mặc định rằng chỉ vì tất cả bean đều chạy trong cùng một Step thì mọi thao tác đều nằm trong một transaction.

## 14. Transaction và restart

Checkpoint của reader, writer và StepExecution giúp Spring Batch khôi phục trạng thái khi Job thất bại. Tuy nhiên, restart chỉ an toàn nếu dữ liệu đã commit và trạng thái đã lưu nhất quán.

Giả sử Job xử lý ba chunk:

~~~text
Chunk 1: write -> commit
Chunk 2: write -> rollback
Chunk 3: chưa chạy
~~~

Khi restart:

- Chunk 1 đã commit nên được giữ.
- Chunk 2 được xử lý lại theo checkpoint và cơ chế reader.
- Chunk 3 được xử lý sau khi chunk 2 thành công.

Nếu writer ghi vào một hệ thống ngoài transaction, có thể xảy ra tình huống hệ thống đích đã nhận dữ liệu của chunk 2 nhưng database rollback. Khi restart, chunk 2 được gửi lại và tạo bản ghi trùng.

Vì vậy, writer nên được thiết kế theo một trong các hướng:

- Idempotent: gửi lại cùng thao tác không tạo kết quả khác.
- Có khóa duy nhất hoặc upsert theo khóa nghiệp vụ.
- Có bảng trạng thái để phát hiện item đã xử lý.
- Có cơ chế outbox hoặc xác nhận của hệ thống đích.
- Có quy trình đối soát khi không thể xác định request đã thành công hay chưa.

### Idempotent database writer

Ví dụ, thay vì insert luôn gây lỗi trùng khóa, có thể dùng câu lệnh upsert phù hợp với database:

~~~sql
-- Cú pháp minh họa kiểu PostgreSQL.
INSERT INTO processed_order(order_id, amount)
VALUES (:orderId, :amount)
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

Upsert chỉ phù hợp khi cập nhật bản ghi cũ bằng dữ liệu mới là đúng nghiệp vụ. Nếu bản ghi trùng phải được xem là lỗi, hãy giữ unique constraint và xử lý duplicate theo chính sách rõ ràng.

## 15. Theo dõi commit và rollback

StepExecution lưu các bộ đếm giúp quan sát hành vi transaction:

| Thuộc tính | Ý nghĩa |
|---|---|
| commitCount | Số lần commit của Step |
| rollbackCount | Số lần rollback |
| readCount | Số item đọc |
| writeCount | Số item ghi |
| filterCount | Số item bị lọc |
| readSkipCount | Số lỗi đọc được skip |
| processSkipCount | Số lỗi xử lý được skip |
| writeSkipCount | Số lỗi ghi được skip |

Ví dụ, nếu rollbackCount tăng cao, cần xem log để tìm nguyên nhân: deadlock, timeout, lỗi constraint hoặc writer có side effect thất bại.

Có thể truy cập thông tin StepExecution trong listener:

~~~java
@Bean
StepExecutionListener transactionMetricsListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Ghi nhận thời điểm bắt đầu.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            log.info(
                "step={}, commits={}, rollbacks={}, writes={}",
                stepExecution.getStepName(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount(),
                stepExecution.getWriteCount()
            );
            return null;
        }
    };
}
~~~

Listener minh họa cách ghi nhận thống kê khi Step kết thúc. Trong ứng dụng thực tế, nên dùng logging framework và metrics phù hợp, đồng thời tránh ghi dữ liệu nhạy cảm của item.

Các bộ đếm giúp phát hiện xu hướng, nhưng không thay thế đối soát dữ liệu nghiệp vụ. Ví dụ writeCount bằng số item dự kiến không đảm bảo mọi bản ghi đúng nếu writer đã ánh xạ sai cột hoặc ghi sai giá trị.

## 16. Kiểm thử transaction của writer

Kiểm thử transaction nên xác nhận cả trường hợp commit và rollback. Không chỉ kiểm tra writer được gọi hay không.

### Kiểm thử commit

Một test tích hợp có thể:

1. Chuẩn bị database test.
2. Khởi chạy Step với một số item đầu vào.
3. Đợi Job hoàn tất.
4. Truy vấn bảng đích.
5. Xác nhận toàn bộ item hợp lệ đã được ghi.
6. Xác nhận commitCount và writeCount phù hợp.

### Kiểm thử rollback

Tạo writer hoặc constraint khiến một chunk thất bại. Sau khi Step thất bại, truy vấn database để xác nhận không còn dữ liệu dở dang từ chunk rollback.

Ví dụ tình huống:

~~~text
Chunk 1: 100 item -> commit
Chunk 2: 100 item -> writer ném exception
Kết quả mong đợi:
  - Chunk 1 vẫn tồn tại.
  - Chunk 2 không để lại dữ liệu một phần.
  - Step ghi nhận rollback hoặc thất bại theo policy.
~~~

Nếu Step được cấu hình retry, cần kiểm tra số lần thử và kết quả cuối. Nếu skip, cần xác nhận item bị skip được ghi nhận và các item hợp lệ còn lại được xử lý.

### Kiểm thử side effect ngoài transaction

Nếu writer gọi API hoặc message broker, cần test tình huống:

- API đã nhận request nhưng writer chưa nhận được response.
- Database rollback sau khi API thành công.
- Job restart và gửi lại item.
- Hệ thống đích nhận cùng idempotency key nhiều lần.

Kiểm thử phải xác nhận side effect không tạo kết quả nghiệp vụ trùng hoặc sai.

### Dùng test transaction đúng cách

Spring test có thể tự bọc test method trong transaction và rollback khi test kết thúc. Điều này hữu ích nhưng có thể làm kết quả quan sát khác với transaction thực tế của Job nếu không kiểm soát rõ.

Với kiểm thử batch, cần phân biệt transaction của test, transaction của JobRepository và transaction của Step. Dùng JobLauncherTestUtils hoặc khởi chạy Job trong test context với cấu hình tương tự ứng dụng để kiểm tra hành vi thực tế.

## 17. Các lỗi thiết kế thường gặp

### Tự commit bên trong writer

Writer commit qua connection riêng khiến transaction chunk không thể rollback thao tác đó. Dùng tài nguyên transaction-bound do Spring quản lý.

### Dùng sai transaction manager

Nếu Step dùng transaction manager của datasource A nhưng writer ghi datasource B, thao tác ghi có thể không tham gia transaction của Step. Hãy xác nhận datasource và transaction manager khớp nhau.

### Cho rằng mọi side effect đều rollback

Email, HTTP request, message đã gửi hoặc file đã được hệ thống khác đọc không tự biến mất khi database rollback. Dùng outbox, idempotency hoặc quy trình bù trừ.

### Chunk quá lớn

Chunk lớn có thể giữ lock lâu, tăng bộ nhớ và làm rollback tốn kém. Chọn commit interval dựa trên đo lường.

### Retry writer không idempotent

Writer được gọi lại có thể ghi trùng hoặc gửi cùng request nhiều lần. Thiết kế thao tác ghi có thể lặp lại an toàn.

### Skip duplicate mà không kiểm tra ý nghĩa dữ liệu

Một duplicate key có thể là bản ghi đã xử lý hoặc là xung đột dữ liệu. Chỉ skip khi nghiệp vụ xác định hai kết quả tương đương.

### Dùng REQUIRES_NEW không có chủ đích

Transaction độc lập có thể commit dù chunk rollback. Chỉ dùng khi dữ liệu cần được lưu độc lập và đã xử lý hệ quả khi retry.

### Nhầm commit database với publish file

Ghi database thành công không có nghĩa file cũng được publish nguyên tử. Tách bước ghi file tạm và publish cuối cùng nếu cần.

### Không kiểm thử rollback

Một writer có thể chạy thành công trong test dữ liệu hợp lệ nhưng để lại dữ liệu một phần khi lỗi. Cần tạo lỗi có kiểm soát để xác nhận transaction thực sự hoạt động.

## 18. Quy trình thiết kế writer transaction an toàn

Khi xây dựng writer mới, có thể thực hiện theo trình tự:

1. **Xác định đích:** database, file, queue, API hoặc nhiều tài nguyên.
2. **Chọn transaction manager:** xác nhận manager quản lý đúng datasource và resource cần thiết.
3. **Xác định chunk size:** chọn commit interval dựa trên khối lượng, thời gian ghi và khả năng rollback.
4. **Dùng transaction-bound API:** tránh tự mở connection và commit độc lập trong writer.
5. **Phân loại lỗi:** xác định lỗi nào retry, skip hoặc làm Step thất bại.
6. **Thiết kế idempotency:** bảo đảm retry và restart không tạo dữ liệu trùng.
7. **Xử lý side effect ngoài transaction:** cân nhắc outbox, publish sau commit hoặc cơ chế bù trừ.
8. **Thiết kế checkpoint:** bảo đảm reader và metadata khôi phục đúng sau rollback.
9. **Ghi metrics:** theo dõi commit, rollback, write count và thời gian ghi.
10. **Kiểm thử:** xác nhận commit, rollback, retry, skip và restart trên database test.

## 19. Những điểm cần nhớ

- Chunk-oriented Step sử dụng transaction theo từng chunk, không phải một transaction duy nhất cho toàn bộ Job.
- ItemWriter thực hiện ghi trong phạm vi transaction của chunk khi dùng đúng tài nguyên và transaction manager.
- Writer không nên tự mở connection độc lập hoặc tự commit.
- Commit làm bền vững các thay đổi của chunk; rollback hoàn tác thay đổi trên các tài nguyên tham gia transaction.
- Chunk đã commit vẫn được giữ nếu chunk sau thất bại.
- Commit interval ảnh hưởng đến hiệu năng, bộ nhớ, lock và phạm vi rollback.
- Transaction attributes điều khiển propagation, isolation, timeout và rollback rules.
- REQUIRES_NEW có thể commit độc lập với transaction chunk.
- File, API và message broker không mặc nhiên cùng transaction với database.
- Retry và restart yêu cầu writer có idempotency hoặc cơ chế đối soát phù hợp.
- Outbox là một cách phối hợp cập nhật database và phát message đáng tin cậy hơn.
- Theo dõi commitCount, rollbackCount và writeCount; kiểm thử cả commit lẫn rollback.

Khi hiểu rõ transaction boundary của chunk và bảo đảm writer tham gia đúng transaction manager, Spring Batch có thể ghi dữ liệu theo nhóm một cách nhất quán, xử lý lỗi có kiểm soát và khởi động lại an toàn hơn.

