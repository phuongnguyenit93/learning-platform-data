# Transaction timeout

Trong Spring Batch, transaction timeout giới hạn khoảng thời gian một transaction của Step được phép thực hiện theo cấu hình transaction manager và resource bên dưới. Timeout giúp tránh transaction giữ connection, lock hoặc tài nguyên quá lâu khi truy vấn chậm, database bị nghẽn hoặc xử lý một chunk không kết thúc như dự kiến.

Chunk-oriented Step thường mở transaction cho từng chunk. TaskletStep mở transaction cho từng lượt gọi Tasklet. Vì vậy, transaction timeout thường áp dụng cho một chunk hoặc một lượt Tasklet, không phải toàn bộ thời gian chạy của Job.

Khi transaction vượt giới hạn, thao tác truy cập resource có thể thất bại và transaction bị rollback theo chính sách của transaction manager. Tuy nhiên, transaction timeout không phải một bộ hẹn giờ có thể bảo đảm dừng tức thì mọi đoạn Java code, HTTP request hoặc thread đang chạy. Cần phân biệt timeout của transaction với query timeout, lock timeout và network/socket timeout.

## 1. Transaction timeout là gì?

Transaction timeout là thời hạn được khai báo cho một transaction mới. Trong Spring, timeout thường được biểu diễn bằng giây thông qua TransactionDefinition hoặc TransactionAttribute. Transaction manager dùng giá trị này để áp dụng giới hạn cho transaction và các resource được quản lý.

Ví dụ, nếu một chunk được cấu hình timeout 60 giây, ứng dụng đang yêu cầu transaction của chunk đó hoàn thành trong giới hạn đã đặt. Nếu công việc vượt quá giới hạn, các thao tác database tiếp theo có thể phát sinh lỗi timeout; transaction hiện tại không thể được xem là hoàn tất thành công.

Một số mục đích của transaction timeout:

- Ngăn transaction giữ connection và lock quá lâu.
- Giới hạn thời gian chờ khi database hoặc resource phản hồi chậm.
- Giúp Step thất bại rõ ràng thay vì giữ transaction mở không xác định.
- Tạo cơ sở để phân loại lỗi tạm thời và áp dụng retry có kiểm soát.
- Bảo vệ các transaction khác đang cần dùng cùng tài nguyên database.

Transaction timeout không tự tối ưu một truy vấn chậm. Nếu một truy vấn luôn mất 90 giây và timeout đặt 60 giây, tăng timeout có thể giúp truy vấn hoàn tất nhưng không giải quyết nguyên nhân hiệu năng. Cần xem execution plan, index, lock, lượng dữ liệu và tải hệ thống.

## 2. Timeout áp dụng ở ranh giới nào trong Spring Batch?

### Chunk-oriented Step

Với chunk-oriented Step, Spring Batch đọc, xử lý và ghi một nhóm item trong transaction của chunk. Sau khi writer hoàn tất và các cập nhật liên quan thành công, transaction được commit.

~~~text
Chunk 1
  |
  +-- mở transaction
  |
  +-- đọc item
  +-- process item
  +-- ghi chunk
  +-- cập nhật metadata/checkpoint
  |
  +-- commit

Chunk 2
  |
  +-- mở transaction mới
  |
  +-- đọc / process / write
  |
  +-- commit
~~~

Transaction timeout được tính cho transaction của từng chunk. Nếu Step xử lý 1.000 chunk, timeout 60 giây không có nghĩa toàn Step chỉ được chạy tối đa 60 giây. Mỗi chunk có transaction riêng theo vòng đời xử lý của Step.

Tuy nhiên, nếu một chunk chứa nhiều item hoặc mỗi item có xử lý chậm, thời gian transaction có thể tăng. Chunk size lớn, processor gọi dịch vụ từ xa hoặc writer thực hiện nhiều truy vấn có thể khiến transaction vượt timeout.

### TaskletStep

TaskletStep gọi Tasklet trong transaction. Nếu Tasklet trả về CONTINUABLE, Step tiếp tục gọi Tasklet ở lượt sau; mỗi lượt thực thi được quản lý bằng transaction của lượt đó.

~~~text
Lượt Tasklet 1: mở transaction -> xử lý -> commit
Lượt Tasklet 2: mở transaction -> xử lý -> commit
Lượt Tasklet 3: mở transaction -> xử lý -> commit
~~~

Nếu Tasklet thực hiện toàn bộ công việc dài trong một lần gọi execute, một transaction có thể phải bao trùm toàn bộ công việc đó. Nếu Tasklet chia công việc thành các phần nhỏ và trả CONTINUABLE sau mỗi phần, mỗi lượt có thể kết thúc transaction riêng. Cách chia này cần checkpoint hoặc trạng thái bền vững để restart biết phần nào đã hoàn tất.

### Timeout không phải giới hạn thời gian của toàn Job

Job thường gồm nhiều Step, còn chunk-oriented Step có nhiều transaction. Một Job có thể chạy hàng giờ dù mỗi transaction của chunk chỉ kéo dài vài giây. Transaction timeout giới hạn từng transaction theo cấu hình, không phải tổng thời gian chạy của Job.

Nếu hệ thống cần giới hạn tổng thời gian của Job hoặc thời gian chờ một quy trình bên ngoài, cần một cơ chế điều phối hoặc timeout riêng cho mục tiêu đó. Không nên dùng transaction timeout như một Job deadline.

## 3. Cấu hình timeout cho chunk-oriented Step

Trong Spring Batch 5 trở lên, có thể tạo TransactionAttribute và truyền vào StepBuilder thông qua transactionAttribute:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setTimeout(60);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .transactionAttribute(transactionAttribute)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong ví dụ:

- Chunk size là 100 item.
- Transaction manager quản lý transaction của chunk.
- Timeout được đặt là 60 giây.
- Mỗi chunk được xử lý trong transaction riêng theo cấu hình của Step.

TransactionAttribute cũng có thể điều khiển propagation, isolation level và rollback rules. Nếu chỉ cần điều chỉnh timeout, giữ các thuộc tính còn lại theo mặc định thường giúp tránh thay đổi hành vi không cần thiết.

Có thể đưa timeout ra cấu hình:

~~~properties
batch.orders.chunk-size=100
batch.orders.transaction-timeout-seconds=60
~~~

Sau đó inject các giá trị vào cấu hình Step. Nên kiểm tra giá trị đầu vào để tránh cấu hình timeout ngoài dự kiến:

~~~java
if (transactionTimeoutSeconds <= 0) {
    throw new IllegalArgumentException(
            "Transaction timeout must be positive");
}
~~~

Giá trị mặc định của transaction timeout có thể được biểu diễn bằng TransactionDefinition.TIMEOUT_DEFAULT, nghĩa là dùng timeout mặc định của transaction manager hoặc resource. Khi cần giới hạn cụ thể cho một Step, hãy đặt giá trị rõ ràng và kiểm tra transaction manager có hỗ trợ cách áp dụng đó.

## 4. Cấu hình timeout cho TaskletStep

TaskletStep cũng cho phép cấu hình TransactionAttribute. Ví dụ:

~~~java
@Bean
public Step reconcileBatchStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReconciliationService reconciliationService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        reconciliationService.reconcileCurrentBatch();
        return RepeatStatus.FINISHED;
    };

    DefaultTransactionAttribute transactionAttribute =
            new DefaultTransactionAttribute();
    transactionAttribute.setTimeout(120);

    return new StepBuilder("reconcileBatchStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .transactionAttribute(transactionAttribute)
            .build();
}
~~~

Ở đây transaction timeout là 120 giây cho transaction của lượt Tasklet. Nếu Tasklet trả CONTINUABLE, các lượt tiếp theo cũng được thực thi theo transaction attributes của Step.

Nếu Tasklet gọi một API bên ngoài mất 5 phút, transaction timeout 120 giây không bảo đảm HTTP request bị hủy sau đúng 120 giây. Cần cấu hình connect timeout, response/read timeout hoặc deadline ở HTTP client. Đồng thời, không nên giữ transaction database mở trong suốt thời gian chờ API nếu không cần thiết.

## 5. Phân biệt các loại timeout

Một hệ thống batch có thể có nhiều lớp timeout. Chúng bảo vệ các tài nguyên và hoạt động khác nhau:

| Loại timeout | Phạm vi | Ví dụ |
| --- | --- | --- |
| **Transaction timeout** | Thời gian transaction được phép tồn tại theo transaction manager | Một chunk cần hoàn tất trong 60 giây |
| **Query/statement timeout** | Thời gian một câu SQL được phép thực thi | SELECT hoặc UPDATE vượt 20 giây |
| **Lock timeout** | Thời gian chờ lấy lock trên database | UPDATE phải chờ transaction khác nhả lock |
| **Connection timeout** | Thời gian chờ lấy connection từ pool hoặc thiết lập kết nối | HikariCP không cấp connection trong thời hạn |
| **Network/socket timeout** | Thời gian chờ dữ liệu qua kết nối mạng | JDBC driver hoặc HTTP client chờ phản hồi |
| **Job/operation deadline** | Tổng thời gian một quy trình nghiệp vụ được phép chạy | Một đợt đối soát phải hoàn tất trước giờ chốt |

Các timeout có thể tương tác nhưng không thay thế nhau. Ví dụ transaction timeout 60 giây không nhất thiết giới hạn một câu SQL ở 60 giây nếu driver hoặc resource không áp dụng transaction timeout cho statement. Query timeout 20 giây có thể làm câu SQL dừng trước khi transaction timeout xảy ra.

### Transaction timeout và query timeout

Query timeout thường được cấu hình ở JDBC statement hoặc JdbcTemplate. Với JdbcTemplate, có thể đặt query timeout mặc định cho template:

~~~java
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
jdbcTemplate.setQueryTimeout(20);
~~~

Khi dùng JdbcTemplate, Spring áp dụng các cài đặt statement và transaction timeout phù hợp theo cơ chế của DataSourceUtils. Nếu dùng JDBC trực tiếp, ứng dụng cần bảo đảm statement được liên kết với transaction và áp dụng timeout đúng cách; không nên giả định mọi lệnh JDBC thô tự động nhận đầy đủ timeout của Spring.

Ví dụ dùng DataSourceUtils để áp dụng transaction timeout cho statement:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    PreparedStatement statement =
            connection.prepareStatement("SELECT * FROM orders WHERE id = ?");

    try {
        statement.setLong(1, orderId);
        DataSourceUtils.applyTransactionTimeout(statement, dataSource);

        try (ResultSet resultSet = statement.executeQuery()) {
            // Đọc kết quả.
        }
    } finally {
        statement.close();
    }
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Trong ứng dụng thông thường, JdbcTemplate hoặc repository abstraction thường an toàn và dễ quản lý hơn JDBC thủ công.

### Transaction timeout và lock timeout

Transaction có thể bị chậm vì phải chờ lock. Lock timeout do database quản lý và thường có cấu hình riêng theo hệ quản trị. Nếu lock timeout ngắn hơn transaction timeout, database có thể trả lỗi lock trước khi transaction đạt giới hạn tổng thể.

Khi thấy lock wait, cần tìm transaction giữ lock, thứ tự cập nhật bảng và mức độ tranh chấp. Tăng transaction timeout không giải quyết deadlock hoặc lock contention; đôi khi còn làm các transaction khác phải chờ lâu hơn.

### Transaction timeout và network timeout

Một câu SQL hoặc lời gọi HTTP có thể chờ mạng lâu. Network/socket timeout do driver hoặc client điều khiển. Transaction timeout không phải lúc nào cũng ngắt được kết nối mạng đang bị treo.

Hãy cấu hình timeout cho JDBC driver, HTTP client và message client theo đặc tính dịch vụ. Timeout phải có quan hệ hợp lý với transaction timeout và deadline của toàn operation.

## 6. Transaction timeout được áp dụng khi nào?

Trong Spring, timeout là thuộc tính của transaction mới. Nếu một phương thức tham gia transaction đã tồn tại với propagation REQUIRED, nó thường tham gia transaction hiện tại và không thể thay đổi timeout đã được áp dụng khi transaction đó bắt đầu.

Ví dụ:

~~~java
@Transactional(timeout = 30)
public void updateOrders() {
    // ...
}
~~~

Nếu updateOrders được gọi từ một Tasklet đang chạy trong transaction của Step, propagation mặc định REQUIRED có nghĩa phương thức tham gia transaction hiện tại. Annotation timeout trên phương thức không tự biến transaction đang chạy thành transaction 30 giây.

Nếu phương thức được gọi độc lập và tạo transaction mới qua Spring proxy, timeout 30 giây có thể được áp dụng cho transaction đó, tùy transaction manager.

Không nên thêm REQUIRES_NEW chỉ để ép timeout nếu chưa xem xét tác động. REQUIRES_NEW tạo transaction độc lập, có thể commit dữ liệu dù transaction bên ngoài rollback. Điều này làm thay đổi atomicity và có thể khiến metadata hoặc dữ liệu nghiệp vụ không còn đồng bộ như dự kiến.

### Lưu ý về self-invocation

Với proxy-based transaction management, gọi một phương thức @Transactional từ phương thức khác trong cùng object thường không đi qua proxy. Vì vậy, annotation và timeout có thể không được áp dụng như mong đợi. Nếu cần transaction riêng, hãy tổ chức bean và ranh giới gọi phù hợp thay vì dựa vào self-invocation.

## 7. Điều gì xảy ra khi transaction timeout?

Hành vi cụ thể phụ thuộc transaction manager, database và resource. Trong một cấu hình JDBC điển hình:

1. Step bắt đầu transaction cho chunk hoặc lượt Tasklet.
2. Reader, processor hoặc writer thực hiện công việc.
3. Transaction vượt timeout.
4. Một thao tác truy cập resource có thể nhận lỗi timeout hoặc transaction bị đánh dấu rollback-only.
5. Exception thoát khỏi Step nếu không được xử lý phù hợp.
6. Transaction manager rollback transaction hiện tại.
7. StepExecution được ghi nhận trạng thái thất bại nếu Step không có flow xử lý lỗi phù hợp.

Một số exception có thể xuất hiện tùy tầng:

- TransactionTimedOutException từ Spring.
- QueryTimeoutException từ Spring JDBC.
- SQLTimeoutException từ JDBC.
- Exception riêng của database hoặc driver.

Không nên chỉ bắt một class exception duy nhất nếu các driver và resource có thể bọc lỗi theo cách khác nhau. Hãy phân loại bằng exception hierarchy, root cause và mã lỗi database phù hợp.

### Timeout không nhất thiết dừng code Java ngay lập tức

Nếu processor đang thực hiện một phép tính CPU thuần túy trong 90 giây, transaction timeout 60 giây không nhất thiết ngắt thread tại giây thứ 60. Việc kiểm tra timeout có thể chỉ xảy ra khi ứng dụng truy cập resource hoặc transaction manager thực hiện thao tác commit.

Với công việc CPU-bound hoặc lời gọi bên ngoài, cần deadline, cancellation hoặc timeout riêng ở thành phần thực hiện. Không nên dựa vào transaction timeout để kiểm soát thời gian của mọi đoạn code.

## 8. Timeout, rollback và trạng thái Step

Nếu exception do timeout thoát khỏi một chunk transaction, transaction hiện tại thường rollback. Các chunk đã commit trước đó vẫn được giữ nguyên.

~~~text
Chunk 1: xử lý thành công -> COMMIT
Chunk 2: xử lý thành công -> COMMIT
Chunk 3: vượt transaction timeout -> ROLLBACK
Chunk 4: chưa được xử lý
~~~

Nếu Step thất bại, Job có thể kết thúc FAILED hoặc chuyển sang nhánh xử lý lỗi theo flow được cấu hình. Khi restart, Spring Batch tạo JobExecution mới cho cùng JobInstance nếu Job cho phép restart và identifying parameters được giữ nguyên.

Với Tasklet nhiều lượt, những lượt đã commit trước đó không bị rollback chỉ vì một lượt sau timeout. Nếu Tasklet không lưu checkpoint, lần restart có thể phải thực hiện lại phần việc đã hoàn thành. Cần thiết kế idempotency hoặc checkpoint để không tạo dữ liệu trùng.

### Không nuốt exception timeout

Không nên bắt timeout rồi trả FINISHED:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        service.process();
    } catch (QueryTimeoutException ex) {
        log.error("Query timed out", ex);
    }

    return RepeatStatus.FINISHED;
};
~~~

Cách viết này có thể làm Step được ghi nhận hoàn tất dù thao tác database thất bại hoặc transaction đã bị đánh dấu rollback-only. Nếu lỗi timeout có nghĩa công việc chưa hoàn thành, hãy ném exception ra để TaskletStep xử lý:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    service.process();
    return RepeatStatus.FINISHED;
};
~~~

Nếu cần log, hãy log rồi ném lại exception, giữ nguyên cause.

## 9. Chọn timeout phù hợp

Timeout quá ngắn có thể làm Step thất bại khi hệ thống chỉ đang chậm tạm thời. Timeout quá dài có thể khiến connection và lock bị giữ lâu, làm sự cố kéo dài và gây ảnh hưởng đến các transaction khác.

Khi chọn timeout, hãy xem xét:

- Thời gian xử lý bình thường của một chunk hoặc một lượt Tasklet.
- Phân vị cao của thời gian xử lý trong điều kiện tải thực tế, không chỉ giá trị trung bình.
- Số lượng item và kích thước dữ liệu trong chunk.
- Độ trễ truy vấn, ghi dữ liệu và commit.
- Thời gian chờ lock dự kiến và giới hạn của database.
- Thời gian gọi dịch vụ ngoài nếu có.
- Transaction timeout mặc định của transaction manager.
- Query timeout, connection timeout và network timeout.
- Yêu cầu deadline của quy trình nghiệp vụ.

Một cách tiếp cận là đo thời gian chunk trong điều kiện bình thường và tải cao, sau đó đặt timeout cao hơn mức vận hành bình thường nhưng vẫn đủ thấp để giải phóng tài nguyên khi có sự cố. Khoảng đệm cần dựa trên số liệu của hệ thống.

Ví dụ, nếu 99% chunk hoàn tất trong 8 giây, nhưng có một số chunk mất 25 giây khi tải cao, timeout 10 giây có thể gây thất bại thường xuyên. Timeout 60 giây có thể phù hợp hơn nếu database và yêu cầu nghiệp vụ cho phép. Đây chỉ là ví dụ minh họa; không có một giá trị chuẩn cho mọi ứng dụng.

### Cân nhắc chunk size

Chunk size ảnh hưởng đến thời gian transaction. Nếu một item trung bình mất 100 ms và chunk có 500 item, riêng phần xử lý tuần tự có thể mất khoảng 50 giây, chưa tính reader, writer, commit và overhead. Timeout 30 giây có thể không đủ.

Có thể:

- Giảm chunk size để transaction ngắn hơn.
- Tối ưu processor hoặc truy vấn đang chậm.
- Dùng batch write hiệu quả hơn.
- Chuyển thao tác bên ngoài transaction ra khỏi transaction nếu thiết kế nghiệp vụ cho phép.
- Tăng timeout sau khi đánh giá lock, connection và database capacity.

Không nên chỉ tăng timeout để che giấu một chunk có kích thước không phù hợp.

## 10. Timeout khi gọi dịch vụ bên ngoài

Tasklet hoặc ItemProcessor đôi khi gọi REST API, message broker hoặc dịch vụ khác. Những lời gọi này thường không nằm trong transaction JDBC của Step.

Ví dụ một Tasklet mở transaction database, gọi HTTP API mất 2 phút rồi mới cập nhật trạng thái. Nếu transaction timeout là 60 giây, transaction có thể đã quá hạn trước khi lời gọi HTTP trả về. Tuy nhiên, request có thể vẫn đã được server xử lý.

Thiết kế tốt hơn thường là:

1. Đọc hoặc ghi trạng thái chuẩn bị trong transaction ngắn.
2. Commit trạng thái cần thiết.
3. Thực hiện lời gọi từ xa với connect/read timeout và idempotency key.
4. Ghi nhận kết quả trong transaction mới.
5. Có thể retry hoặc đối soát nếu kết quả từ xa không xác định.

Không phải mọi nghiệp vụ đều có thể tách như vậy. Nếu cần tính nguyên tử xuyên database và hệ thống ngoài, cần kiến trúc phù hợp như outbox, saga hoặc giao thức transaction phân tán được các hệ thống hỗ trợ. Một transaction timeout đơn lẻ không cung cấp atomicity xuyên các dịch vụ.

## 11. Retry khi gặp timeout

Timeout có thể là lỗi tạm thời, nhưng không phải lúc nào cũng nên retry. Trước khi retry, cần xác định:

- Timeout xảy ra ở bước lấy connection, chạy query, chờ lock hay gọi dịch vụ ngoài?
- Thao tác đã được server thực hiện hay chưa?
- Transaction đã rollback chắc chắn chưa?
- Retry có thể tạo side effect trùng không?
- Có giới hạn số lần thử và backoff không?
- Có cần circuit breaker hoặc giới hạn concurrency không?

Với lỗi truy vấn tạm thời, retry có giới hạn có thể phù hợp. Với query luôn vượt timeout do thiếu index hoặc quét bảng lớn, retry chỉ làm database chịu thêm tải.

Với HTTP timeout, client có thể không biết server đã xử lý request hay chưa. Dùng idempotency key hoặc truy vấn trạng thái operation trước khi gửi lại.

Trong chunk-oriented Step, có thể cấu hình retry cho exception phù hợp:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Ví dụ này chỉ minh họa retry cho một nhóm lỗi truy cập dữ liệu tạm thời. Cần kiểm tra exception thực tế do driver phát ra và cách nó được Spring dịch. Không nên retry tất cả QueryTimeoutException nếu timeout là triệu chứng của truy vấn quá chậm hoặc lock contention kéo dài.

## 12. Giám sát transaction timeout

Để xác định timeout đến từ đâu, cần kết hợp metadata Spring Batch với số liệu của ứng dụng và database.

### Metadata Spring Batch

JobRepository lưu trạng thái JobExecution và StepExecution. Có thể dùng JobExplorer để xem:

- JobExecution và StepExecution nào FAILED.
- ExitStatus và failure exception.
- Read count, write count, skip count và commit count.
- Thời gian bắt đầu và kết thúc Step.

Metadata cho biết Step thất bại, nhưng có thể không đủ để xác định câu SQL hoặc resource cụ thể gây timeout.

### Log ứng dụng

Ghi nhận Job name, JobExecutionId, Step name, business key, chunk size và loại exception. Không log thông tin xác thực hoặc payload nhạy cảm.

### Database metrics

Theo dõi:

- Query duration và query timeout.
- Lock wait, deadlock và transaction đang mở lâu.
- Connection pool usage và connection acquisition time.
- CPU, I/O, buffer/cache và số lượng session.
- Câu SQL có thời gian chạy bất thường.

Nếu Step timeout nhưng database không có query chậm, nguyên nhân có thể nằm ở processor, gọi dịch vụ ngoài hoặc đoạn code CPU-bound. Instrument từng giai đoạn giúp xác định phần thời gian bị tiêu tốn.

## 13. Những lỗi thường gặp

### Nhầm transaction timeout với Job timeout

Transaction timeout giới hạn transaction của chunk hoặc lượt Tasklet. Nó không giới hạn tổng thời gian chạy của toàn Job.

### Chỉ đặt @Transactional timeout trên service được gọi bên trong Step

Nếu service tham gia transaction hiện tại với propagation REQUIRED, timeout của annotation không tự thay đổi timeout đã đặt khi transaction Step bắt đầu. Cấu hình timeout ở ranh giới transaction thực sự được tạo.

### Tăng timeout để xử lý query chậm

Tăng timeout có thể cho query thêm thời gian nhưng không sửa index thiếu, execution plan kém hoặc lock contention. Hãy điều tra query trước khi tăng giới hạn.

### Nghĩ transaction timeout hủy HTTP request

Transaction manager không tự điều khiển timeout của mọi HTTP client. Cấu hình connect/read timeout hoặc deadline ở client riêng.

### Dùng timeout dài cho transaction có nhiều side effect

Transaction dài giữ tài nguyên lâu và tăng khả năng side effect bên ngoài đã xảy ra trước khi rollback. Giữ transaction ngắn khi có thể và thiết kế idempotency.

### Retry timeout vô hạn

Retry không giới hạn có thể làm database hoặc dịch vụ đang quá tải càng quá tải hơn. Dùng retry limit, backoff và phân loại exception.

### Không kiểm tra transaction manager và driver

Timeout được áp dụng khác nhau tùy transaction manager, JDBC driver và database. Kiểm thử trong môi trường tương đương production để xác nhận hành vi thực tế.

### Giảm timeout mà không xem xét thời gian chunk

Một chunk quá lớn có thể vượt timeout ngay cả khi hệ thống hoạt động bình thường. Đánh giá chunk size, thời gian xử lý item và writer cùng timeout.

## 14. Quy trình cấu hình và xử lý timeout

Khi triển khai transaction timeout cho một Step, có thể đi theo trình tự:

1. Xác định ranh giới transaction: mỗi chunk hay mỗi lượt Tasklet.
2. Đo thời gian xử lý bình thường và tải cao của transaction.
3. Xác định phần thời gian dành cho reader, processor, writer, commit và chờ resource.
4. Chọn timeout có khoảng đệm phù hợp với yêu cầu nghiệp vụ.
5. Cấu hình TransactionAttribute tại Step hoặc transaction boundary thực sự tạo transaction.
6. Cấu hình query, lock, connection và network timeout riêng theo resource.
7. Kiểm tra transaction manager và driver có áp dụng timeout như mong đợi.
8. Thử tình huống query chậm, lock wait và dịch vụ ngoài bị treo.
9. Xác nhận rollback, BatchStatus, ExitStatus và khả năng restart.
10. Bổ sung retry có giới hạn chỉ cho lỗi thực sự có thể phục hồi.

Một cấu hình timeout chỉ được xem là phù hợp khi vừa bảo vệ tài nguyên, vừa không làm Step thất bại trong điều kiện tải hợp lệ. Cần tiếp tục theo dõi sau triển khai vì dữ liệu và tải có thể thay đổi theo thời gian.

## Kết luận

Transaction timeout giới hạn thời gian của transaction được quản lý bởi transaction manager. Trong Spring Batch, nó thường áp dụng cho từng chunk của chunk-oriented Step hoặc từng lượt gọi Tasklet, không phải toàn bộ Job. Có thể cấu hình bằng TransactionAttribute và setTimeout, nhưng cần phân biệt với query, lock, connection và network timeout. Khi timeout xảy ra, transaction hiện tại có thể rollback và Step thất bại; các chunk đã commit trước đó vẫn tồn tại. Hãy chọn timeout dựa trên số liệu thực tế, giữ transaction ngắn, phân loại retry và thiết kế checkpoint/idempotency để phục hồi an toàn.
