# Retry cùng transaction rollback trong Spring Batch

Trong một chunk-oriented Step, Spring Batch xử lý nhiều item trong cùng một transaction. Nếu một thao tác gặp lỗi tạm thời như database deadlock, lock timeout hoặc dịch vụ từ xa gián đoạn, ứng dụng có thể cần thử lại. Nhưng việc thử lại chỉ an toàn khi hiểu transaction hiện tại đang ở trạng thái nào và các thay đổi của lần thử trước đã được rollback hay chưa.

**Retry** quyết định có thử lại thao tác sau exception hay không. **Rollback** quyết định transaction hiện tại có bị hoàn tác hay không. Hai chính sách này liên quan chặt chẽ nhưng không phải một. Một thao tác có thể được đánh dấu retryable nhưng transaction vẫn cần rollback trước khi lần thử tiếp theo bắt đầu. Ngược lại, một exception có thể không làm rollback nhưng vẫn không được retry.

Bài học này trình bày vòng đời transaction của chunk, cách retry phối hợp với rollback, sự khác nhau giữa retry trong một transaction và retry sau rollback, cấu hình rollback rules, cách writer và processor được gọi lại, cùng những yêu cầu về idempotency, backoff, restart và kiểm thử.

## 1. Retry và rollback giải quyết hai vấn đề khác nhau

Retry và rollback thường xuất hiện cùng nhau khi xử lý lỗi tạm thời, nhưng mỗi cơ chế có trách nhiệm riêng.

| Cơ chế | Câu hỏi mà nó trả lời | Ví dụ |
|---|---|---|
| Retry | Có nên thử lại thao tác sau exception không? | Thử lại khi database báo deadlock |
| Rollback | Có cần hoàn tác transaction hiện tại không? | Hoàn tác các insert của chunk khi writer thất bại |
| Skip | Có được bỏ item lỗi và tiếp tục không? | Bỏ dòng CSV sai định dạng |
| Commit | Có xác nhận các thay đổi của transaction thành công không? | Lưu kết quả chunk vào database |
| Restart | Có thể tiếp tục Job sau một JobExecution thất bại hoặc dừng không? | Chạy lại Step từ checkpoint |

Ví dụ, writer ghi 100 đơn hàng và database phát sinh deadlock:

1. Writer ném exception.
2. Transaction hiện tại có thể cần rollback để giải phóng lock và loại bỏ các thay đổi dở dang.
3. Retry policy quyết định exception này có thể được thử lại.
4. Nếu còn lượt, Spring Batch thực hiện lần thử tiếp theo theo cơ chế của Step.
5. Nếu ghi thành công, transaction mới được commit.
6. Nếu hết retry, Step tiếp tục theo skip policy hoặc thất bại.

Retry không tự rollback transaction. Rollback cũng không tự quyết định có thử lại hay không. Cần cấu hình và kiểm thử cả hai hành vi.

## 2. Transaction boundary của chunk-oriented Step

Một chunk-oriented Step gom item theo commit interval. Framework đọc dữ liệu, gọi processor nếu có, rồi gọi writer cho các item đầu ra. Transaction manager điều khiển transaction của chunk.

Ví dụ:

~~~java
@Bean
Step importOrdersStep(
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

Với commit interval 100, một chunk có tối đa 100 item đầu vào. Transaction của chunk bao quanh công việc cần hoàn tất trước khi chunk được commit.

~~~mermaid
flowchart TD
    A["Bắt đầu chunk transaction"] --> B["Đọc item"]
    B --> C["Process item"]
    C --> D["Writer ghi output"]
    D --> E{"Chunk thành công?"}
    E -- "Có" --> F["Commit transaction"]
    E -- "Không" --> G["Rollback theo policy"]
    G --> H["Retry / skip / fail"]
    F --> I["Chunk tiếp theo"]
~~~

Khi transaction commit, các thay đổi tham gia transaction trở nên bền vững. Khi rollback, các thay đổi đó bị hoàn tác. Các chunk trước đã commit vẫn tồn tại nếu chunk hiện tại thất bại.

### Một Job có nhiều transaction

Nếu Job xử lý 10.000 item với commit interval 100, nó có thể có nhiều chunk và nhiều transaction độc lập. Một lỗi ở chunk thứ 50 không tự rollback 49 chunk trước đã commit.

Đây là đặc điểm quan trọng khi điều tra lỗi: rollback thường giới hạn ở transaction hiện tại, không phải toàn bộ Job.

## 3. Điều gì xảy ra khi lỗi xuất hiện trong chunk?

Giả sử chunk có các item A, B, C, D. Writer thực hiện các câu lệnh ghi và lỗi xuất hiện ở C.

~~~text
Chunk hiện tại:
  A -> ghi thành công trong transaction
  B -> ghi thành công trong transaction
  C -> lỗi constraint hoặc deadlock
  D -> chưa hoàn tất

Kết quả nếu transaction rollback:
  A -> hoàn tác
  B -> hoàn tác
  C -> không được ghi
  D -> chưa được ghi
~~~

Nếu A và B được ghi qua cùng transaction manager và resource được quản lý, rollback sẽ hoàn tác cả hai thay đổi dù các câu lệnh trước đó đã chạy thành công.

Sau đó, retry policy có thể cho phép thực hiện lại thao tác. Lần thử tiếp theo cần bắt đầu từ trạng thái transaction hợp lệ. Với lỗi database như deadlock, việc rollback thường cần thiết để database giải phóng lock và kết thúc transaction bị ảnh hưởng.

Không được coi việc một câu SQL đã trả về update count thành công là bằng chứng dữ liệu đã commit. Trước commit, thay đổi vẫn có thể bị rollback.

## 4. Cấu hình retry trong Spring Batch

Một chunk Step có thể bật fault tolerance và khai báo exception retryable:

~~~java
@Bean
Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

Các phần chính:

- `faultTolerant()` bật cấu hình retry/skip của chunk Step.
- `retry(...)` chỉ định loại exception có thể được thử lại.
- `retryLimit(...)` giới hạn số lần thử theo retry policy.
- Transaction manager vẫn quản lý transaction của chunk.

Không nên hiểu `faultTolerant()` là mọi lỗi đều được retry. Chỉ các exception được policy nhận diện mới có hành vi retry.

### Retry limit và số lần gọi

Ý nghĩa giới hạn có thể phụ thuộc API/policy và phiên bản thư viện tích hợp. Với policy kiểu SimpleRetryPolicy, maxAttempts thường tính cả lần gọi đầu tiên. Khi dùng builder của Spring Batch, hãy kiểm tra tài liệu phiên bản đang chạy và viết test xác nhận chính xác số lần gọi. Đừng suy luận số attempt chỉ từ tên tham số.

Ví dụ mục tiêu có tối đa ba lần gọi:

~~~text
Lần 1: lỗi tạm thời
Lần 2: lỗi tạm thời
Lần 3: thành công
Kết quả: thao tác thành công trong giới hạn
~~~

Nếu tất cả lần thử đều thất bại, exception cuối cùng được chuyển sang skip policy nếu được phép; nếu không, Step thất bại.

## 5. Vì sao retry database thường cần rollback?

Một số lỗi database cho thấy transaction hiện tại không còn thích hợp để tiếp tục:

- Deadlock: database chọn một transaction làm nạn nhân và hủy transaction đó.
- Lock timeout: transaction không lấy được lock trong thời gian quy định.
- Serialization failure: database từ chối transaction do xung đột đồng thời.
- Mất kết nối: trạng thái transaction có thể không còn xác định ở phía client.
- Lỗi ghi làm transaction bị đánh dấu rollback-only.

Với các lỗi này, tiếp tục chạy câu lệnh trong cùng transaction có thể không thành công hoặc transaction đã bị đánh dấu rollback-only. Cần rollback transaction bị lỗi và thực hiện lần thử trong một transaction hợp lệ theo cơ chế retry của Step.

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant TM as TransactionManager
    participant W as ItemWriter
    participant DB as Database

    S->>TM: Begin transaction
    S->>W: write(chunk)
    W->>DB: Execute statements
    DB-->>W: Deadlock
    W-->>S: Throw exception
    S->>TM: Rollback transaction
    Note over S,TM: Retry policy và backoff
    S->>TM: Begin transaction tiếp theo
    S->>W: Thử ghi lại
    W->>DB: Execute statements
    DB-->>W: Success
    S->>TM: Commit
~~~

Sơ đồ mô tả một tình huống điển hình. Vị trí chính xác của retry wrapper, việc chunk hoặc item được replay và thời điểm bắt đầu transaction mới phụ thuộc loại lỗi, giai đoạn xảy ra lỗi và cấu hình fault-tolerant của Step.

Điều quan trọng là lần thử lại phải tuân theo trạng thái transaction thực tế. Nếu transaction đã rollback-only, không thể coi việc gọi lại một phương thức trong cùng transaction đó là một lần thử sạch.

## 6. Retry có thể xảy ra ở những giai đoạn nào?

Trong chunk Step, lỗi có thể xuất hiện ở reader, processor hoặc writer. Mỗi giai đoạn có trạng thái và khả năng phát lại khác nhau.

| Giai đoạn | Ví dụ lỗi | Điều cần xem xét |
|---|---|---|
| Reader | Timeout khi truy vấn nguồn | Reader có thể khôi phục cursor, connection hoặc vị trí đọc không? |
| Processor | Dịch vụ enrichment tạm thời lỗi | Processor có side effect hoặc thay đổi input không? |
| Writer | Deadlock khi insert/update | Transaction có rollback toàn bộ thay đổi chunk không? |

### Retry ở processor

Processor thường biến đổi input thành output. Nếu processor gọi dịch vụ bên ngoài và dịch vụ tạm thời không sẵn sàng, nó có thể ném exception retryable.

~~~java
@Bean
ItemProcessor<OrderInput, EnrichedOrder> orderProcessor(
        CustomerProfileClient profileClient) {

    return input -> {
        CustomerProfile profile =
            profileClient.fetchProfile(input.customerId());

        return new EnrichedOrder(
            input.orderId(),
            profile,
            input.amount()
        );
    };
}
~~~

Nếu client ném exception retryable, framework có thể gọi lại processor theo retry policy. Processor nên tránh sửa input object hoặc tạo side effect không thể hoàn tác, vì cùng item có thể được xử lý lại.

### Retry ở writer

Writer có thể gặp deadlock hoặc lỗi tạm thời khi ghi. Khi lỗi làm rollback transaction, framework có thể phải thực hiện lại thao tác ghi hoặc xử lý chunk theo cơ chế fault-tolerant.

Writer cần chịu được việc nhận lại cùng item hoặc cùng nhóm item. Không giả định mỗi item chỉ được gửi đến writer đúng một lần.

### Retry ở reader

Reader có thể gặp lỗi kết nối khi đọc database hoặc nguồn từ xa. Tuy nhiên, reader có trạng thái như cursor, offset, file position hoặc message acknowledgment. Phải bảo đảm lần thử lại không làm mất item hoặc đọc sai vị trí.

Không bắt exception rồi trả `null` để báo EOF. `null` có nghĩa nguồn đã hết; lỗi tạm thời phải được biểu diễn bằng exception.

## 7. Retry và rollback classification

Retry policy và rollback policy là hai quyết định độc lập.

- Retry policy phân loại exception có được thử lại không.
- Rollback policy phân loại exception có làm transaction rollback không.
- Skip policy quyết định item có được bỏ qua không.

Một exception có thể được đánh dấu retryable nhưng không được rollback theo cấu hình. Ngược lại, exception có thể làm rollback nhưng không được retry.

Ví dụ bảng quyết định:

| Exception | Retry? | Rollback? | Lý do |
|---|---|---|---|
| Deadlock | Thường có | Thường có | Transaction bị database hủy hoặc không thể tiếp tục |
| Lock timeout | Có thể | Thường có | Cần giải phóng transaction trước lần thử mới |
| ValidationException | Không | Tùy giai đoạn và policy | Dữ liệu không đổi khi thử lại |
| File parse error | Thường không | Có thể không cần rollback chunk theo policy | Có thể skip riêng dòng lỗi |
| HTTP 503 từ API | Có thể | Database rollback nếu chunk phải thử lại và side effect cần nhất quán | Dịch vụ có thể phục hồi |
| Lỗi cấu hình SQL | Không | Thường có nếu transaction đã lỗi | Cần sửa cấu hình |

Bảng chỉ là hướng dẫn. Exception thực tế và transaction manager quyết định hành vi cuối cùng. Cần kiểm tra cause chain, rollback rules và tài nguyên tham gia transaction.

## 8. Rollback rules và checked exception

Spring transaction có quy tắc rollback theo loại exception. Theo mặc định phổ biến, unchecked exception và Error thường kích hoạt rollback; checked exception không nhất thiết tự động làm rollback trừ khi rollback rule được cấu hình.

Ví dụ:

~~~java
@Transactional(rollbackFor = IOException.class)
public void writeFileMetadata() throws IOException {
    // Thao tác cần rollback khi phát sinh IOException.
}
~~~

Với chunk Step, transaction attributes của Step và rollback classifier của Spring Batch cũng ảnh hưởng hành vi. Không nên giả định mọi exception đều có cùng kết quả.

Nếu một checked exception được đánh dấu retryable nhưng transaction không rollback, lần thử tiếp theo có thể tiếp tục trên transaction vẫn chứa thay đổi từ lần trước. Điều này chỉ an toàn nếu transaction và thao tác vẫn ở trạng thái hợp lệ. Với lỗi database làm transaction bị hỏng, cần rollback.

### Cấu hình transaction attributes cho Step

Có thể cấu hình propagation, isolation, timeout và rollback rules qua TransactionAttribute:

~~~java
@Bean
TransactionAttribute chunkTransactionAttribute() {
    RuleBasedTransactionAttribute attribute =
        new RuleBasedTransactionAttribute();

    attribute.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED
    );
    attribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
    );
    attribute.setTimeout(60);
    attribute.setRollbackRules(List.of(
        new RollbackRuleAttribute(Exception.class)
    ));

    return attribute;
}
~~~

Gắn vào Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .transactionAttribute(chunkTransactionAttribute)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .build();
~~~

Ví dụ trên minh họa cấu hình rollback cho mọi Exception. Trong ứng dụng thực tế, rollback rules cần được chọn cẩn thận. Không nên thêm quy tắc rộng nếu có checked exception được dự kiến là lỗi có thể skip và không làm transaction mất tính nhất quán.

## 9. noRollback không có nghĩa là retry an toàn

Fault-tolerant Step có thể khai báo exception không làm rollback bằng `noRollback(...)`:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TemporaryBusinessServiceException.class)
    .retryLimit(3)
    .noRollback(TemporaryBusinessServiceException.class)
    .build();
~~~

Cấu hình này chỉ phù hợp nếu exception không làm transaction bị hỏng và các thao tác đã thực hiện trước đó vẫn hợp lệ. Nó không phải cách chung để xử lý mọi lỗi retryable.

Với deadlock, serialization failure hoặc transaction đã bị đánh dấu rollback-only, việc giữ transaction không có ý nghĩa. Database có thể từ chối các câu lệnh tiếp theo hoặc commit ném UnexpectedRollbackException.

### Khi nào cân nhắc noRollback?

Có thể cân nhắc khi exception chỉ báo một điều kiện không làm hỏng transaction và ứng dụng muốn tiếp tục trong cùng ranh giới transaction. Nhưng cần xác nhận:

- Resource vẫn hoạt động.
- Transaction chưa bị đánh dấu rollback-only.
- Không có thay đổi dở dang cần hoàn tác.
- Item có thể bị bỏ qua hoặc xử lý tiếp theo cách nhất quán.
- Test chứng minh dữ liệu cuối đúng.

Không dùng noRollback để né deadlock hoặc giữ lại một phần ghi dở dang.

## 10. Writer phải tham gia transaction do Step quản lý

Writer ghi database nên dùng API tham gia transaction hiện tại như JdbcTemplate, NamedParameterJdbcTemplate, Spring Data repository hoặc JDBC connection được lấy qua cơ chế quản lý của Spring.

Ví dụ JdbcBatchItemWriter:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO processed_order(order_id, amount)
            VALUES (:orderId, :amount)
            """)
        .beanMapped()
        .build();
}
~~~

Khi writer dùng đúng DataSource và transaction manager của Step, các câu lệnh JDBC có thể tham gia transaction chunk.

Không nên tự mở connection rồi commit bên trong writer:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        // Thực hiện insert...

        connection.commit();
    }
}
~~~

Nếu writer commit riêng, transaction của Step không thể rollback thay đổi đó. Khi retry, dữ liệu đã commit có thể bị ghi trùng hoặc vi phạm constraint.

### Dùng cùng transaction manager

Cần xác nhận:

- Step nhận transaction manager nào.
- Transaction manager quản lý DataSource hoặc EntityManagerFactory nào.
- Writer dùng resource nào.
- Các DAO/service được gọi có tham gia transaction hiện tại không.
- Có connection độc lập hoặc propagation khác thường không.

Nếu writer dùng DataSource khác, rollback của Step không tự rollback dữ liệu ở datasource đó.

## 11. Retry và propagation của transaction

Propagation quyết định phương thức được gọi tham gia transaction hiện tại hay tạo transaction khác.

### PROPAGATION_REQUIRED

Đây là lựa chọn phổ biến cho service ghi nghiệp vụ:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void saveOrder(Order order) {
    orderRepository.save(order);
}
~~~

Nếu có transaction chunk hiện tại, phương thức tham gia transaction đó. Khi chunk rollback, thay đổi của service cũng rollback.

### PROPAGATION_REQUIRES_NEW

REQUIRES_NEW tạo transaction độc lập:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(Order order) {
    attemptRepository.save(toAttempt(order));
}
~~~

Transaction audit này có thể commit ngay cả khi chunk bên ngoài rollback. Điều đó có thể hữu ích để ghi nhận lần thử, nhưng cần tránh dùng cho dữ liệu nghiệp vụ chính vốn phải rollback cùng chunk.

Khi retry, một audit event có thể được ghi nhiều lần cho cùng item. Dùng attempt ID hoặc khóa deduplication để phân biệt lần thử.

### Transaction bị rollback-only

Một service tham gia transaction có thể đánh dấu transaction rollback-only sau exception. Ngay cả khi lớp ngoài bắt exception, transaction vẫn có thể không commit được. Khi hoàn tất transaction, ứng dụng có thể nhận UnexpectedRollbackException.

Đừng bắt exception rồi giả định transaction đã trở lại trạng thái bình thường. Nếu transaction đã rollback-only, lần thử tiếp theo cần diễn ra theo một ranh giới transaction hợp lệ.

## 12. Retry writer có thể làm thao tác ghi được gọi lại

Khi writer ném exception, framework có thể retry theo policy. Với write skip hoặc fault-tolerant processing, framework cũng có thể cô lập item lỗi bằng cách gọi lại writer với các nhóm item nhỏ hơn.

Ví dụ khái niệm:

~~~text
Lần gọi đầu:
  write([A, B, C, D]) -> lỗi tại C

Rollback:
  transaction chunk được hoàn tác

Quá trình xác định lỗi:
  write([A]) -> thành công
  write([B]) -> thành công
  write([C]) -> lỗi
  write([D]) -> thành công

Sau khi skip C:
  ghi các item hợp lệ theo transaction phù hợp
~~~

Đây là minh họa cho quá trình cô lập lỗi, không phải cam kết rằng mọi retry đều gọi writer theo đúng chuỗi trên. Framework có thể sử dụng chiến lược khác tùy cấu hình và loại exception.

### Vì sao phải thiết kế writer idempotent?

Nếu writer ghi ra một hệ thống không rollback được, lần gọi lại có thể tạo side effect trùng. Ngay cả khi database rollback, API bên ngoài có thể đã xử lý request.

Một số cách bảo vệ:

- Khóa duy nhất theo business key.
- Upsert nếu đúng với nghiệp vụ.
- Idempotency key ổn định cho API.
- Outbox cho việc phát message.
- Ghi file tạm riêng theo batch và publish sau commit.
- Lưu trạng thái xử lý để đối soát khi response không rõ ràng.

Idempotency cần được thiết kế ở phía hệ thống đích nếu client không thể biết chắc request trước đã được xử lý hay chưa.

## 13. Retry và side effect bên ngoài transaction

Database rollback không thể tự hoàn tác email, HTTP request, message đã gửi hoặc file đã được hệ thống khác đọc.

Ví dụ:

1. Writer insert order vào database.
2. Writer gọi API gửi thông báo.
3. API đã xử lý nhưng client nhận timeout.
4. Transaction database rollback.
5. Retry gọi lại writer.
6. API nhận request lần nữa.

Nếu API không hỗ trợ idempotency, người nhận có thể nhận hai thông báo hoặc hệ thống tạo hai giao dịch.

### Outbox pattern

Một cách phối hợp database và message broker là ghi event vào bảng outbox cùng transaction với dữ liệu nghiệp vụ:

~~~mermaid
flowchart TD
    A["Chunk writer"] --> B["Database transaction"]
    B --> C["Ghi order"]
    B --> D["Ghi outbox event"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Message broker"]
~~~

Khi chunk commit, cả order và outbox event cùng tồn tại. Publisher riêng gửi event và có thể retry. Consumer vẫn cần deduplication vì publisher có thể gửi lặp nếu không nhận được xác nhận.

### Không phát thông báo thành công trước commit

Processor hoặc ItemProcessListener chỉ biết processor đã trả kết quả. Điều đó không chứng minh writer đã commit. Hãy publish thông báo sau commit hoặc dùng outbox.

## 14. Backoff giữa các lần retry

Nếu retry ngay lập tức, nhiều worker có thể tạo tải dồn dập lên database hoặc dịch vụ đang lỗi. Backoff cho phép hệ thống đích có thời gian phục hồi.

Ví dụ exponential backoff:

~~~java
@Bean
BackOffPolicy retryBackOffPolicy() {
    ExponentialBackOffPolicy policy =
        new ExponentialBackOffPolicy();

    policy.setInitialInterval(500L);
    policy.setMultiplier(2.0);
    policy.setMaxInterval(5000L);

    return policy;
}
~~~

Gắn vào Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .backOffPolicy(retryBackOffPolicy)
    .build();
~~~

Khoảng chờ tăng dần và không vượt quá giá trị tối đa được cấu hình. API cụ thể của backoff policy cần khớp phiên bản Spring Retry đang dùng.

### Jitter khi có nhiều worker

Nếu nhiều partition cùng retry sau một khoảng thời gian cố định, chúng có thể gọi lại đồng thời. Randomized hoặc exponential random backoff giúp phân tán thời điểm thử lại.

Khi dùng API bên ngoài, nên tôn trọng Retry-After nếu dịch vụ cung cấp. Không retry dồn dập khi hệ thống đang yêu cầu giảm tốc độ.

### Tính tổng thời gian retry

Tổng thời gian xử lý một item có thể bao gồm:

- Timeout của mỗi request.
- Thời gian chờ backoff.
- Thời gian rollback transaction.
- Thời gian lấy connection mới.
- Thời gian thực hiện lần thử tiếp theo.

Đặt timeout và retry limit sao cho phù hợp với deadline của Job. Retry quá dài có thể làm worker giữ tài nguyên trong khi dịch vụ không thể phục hồi.

## 15. Kết hợp retry, skip và rollback

Ba chính sách có thể phối hợp:

- Retry lỗi tạm thời trong giới hạn.
- Nếu hết retry, skip nếu item được phép bỏ.
- Nếu không retry được hoặc không được skip, Step thất bại.
- Rollback theo rollback policy để bảo vệ transaction.

Ví dụ:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(20)
    .build();
~~~

Trong cấu hình này, lỗi truy cập dữ liệu tạm thời được retry. Lỗi InvalidOrderException được skip nếu nghiệp vụ cho phép. Lỗi khác không thuộc retry hoặc skip policy có thể làm Step thất bại.

Nếu cùng một exception vừa retryable vừa skippable, cần kiểm thử hành vi sau khi hết retry. Không giả định mọi policy đều có cùng thứ tự hoặc số lần thử qua các phiên bản.

### Retry exhausted không đồng nghĩa tự động skip

Khi retry hết lượt, framework vẫn cần áp dụng skip policy. Nếu exception không được phép skip hoặc skip limit đã vượt, Step thất bại.

Retry limit và skip limit là hai giới hạn khác nhau:

| Giới hạn | Đếm gì? |
|---|---|
| Retry limit | Số lần thử thao tác theo retry policy |
| Skip limit | Tổng số item được phép bỏ trong Step |

## 16. Retry trong reader và buffering

Khi chunk rollback, framework có thể cần phát lại các item đã đọc. Với reader thông thường, Spring Batch có cơ chế buffer item trong chunk để không phải đọc lại nguồn ngay lập tức.

Điều này quan trọng với file reader hoặc cursor reader, vì vị trí nguồn có thể đã tiến lên.

Với transactional queue, message có thể được trả lại queue khi transaction rollback. Trong trường hợp đó, Step có thể cần cấu hình:

~~~java
return new StepBuilder("queueStep", jobRepository)
    .<Message, ProcessedMessage>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(messageProcessor)
    .writer(messageWriter)
    .readerIsTransactionalQueue()
    .faultTolerant()
    .retry(TransientMessageException.class)
    .retryLimit(3)
    .build();
~~~

Cấu hình này báo cho Spring Batch biết reader lấy item từ transactional queue để framework xử lý buffering theo cơ chế phù hợp.

Cần phối hợp acknowledgment với transaction. Nếu reader acknowledge message trước khi chunk commit, database có thể rollback nhưng message đã biến mất khỏi queue. Retry không thể phục hồi item mà nguồn đã loại bỏ vĩnh viễn.

## 17. Stateful và stateless retry

Retry có thể duy trì trạng thái số lần thử theo cách khác nhau.

**Stateless retry** thường giữ retry context trong phạm vi lời gọi hiện tại. Nếu thao tác được gọi lại trong một execution khác, trạng thái có thể được khởi tạo lại tùy policy.

**Stateful retry** dùng một khóa để nhận diện cùng một lần xử lý logic qua các lần rollback và gọi lại. Cơ chế này hữu ích khi exception làm transaction rollback và framework phải đưa item trở lại luồng xử lý trong transaction mới.

Trong batch, Spring Retry và Spring Batch phối hợp retry context với item/chunk và rollback. Chi tiết implementation phụ thuộc phiên bản, retry policy và cấu hình. Không nên tự giả định retry counter luôn sống qua mọi transaction hoặc mọi JobExecution.

### Chọn stateful hay stateless theo đặc tính thao tác

Cần xem xét:

- Item có được nhận diện bằng khóa ổn định không?
- Transaction có rollback giữa các lần thử không?
- Item có được reader phát lại không?
- Retry context cần tồn tại qua lần gọi lại nào?
- Có thể có hai item giống nhau về equals/hashCode nhưng là hai bản ghi nghiệp vụ khác nhau không?

Nếu cần retry stateful cho item, khóa nhận diện phải phân biệt đúng item logic. Không dùng object mutable làm khóa nếu các field ảnh hưởng hashCode thay đổi trong quá trình xử lý.

## 18. Retry và restart là hai phạm vi khác nhau

Retry diễn ra trong lúc Step đang chạy. Restart diễn ra sau khi một JobExecution đã kết thúc thất bại hoặc dừng và cần một JobExecution mới cho cùng JobInstance.

| Cơ chế | Phạm vi | Khi nào dùng |
|---|---|---|
| Retry | Một thao tác hoặc item trong Step đang chạy | Lỗi tạm thời có thể phục hồi nhanh |
| Rollback | Transaction hiện tại | Loại bỏ thay đổi dở dang trước khi thử lại |
| Skip | Item lỗi trong Step đang chạy | Item được phép bỏ |
| Restart | JobExecution mới | Job thất bại hoặc dừng sau khi retry không đủ |
| JobInstance mới | Một lần xử lý logic mới | Batch ID hoặc identifying parameters khác |

Ví dụ:

~~~text
Chunk 1: commit thành công
Chunk 2: writer deadlock -> rollback -> retry thành công
Chunk 3: commit thành công
Job: COMPLETED
~~~

Không cần restart vì retry đã phục hồi trong cùng JobExecution.

Nếu chunk 2 hết retry và Step thất bại:

~~~text
Chunk 1: commit thành công
Chunk 2: rollback -> retry exhausted -> Step FAILED
Restart cùng JobInstance sau khi sửa sự cố
Chunk 2 được xử lý lại theo checkpoint
~~~

Restart cần reader có khả năng khôi phục và writer an toàn khi thao tác được phát lại.

## 19. Theo dõi retry và rollback

StepExecution cung cấp các bộ đếm như:

| Thuộc tính | Ý nghĩa |
|---|---|
| readCount | Số item reader trả về |
| writeCount | Số item writer ghi |
| filterCount | Số item processor lọc |
| readSkipCount | Số lỗi đọc được skip |
| processSkipCount | Số lỗi xử lý được skip |
| writeSkipCount | Số lỗi ghi được skip |
| commitCount | Số lần commit |
| rollbackCount | Số lần rollback |

Không có một bộ đếm StepExecution duy nhất đại diện cho mọi retry attempt. Nếu cần số lần retry, hãy instrument retry listener hoặc metrics ở lớp retry/client phù hợp.

Nên theo dõi:

- Số retry attempt theo loại exception.
- Số lần retry thành công.
- Số item hết retry.
- Số rollback theo Step và partition.
- Thời gian backoff.
- Thời gian xử lý một item sau các lần thử.
- Số item cuối cùng bị skip.
- Tỷ lệ lỗi theo database hoặc dịch vụ đích.

### Retry thành công vẫn có thể là tín hiệu cảnh báo

Một Job có thể COMPLETED dù hàng nghìn thao tác phải retry. Điều này có thể chỉ ra database quá tải, lock contention hoặc dịch vụ ngoài không ổn định.

Đặt ngưỡng cảnh báo cho retry rate và rollback count. Đừng chỉ nhìn trạng thái Job cuối cùng.

## 20. Kiểm thử retry cùng rollback

Kiểm thử phải chứng minh cả số lần thử lẫn trạng thái dữ liệu sau transaction.

### Test writer deadlock giả lập rồi thành công

Tạo writer test hoặc repository giả lập để lần đầu ném exception retryable, lần tiếp theo thành công.

Kỳ vọng:

1. Lần ghi đầu thất bại.
2. Transaction rollback theo policy.
3. Retry policy cho phép thử lại.
4. Lần thử sau ghi thành công.
5. Chunk được commit.
6. Không có dữ liệu trùng hoặc thay đổi dở dang.

Ví dụ logic giả lập:

~~~java
AtomicInteger attempts = new AtomicInteger();

ItemWriter<Order> writer = chunk -> {
    if (attempts.incrementAndGet() == 1) {
        throw new DeadlockLoserDataAccessException(
            "Deadlock giả lập"
        );
    }

    orderRepository.saveAll(chunk.getItems());
};
~~~

Ví dụ minh họa lần ghi đầu thất bại và lần sau thành công. Test tích hợp cần dùng transaction manager và database test thực để xác nhận rollback thật.

### Test retry exhausted

Cho writer luôn ném exception retryable. Xác nhận:

- Số lần gọi đúng giới hạn policy.
- Transaction thất bại được rollback.
- Step FAILED nếu exception không được skip.
- Chunk trước đã commit vẫn còn.
- Không có dữ liệu một phần từ chunk lỗi.

### Test noRollback

Cấu hình một exception noRollback trong tình huống có thể tiếp tục an toàn. Xác nhận transaction vẫn hợp lệ và dữ liệu cuối đúng. Không dùng test chỉ mock transaction manager để kết luận database không rollback.

### Test transaction bị rollback-only

Tạo service tham gia transaction và đánh dấu rollback-only. Bắt exception ở lớp gọi ngoài rồi thử commit. Xác nhận ứng dụng nhận biết UnexpectedRollbackException và không coi lần gọi tiếp theo trong cùng transaction là một retry sạch.

### Test side effect ngoài transaction

Giả lập API đã nhận request nhưng client nhận timeout. Khi retry, xác nhận cùng idempotency key được dùng và hệ thống đích chỉ tạo một thao tác logic.

### Test restart sau retry exhausted

Cho Step thất bại sau khi hết retry, sau đó restart cùng JobInstance. Xác nhận reader khôi phục checkpoint, chunk đã commit không bị ghi lại và writer có thể xử lý an toàn phần chưa commit.

## 21. Những lỗi thiết kế thường gặp

### Retry trong transaction đã rollback-only

Transaction đã bị đánh dấu rollback-only không thể trở thành transaction sạch chỉ bằng cách gọi lại phương thức. Cần để framework rollback và thực hiện lần thử theo ranh giới transaction phù hợp.

### Retry nhưng không rollback lỗi database

Deadlock hoặc serialization failure thường yêu cầu transaction hiện tại kết thúc. Không giữ transaction lỗi rồi tiếp tục ghi.

### Rollback nhưng writer tự commit connection riêng

Connection được commit độc lập không nằm trong transaction chunk. Rollback của Step không thể hoàn tác thay đổi đó.

### Retry mọi Exception

Lỗi dữ liệu, lỗi SQL cố định và lỗi quyền truy cập không tự hết khi thử lại. Chỉ retry exception có khả năng phục hồi.

### Dùng noRollback cho lỗi transaction nghiêm trọng

noRollback không sửa transaction bị hỏng hoặc rollback-only. Cấu hình sai có thể giữ thay đổi dở dang.

### Side effect bị lặp khi retry

Email, message hoặc request API có thể đã thành công dù client nhận timeout. Dùng idempotency key, outbox hoặc cơ chế deduplication.

### Bắt exception rồi trả kết quả giả

Nếu writer hoặc processor nuốt exception, retry policy không biết thao tác đã thất bại. Hãy truyền exception có ngữ nghĩa rõ ràng.

### Không kiểm thử rollback thật

Mock writer không chứng minh database đã hoàn tác thay đổi. Dùng integration test với transaction manager và database phù hợp.

### Tăng retry limit để che giấu lỗi hạ tầng

Retry nhiều lần có thể kéo dài Job và tăng tải. Nếu dịch vụ không phục hồi, fail Step và điều tra nguyên nhân.

### Nhầm retry với restart

Retry là lần thử trong execution hiện tại; restart là JobExecution mới. Theo dõi và thiết kế hai cơ chế riêng.

## 22. Quy trình thiết kế retry cùng transaction rollback

Khi thêm retry cho một Step, có thể thực hiện theo trình tự:

1. **Xác định điểm lỗi:** reader, processor, writer hoặc service bên ngoài.
2. **Phân loại exception:** xác định lỗi tạm thời, lỗi dữ liệu hay lỗi cấu hình.
3. **Chọn retry policy:** chỉ cho phép retry các exception có khả năng phục hồi.
4. **Xác định rollback rule:** quyết định transaction nào phải rollback khi exception xuất hiện.
5. **Kiểm tra transaction manager:** bảo đảm writer và DAO dùng đúng resource được quản lý.
6. **Chọn retry limit:** tính cả request timeout và tổng thời gian Job.
7. **Cấu hình backoff:** dùng fixed, exponential hoặc jitter theo tải hệ thống.
8. **Kiểm tra replay:** xác định item/chunk nào có thể được gọi lại và reader khôi phục ra sao.
9. **Thiết kế idempotency:** bảo vệ writer và side effect ngoài transaction.
10. **Kết hợp skip/fail:** quyết định kết quả khi retry hết lượt.
11. **Theo dõi:** đo retry attempt, rollback count, retry exhausted và thời gian xử lý.
12. **Kiểm thử:** xác nhận rollback thật, retry thành công, retry exhausted, skip và restart.

Một ma trận quyết định giúp nhóm thống nhất chính sách:

| Loại lỗi | Retry | Rollback | Kết quả khi hết retry |
|---|---|---|---|
| Database deadlock | Có, giới hạn | Có | Fail hoặc restart |
| Lock timeout | Có, giới hạn | Thường có | Fail hoặc skip nếu là lỗi item được phép |
| HTTP 503 | Có, backoff | Theo transaction của chunk và side effect | Fail hoặc đưa vào luồng phục hồi |
| Validation error | Không | Theo giai đoạn và rollback rules | Skip hoặc fail |
| SQL sai cấu hình | Không | Thường có nếu transaction đã lỗi | Fail |
| API request không hợp lệ | Không | Không thể rollback tác động ngoài nếu đã xảy ra | Reject hoặc fail |

## 23. Những điểm cần nhớ

- Retry quyết định có thử lại thao tác; rollback quyết định có hoàn tác transaction hiện tại.
- Hai chính sách độc lập và cần được thiết kế cùng nhau.
- Chunk transaction bao quanh công việc của một nhóm item; chunk đã commit trước đó không bị rollback khi chunk sau thất bại.
- Lỗi database như deadlock thường cần rollback transaction trước khi thử lại.
- Retry policy chỉ nên nhận các exception có khả năng phục hồi.
- Rollback rules và retry policy không phải cùng một cấu hình.
- noRollback không làm transaction rollback-only trở lại trạng thái bình thường và không tự bật retry.
- Writer cần dùng resource tham gia transaction manager của Step, không tự commit connection riêng.
- Processor và writer có thể được gọi lại; side effect phải idempotent hoặc được tách khỏi luồng chính.
- Backoff và jitter giúp giảm tải khi nhiều worker cùng retry.
- Skip chỉ được áp dụng nếu nghiệp vụ cho phép bỏ item sau khi retry hết lượt.
- Retry không phải restart; restart dùng JobExecution mới và phụ thuộc checkpoint.
- Theo dõi retry attempt riêng với rollbackCount và skip counts.
- Kiểm thử với transaction thật để xác nhận rollback, replay, retry thành công và retry exhausted.

Khi retry được phối hợp với rollback đúng cách, Spring Batch có thể phục hồi trước lỗi tạm thời mà vẫn giữ tính nhất quán của dữ liệu. Điều kiện quan trọng là transaction phải ở trạng thái hợp lệ trước lần thử mới, writer phải tham gia đúng transaction manager và mọi side effect có thể được gọi lại phải có cơ chế chống trùng.

