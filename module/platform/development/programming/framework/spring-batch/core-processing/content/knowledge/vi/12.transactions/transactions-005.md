# Transaction manager cho database

Trong Spring Batch, transaction manager xác định cách một Step bắt đầu, commit và rollback transaction khi xử lý dữ liệu. Với database writer, transaction manager phải quản lý đúng DataSource hoặc persistence resource mà writer sử dụng. Khi cấu hình đúng, các thao tác ghi trong một chunk có thể được commit cùng nhau hoặc rollback cùng nhau nếu có lỗi.

Transaction manager cũng ảnh hưởng đến cách checkpoint và metadata được lưu. Vì vậy, khi xây dựng batch job, cần phân biệt transaction của business database với transaction mà JobRepository dùng để lưu trạng thái thực thi.

## 1. Transaction manager làm nhiệm vụ gì?

Spring quản lý transaction thông qua abstraction PlatformTransactionManager. Abstraction này cho phép framework bắt đầu transaction, tham gia transaction hiện có, commit hoặc rollback mà không buộc code nghiệp vụ phải tự gọi lệnh BEGIN, COMMIT hay ROLLBACK.

Với Spring Batch, transaction manager được Step sử dụng để điều khiển transaction của từng đơn vị xử lý. Trong chunk-oriented Step, một chunk thường là một transaction:

~~~text
Begin transaction
      |
      v
Read items
      |
      v
Process items
      |
      v
Write chunk to database
      |
      v
Update checkpoint / stream state
      |
      v
Commit transaction
~~~

Nếu writer gặp lỗi làm transaction rollback, các thay đổi trên tài nguyên tham gia transaction đó được hoàn tác. Các chunk đã commit trước đó vẫn được giữ.

Transaction manager không tự quyết định quy tắc nghiệp vụ cần ghi dữ liệu gì. Nó quản lý ranh giới transaction và phối hợp với transaction resource như JDBC Connection hoặc JPA EntityManager.

## 2. PlatformTransactionManager và các implementation thường dùng

PlatformTransactionManager là interface chung của Spring cho transaction imperative. Các implementation phổ biến với database gồm:

| Transaction manager | Resource được quản lý | Trường hợp thường dùng |
|---|---|---|
| DataSourceTransactionManager | JDBC DataSource | JDBC và JdbcTemplate |
| JdbcTransactionManager | JDBC DataSource | JDBC; bổ sung dịch lỗi SQL ở ranh giới transaction |
| JpaTransactionManager | JPA EntityManagerFactory | Spring Data JPA hoặc EntityManager |
| JtaTransactionManager | JTA transaction coordinator | Phối hợp nhiều resource có hỗ trợ distributed transaction |

Chọn implementation theo cách writer truy cập database:

- Nếu writer dùng JdbcBatchItemWriter, JdbcTemplate hoặc JDBC trực tiếp, transaction manager cần quản lý đúng DataSource.
- Nếu writer dùng JPA hoặc Spring Data repository, JpaTransactionManager thường là lựa chọn phù hợp với EntityManagerFactory tương ứng.
- Nếu một transaction phải phối hợp nhiều resource độc lập, cần đánh giá JTA hoặc một thiết kế khác như outbox/saga. Không giả định rằng hai transaction manager cục bộ tự tạo thành một transaction nguyên tử.

### DataSourceTransactionManager và JdbcTransactionManager

DataSourceTransactionManager quản lý transaction cho một JDBC DataSource. Nó bind JDBC Connection vào thread hiện tại để các thao tác JDBC tham gia transaction đó khi dùng cùng DataSource và cơ chế truy cập được Spring hỗ trợ.

JdbcTransactionManager là biến thể dành cho JDBC, có khả năng dịch một số SQLException phát sinh ở các thao tác commit/rollback sang hệ thống exception của Spring. Với ứng dụng Spring hiện đại, có thể chọn một trong hai tùy phiên bản framework và convention của dự án.

Ví dụ cấu hình JDBC transaction manager:

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Nếu phiên bản Spring đang dùng chưa có JdbcTransactionManager, có thể dùng DataSourceTransactionManager:

~~~java
@Bean
PlatformTransactionManager batchTransactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
~~~

Không tạo transaction manager mới tùy tiện cho mỗi writer. Các thành phần cần tham gia cùng transaction phải dùng đúng manager và resource theo cấu hình của Step.

## 3. Gắn transaction manager vào chunk-oriented Step

Trong Spring Batch 5, transaction manager được truyền trực tiếp vào phương thức chunk của StepBuilder.

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager batchTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, batchTransactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Trong ví dụ:

- chunk(100, batchTransactionManager) cấu hình commit interval là 100 và chọn transaction manager cho chunk.
- Reader cung cấp từng item.
- Processor biến đổi hoặc lọc item.
- Writer ghi các item còn lại trong chunk.
- Framework quản lý transaction theo từng chunk.

Nếu chunk xử lý 100 item, writer ghi database trong transaction hiện tại. Khi tất cả thao tác hoàn tất, framework commit. Nếu một lỗi yêu cầu rollback xảy ra trước commit, transaction manager rollback chunk theo quy tắc đã cấu hình.

Với Spring Batch 4, cách cấu hình StepBuilder có thể khác, đặc biệt cách truyền transaction manager vào chunk. Hãy dùng API đúng phiên bản thay vì sao chép nguyên ví dụ Batch 5 vào dự án cũ.

## 4. Ví dụ writer JDBC tham gia transaction của Step

JdbcBatchItemWriter sử dụng DataSource để ghi nhiều item trong chunk. Khi DataSource của writer được quản lý bởi transaction manager của Step, các lệnh JDBC có thể tham gia cùng transaction.

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                insert into orders (id, customer_id, amount)
                values (:id, :customerId, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Cấu hình Step:

~~~java
@Bean
Step writeOrdersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        JdbcBatchItemWriter<Order> orderWriter) {

    return new StepBuilder("writeOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

Cần bảo đảm hai bean thực sự dùng cùng DataSource:

- Transaction manager được tạo với DataSource đích.
- JdbcBatchItemWriter được cấu hình với chính DataSource đó.
- Không tự mở Connection mới bằng DriverManager trong writer.
- Không tự commit Connection trong writer.

Nếu writer tự lấy một JDBC Connection độc lập ngoài cơ chế Spring, thao tác ghi có thể không tham gia transaction của Step. Khi đó, rollback chunk không hoàn tác được phần ghi trên connection độc lập.

## 5. Transaction manager với JPA writer

Nếu writer dùng JPA hoặc Spring Data JPA, transaction manager phải quản lý EntityManagerFactory tương ứng.

Ví dụ:

~~~java
@Bean
PlatformTransactionManager orderJpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

Một writer có thể gọi repository:

~~~java
public class OrderJpaWriter implements ItemWriter<Order> {

    private final OrderRepository orderRepository;

    public OrderJpaWriter(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        orderRepository.saveAll(chunk.getItems());
    }
}
~~~

Step dùng JPA transaction manager:

~~~java
@Bean
Step persistOrdersStep(
        JobRepository jobRepository,
        @Qualifier("orderJpaTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderJpaWriter) {

    return new StepBuilder("persistOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderJpaWriter)
            .build();
}
~~~

Trong một số cấu hình, Spring Data repository tham gia transaction do JpaTransactionManager quản lý vì chúng dùng cùng EntityManagerFactory và transaction-bound EntityManager. Nếu repository tự dùng transaction manager khác hoặc một EntityManagerFactory khác, cần kiểm tra lại cách tham gia transaction.

Với JPA, việc gọi saveAll() không nhất thiết đồng nghĩa SQL đã được gửi ngay lập tức. EntityManager có thể trì hoãn flush cho đến thời điểm phù hợp. Lỗi constraint có thể xuất hiện ở flush hoặc commit, không nhất thiết ngay tại dòng saveAll().

## 6. Transaction của chunk khác transaction của toàn Job

Một Job có thể chứa nhiều Step. Mỗi Step có transaction riêng theo cấu hình. Với chunk-oriented Step, transaction thường được tạo và kết thúc cho từng chunk.

Ví dụ Job có ba Step:

~~~text
Job
 |
 +--> Step A
 |      chunk 1 -> commit
 |      chunk 2 -> commit
 |
 +--> Step B
 |      chunk 1 -> commit
 |      chunk 2 -> rollback
 |
 +--> Step C (không chạy theo flow thành công)
~~~

Nếu Step B thất bại, các chunk đã commit trong Step A vẫn tồn tại. Transaction manager của Step B không tự rollback các transaction đã hoàn tất của Step A.

Do đó, một Job nhiều Step không mặc nhiên là một transaction database duy nhất. Nếu nghiệp vụ yêu cầu hoàn tác nhiều Step đã commit trước đó, cần thiết kế compensation, staging hoặc một quy trình nghiệp vụ riêng.

## 7. Transaction manager của Step và JobRepository

JobRepository lưu metadata của Spring Batch như JobInstance, JobExecution, StepExecution và ExecutionContext. Các thao tác cập nhật metadata cũng cần transaction.

Cần phân biệt:

- **Step transaction manager:** quản lý transaction của chunk hoặc tasklet, thường gắn với business database.
- **JobRepository transaction manager:** quản lý transaction lưu metadata, có thể dùng cùng hoặc khác transaction manager của business database tùy cấu hình.

Nếu business data và JobRepository dùng cùng database và cùng transaction resource, chúng có thể tham gia cùng transaction trong cấu hình phù hợp. Khi đó, business writes và checkpoint có thể commit hoặc rollback cùng nhau.

Nếu JobRepository dùng database riêng, hai nơi không tự động có tính nguyên tử:

~~~text
Chunk processing
    |
    +--> Business database transaction
    |
    +--> JobRepository metadata transaction
~~~

Có thể xảy ra tình huống business data đã commit nhưng metadata chưa được cập nhật, hoặc metadata và dữ liệu nghiệp vụ không ở cùng trạng thái sau một lỗi hệ thống. Cần hiểu rõ transaction manager nào được dùng cho từng resource và thiết kế khả năng phục hồi tương ứng.

Không giả định rằng chỉ vì JobRepository và writer cùng xuất hiện trong một Step thì chúng chắc chắn dùng chung transaction. Hãy kiểm tra cấu hình thực tế.

## 8. Cấu hình nhiều DataSource

Một ứng dụng có thể dùng một database cho dữ liệu nghiệp vụ và một database khác cho metadata Spring Batch.

Ví dụ:

- batchMetaDataSource lưu BATCH_JOB_INSTANCE, BATCH_JOB_EXECUTION và các bảng metadata khác.
- businessDataSource lưu orders, customers và các bảng nghiệp vụ.

Có thể khai báo transaction manager riêng:

~~~java
@Bean
@Primary
PlatformTransactionManager businessTransactionManager(
        @Qualifier("businessDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean
PlatformTransactionManager batchMetadataTransactionManager(
        @Qualifier("batchMetaDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Khi cấu hình Spring Batch, cần chỉ rõ manager nào dùng cho JobRepository và manager nào dùng cho Step ghi business data theo API cấu hình của phiên bản đang dùng. Ví dụ Step có thể nhận businessTransactionManager trong chunk(...).

Không dựa vào @Primary để suy đoán mọi thành phần sẽ chọn đúng manager. Khi có nhiều bean cùng kiểu PlatformTransactionManager, nên dùng @Qualifier rõ ràng tại các điểm cấu hình.

### Sơ đồ hai database

~~~text
Spring Batch Job
      |
      +---------------------------+
      |                           |
      v                           v
JobRepository                 Business Step
      |                           |
      v                           v
batchMetaDataSource           businessDataSource
      |                           |
      v                           v
BATCH_* tables                orders / customers
      |                           |
      v                           v
metadata transaction          chunk transaction
~~~

Hai transaction manager cục bộ không tự phối hợp commit nguyên tử. Nếu một transaction commit còn transaction kia thất bại, ứng dụng phải có cách phát hiện và xử lý trạng thái không đồng bộ.

## 9. Dùng một transaction manager hay nhiều transaction manager?

Không có cấu hình duy nhất phù hợp cho mọi ứng dụng. Hãy dựa vào resource thực tế.

| Kiến trúc | Cách tiếp cận thường dùng |
|---|---|
| JobRepository và business tables cùng một DataSource | Một transaction manager phù hợp có thể quản lý chunk và metadata theo cấu hình |
| Business JDBC writer trên một DataSource | DataSourceTransactionManager hoặc JdbcTransactionManager cho DataSource đó |
| JPA writer trên một EntityManagerFactory | JpaTransactionManager tương ứng |
| Metadata và business data ở hai DataSource | Cấu hình rõ manager cho repository và Step; thiết kế consistency/recovery |
| Một chunk ghi nhiều database độc lập | Đánh giá JTA hoặc tách quy trình bằng outbox/staging |
| Ghi database và gọi API ngoài | Transaction database cộng idempotency/outbox/compensation |

JTA có thể phối hợp nhiều resource nếu database, driver và môi trường hỗ trợ XA và được cấu hình đúng. Distributed transaction làm tăng độ phức tạp vận hành và có chi phí riêng. Với nhiều hệ thống hiện đại, outbox hoặc quy trình eventual consistency có thể đơn giản và dễ phục hồi hơn.

## 10. Propagation và transaction hiện có

Spring transaction manager sử dụng transaction propagation để quyết định cách một phương thức tham gia transaction hiện có.

Các propagation mode thường gặp:

- **REQUIRED:** tham gia transaction hiện có; nếu chưa có thì tạo transaction mới.
- **REQUIRES_NEW:** tạm treo transaction hiện tại và tạo transaction mới.
- **SUPPORTS:** tham gia nếu có transaction; nếu không thì chạy không có transaction.
- **MANDATORY:** yêu cầu phải có transaction hiện tại.
- **NOT_SUPPORTED:** tạm treo transaction hiện tại và chạy không có transaction.
- **NEVER:** yêu cầu không có transaction hiện tại.

Với writer gọi service có @Transactional, mặc định REQUIRED thường khiến service tham gia transaction chunk đang chạy, nếu dùng đúng transaction manager và resource.

Ví dụ:

~~~java
@Service
public class OrderWriteService {

    private final OrderRepository repository;

    public OrderWriteService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void saveOrders(List<Order> orders) {
        repository.saveAll(orders);
    }
}
~~~

Nếu method được gọi trong transaction chunk và cùng transaction manager, thao tác saveOrders thường tham gia transaction đó.

Nếu đặt REQUIRES_NEW, service có thể commit độc lập với chunk. Khi chunk rollback, dữ liệu đã commit trong transaction mới không tự rollback theo transaction ngoài. Điều này có thể phá vỡ giả định rằng toàn bộ chunk là một đơn vị nguyên tử.

Chỉ dùng REQUIRES_NEW khi có chủ đích rõ ràng, chẳng hạn ghi audit độc lập mà nghiệp vụ chấp nhận giữ lại kể cả khi chunk thất bại. Đừng dùng nó như một cách sửa lỗi transaction chưa được cấu hình đúng.

## 11. Rollback khi writer gặp lỗi

Khi writer ném exception, Spring Batch xử lý theo cấu hình transaction và fault tolerance của Step.

Nếu lỗi làm transaction rollback:

- Các thao tác database tham gia transaction hiện tại được hoàn tác.
- Checkpoint của chunk không được xem là đã commit thành công.
- Step có thể retry hoặc skip item nếu cấu hình cho phép.
- Nếu lỗi không được xử lý, Step có thể kết thúc với trạng thái FAILED.

Ví dụ cấu hình retry cho một lỗi tạm thời:

~~~java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Tên và API fault-tolerance có thể khác theo phiên bản Spring Batch. Cần chọn exception phù hợp và xác định rõ retry có an toàn với writer hay không.

Không phải mọi exception đều mặc định có cùng rollback behavior. Spring transaction có quy tắc rollback theo loại exception và có thể được tùy chỉnh. Kiểm tra cấu hình rollback khi dùng exception tùy chỉnh hoặc khi muốn một loại lỗi không làm rollback.

Nếu writer gọi API bên ngoài rồi ném lỗi, transaction database có thể rollback nhưng API đã thực hiện hành động. Đây là lý do writer ngoài database cần idempotency hoặc một cơ chế phát hành sau commit.

## 12. Isolation level và lock

Transaction manager cũng có thể điều khiển isolation level cho transaction. Isolation ảnh hưởng cách transaction nhìn thấy dữ liệu từ transaction khác và cách database xử lý lock.

Các mức isolation thường gặp:

| Isolation | Đặc điểm khái quát |
|---|---|
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit |
| REPEATABLE_READ | Dữ liệu đã đọc trong transaction được bảo vệ khỏi một số thay đổi đồng thời |
| SERIALIZABLE | Mức cô lập chặt hơn, có thể giảm concurrency và tăng lock/contention |

Mức isolation thực tế và hành vi chi tiết phụ thuộc database. Ví dụ, một số database triển khai isolation bằng MVCC và có khác biệt so với cách hiểu lý thuyết.

Với batch job, transaction quá dài có thể giữ lock lâu và ảnh hưởng workload trực tuyến. Chunk size nhỏ hơn thường làm transaction ngắn hơn, nhưng tăng số lần commit. Hãy cân nhắc isolation, index, truy vấn, commit interval và tải đồng thời.

Có thể cấu hình isolation/timeout cho transaction của Step bằng các API transaction attribute tương ứng trong phiên bản Spring Batch đang dùng. Không nâng isolation lên SERIALIZABLE chỉ để “chắc chắn hơn” nếu chưa đo tác động và chưa xác định vấn đề consistency cần giải quyết.

## 13. Tasklet Step cũng cần transaction manager

Tasklet Step không dùng ItemReader/ItemWriter theo chunk, nhưng vẫn có thể chạy trong transaction. Khi cấu hình Step bằng tasklet, truyền transaction manager để Spring Batch quản lý transaction của lần gọi Tasklet theo cấu hình.

~~~java
@Bean
Step archiveOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveOrdersTasklet) {

    return new StepBuilder("archiveOrdersStep", jobRepository)
            .tasklet(archiveOrdersTasklet, transactionManager)
            .build();
}
~~~

Nếu Tasklet thực hiện một câu SQL hoặc nhiều thao tác database, chúng có thể tham gia transaction này khi dùng đúng resource.

Tasklet có thể được gọi lặp tùy RepeatStatus. Mỗi lần thực thi cần hiểu rõ transaction boundary tương ứng. Không nên giả định toàn bộ một quy trình dài bên trong Tasklet tự động có thể rollback mọi tác động bên ngoài.

## 14. Không tự mở connection và commit thủ công

Một lỗi thường gặp là writer tự tạo JDBC connection bằng DriverManager rồi commit hoặc close connection bên trong write().

~~~java
// Tránh cách làm này trong writer tham gia transaction của Step.
Connection connection = DriverManager.getConnection(url, user, password);
connection.setAutoCommit(false);
// Thực hiện INSERT...
connection.commit();
connection.close();
~~~

Connection này có thể nằm ngoài transaction do Spring quản lý. Khi Spring Batch rollback chunk, các lệnh đã commit thủ công không được hoàn tác.

Hãy inject JdbcTemplate, DataSource đã cấu hình hoặc dùng JdbcBatchItemWriter. Nếu cần JDBC trực tiếp, dùng cơ chế lấy Connection gắn với transaction Spring, chẳng hạn DataSourceUtils, và không tự commit/close resource mà transaction manager sở hữu.

Tương tự với JPA, không tự tạo EntityManager độc lập nếu muốn tham gia transaction của Step. Dùng EntityManager hoặc Spring Data repository được quản lý bởi Spring và cùng EntityManagerFactory.

## 15. Transaction manager và thread

Transaction imperative của Spring thường gắn với thread thực thi. Một transaction của chunk không tự lan sang thread khác chỉ vì code khởi chạy một tác vụ bất đồng bộ.

Ví dụ, nếu writer gửi việc ghi dữ liệu sang một executor khác rồi trả về ngay, thread mới không mặc nhiên tham gia transaction chunk của thread gọi. Step có thể commit trước khi tác vụ ghi hoàn tất.

Không khởi chạy công việc ghi bất đồng bộ từ writer nếu chưa có thiết kế rõ ràng về:

- Thời điểm ghi hoàn tất so với thời điểm chunk commit.
- Cách truyền transaction context hoặc dùng transaction riêng.
- Cách chờ và xử lý lỗi của các tác vụ con.
- Idempotency và khả năng retry.
- Cách đồng bộ checkpoint với kết quả ghi thực tế.

Với xử lý song song trong Spring Batch, hãy dùng mô hình concurrency/partitioning phù hợp và hiểu transaction boundary của từng worker. Mỗi worker/partition thường cần transaction và StepExecution riêng theo cấu hình.

## 16. Kiểm tra cấu hình transaction manager

Khi database writer không rollback như mong đợi, hãy kiểm tra từ cấu hình đến resource thực tế.

1. Xác định writer đang dùng JDBC, JPA hay một client riêng.
2. Xác định DataSource hoặc EntityManagerFactory mà writer dùng.
3. Kiểm tra transaction manager của Step quản lý đúng resource đó.
4. Nếu có nhiều PlatformTransactionManager, kiểm tra @Qualifier và bean được inject.
5. Kiểm tra service được gọi từ writer có tham gia transaction hiện tại hay tự tạo transaction mới.
6. Xác nhận writer không tự mở connection, tự commit hoặc ghi qua một resource khác.
7. Kiểm tra rollback rules, propagation và isolation.
8. Xác định JobRepository dùng transaction manager và DataSource nào.
9. Kiểm tra log SQL, transaction debug log và trạng thái database sau rollback.
10. Kiểm thử lỗi xảy ra giữa chunk để xác nhận mọi thay đổi cần rollback thực sự được hoàn tác.

Không dùng việc Job kết thúc FAILED làm bằng chứng duy nhất rằng dữ liệu đã rollback. Job có thể thất bại sau khi một số chunk đã commit hoặc sau khi một tác động ngoài transaction đã xảy ra.

## 17. Kiểm thử transaction của Step

Một integration test có thể chạy Step với dữ liệu thử nghiệm, cố ý làm writer ném lỗi ở một item và xác nhận transaction behavior.

Ví dụ kịch bản:

~~~text
Chunk size = 3
Input = [A, B, C, D, E, F]

Chunk 1:
  write A, B, C
  commit

Chunk 2:
  write D
  writer lỗi tại E
  rollback

Kết quả mong đợi nếu tất cả ghi vào cùng transaction:
  A, B, C tồn tại
  D và E không được commit
  Step FAILED
~~~

Khi kiểm thử, nên dùng database thật trong môi trường test hoặc embedded database phù hợp để xác nhận transaction thực tế. Mock transaction manager chỉ kiểm tra tương tác, không chứng minh JDBC/JPA resource đã tham gia cùng transaction.

Các tình huống nên có:

- Ghi thành công một chunk.
- Lỗi trong writer làm rollback toàn chunk.
- Retry được gọi lại và không tạo dữ liệu trùng.
- Skip hoạt động đúng khi được cấu hình.
- Hai Step dùng transaction manager đúng resource.
- Metadata và business data được xử lý theo kiến trúc một hoặc nhiều database.
- Tasklet rollback khi một thao tác database thất bại.

## 18. Các lỗi cấu hình thường gặp

**Transaction manager dùng sai DataSource.** Writer ghi bằng DataSource A nhưng Step dùng manager quản lý DataSource B. Lệnh ghi không tham gia transaction dự kiến.

**Có nhiều transaction manager nhưng không dùng Qualifier.** Spring có thể inject nhầm bean hoặc ứng dụng dựa vào @Primary trong khi Step cần manager khác.

**JobRepository và business database bị coi là một transaction.** Hai DataSource khác nhau không tự commit/rollback nguyên tử.

**Tự commit trong writer.** Một phần chunk có thể đã bền vững dù phần còn lại thất bại.

**Dùng REQUIRES_NEW không có chủ đích.** Dữ liệu có thể commit độc lập và không rollback cùng chunk.

**Bất đồng bộ hóa việc ghi.** Thread mới không tự tham gia transaction của chunk; framework có thể commit trước khi ghi hoàn tất.

**Chunk quá lớn hoặc transaction quá dài.** Lock, connection và tài nguyên database có thể bị giữ lâu, làm giảm khả năng phục vụ workload khác.

**Giả định mọi side effect đều rollback.** File, email, HTTP API và message broker thường nằm ngoài transaction database.

## 19. Quy trình lựa chọn transaction manager

Khi thiết kế một Spring Batch Step ghi database, hãy đi theo trình tự:

1. Xác định công nghệ ghi: JDBC, JPA hay resource khác.
2. Xác định DataSource hoặc EntityManagerFactory chính xác.
3. Chọn transaction manager quản lý resource đó.
4. Truyền manager vào chunk(...) hoặc tasklet(...) của Step.
5. Bảo đảm writer/service dùng cùng resource và tham gia transaction Spring.
6. Xác định JobRepository dùng manager nào để lưu metadata.
7. Nếu metadata và business data ở hai resource, thiết kế consistency, restart và reconciliation.
8. Chọn commit interval và isolation dựa trên tải, lock và yêu cầu nghiệp vụ.
9. Kiểm thử rollback, retry và restart bằng database trong môi trường test.

Với một Step JDBC đơn giản, JdbcTransactionManager hoặc DataSourceTransactionManager quản lý cùng DataSource của JdbcBatchItemWriter thường là cấu hình dễ hiểu. Với Step JPA, dùng JpaTransactionManager gắn với EntityManagerFactory mà repository sử dụng. Với nhiều database, cấu hình manager rõ ràng và không dựa vào giả định về transaction nguyên tử.

Transaction manager là thành phần nối Spring Batch với transaction resource của database. Khi Step dùng đúng manager, writer tham gia đúng transaction và checkpoint được lưu theo cấu hình nhất quán, mỗi chunk có thể trở thành đơn vị commit/rollback đáng tin cậy. Điều đó giúp batch job xử lý dữ liệu theo từng phần, phục hồi khi lỗi và phối hợp an toàn với các workload khác trên database.

