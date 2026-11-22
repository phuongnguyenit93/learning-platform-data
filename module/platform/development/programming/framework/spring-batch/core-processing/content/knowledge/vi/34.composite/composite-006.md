# Thứ tự writer và lỗi một writer

Trong Spring Batch, CompositeItemWriter cho phép một chunk được ghi tới nhiều đích bằng cách kết hợp nhiều ItemWriter delegate. Các delegate được gọi tuần tự theo thứ tự cấu hình. Nếu một delegate ném exception, composite dừng tại delegate đó, không gọi các delegate phía sau trong lần invocation hiện tại và truyền exception về Step.

Thứ tự gọi không tự tạo ra một transaction chung cho mọi hệ thống. Nếu các delegate cùng ghi vào một database và cùng tham gia transaction của chunk, lỗi có thể rollback các thay đổi database trước đó. Nếu một delegate đã gửi HTTP request, publish message hoặc ghi vào resource không transactional, side effect đó có thể vẫn tồn tại dù chunk rollback.

Khi thiết kế composite writer, cần xác định:

- Delegate nào chạy trước và vì sao.
- Mỗi delegate nhận toàn bộ chunk hay một tập item riêng.
- Lỗi ở delegate thứ mấy sẽ ngăn delegate sau chạy.
- Các delegate có tham gia cùng transaction không.
- Khi retry hoặc write skip, delegate nào sẽ được gọi lại.
- Side effect nào cần idempotency, outbox hoặc đối soát.

## 1. CompositeItemWriter là gì?

CompositeItemWriter là một ItemWriter điều phối nhiều ItemWriter khác. Khi Step gọi write(chunk), composite lần lượt gọi write(chunk) trên từng delegate theo thứ tự được cấu hình.

Ví dụ một Job cần ghi đơn hàng vào database, ghi audit và tạo file kết quả:

~~~text
Step
 |
 v
CompositeItemWriter
 |
 +--> DatabaseOrderWriter
 |
 +--> AuditOrderWriter
 |
 +--> OrderFileWriter
~~~

Mỗi delegate có một trách nhiệm ghi riêng. Composite gom chúng thành một writer duy nhất để đăng ký trong Step.

CompositeItemWriter không tự chia chunk thành các nhóm item khác nhau cho từng delegate. Mặc định, mỗi delegate nhận cùng chunk đầu vào. Nếu một đích cần dữ liệu khác kiểu hoặc chỉ nhận một tập item được lọc, hãy dùng adapter/decorator writer có chủ đích hoặc thiết kế pipeline riêng.

## 2. Thứ tự delegate được quyết định ở đâu?

Thứ tự là thứ tự các delegate được truyền vào CompositeItemWriterBuilder hoặc danh sách được cấu hình cho CompositeItemWriter.

~~~java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        ItemWriter<Order> databaseOrderWriter,
        ItemWriter<Order> auditOrderWriter,
        ItemWriter<Order> fileOrderWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(
                    databaseOrderWriter,
                    auditOrderWriter,
                    fileOrderWriter)
            .build();
}
~~~

Khi Step gọi writer, trình tự là:

1. databaseOrderWriter.write(chunk)
2. auditOrderWriter.write(chunk)
3. fileOrderWriter.write(chunk)

Composite gọi tuần tự, không chạy các delegate song song. Delegate thứ hai chỉ bắt đầu sau khi delegate thứ nhất trả về bình thường.

Thứ tự cấu hình là một phần của hành vi ứng dụng. Khi đổi vị trí delegate, có thể thay đổi side effect nào xảy ra trước khi lỗi được phát hiện. Vì vậy, thay đổi thứ tự writer cần được xem là thay đổi logic xử lý, có test cho các tình huống lỗi.

## 3. Mỗi delegate nhận cùng một chunk

Giả sử chunk có ba đơn hàng A, B và C:

~~~text
Chunk = [A, B, C]
          |
          v
DatabaseWriter.write([A, B, C])
          |
          v
AuditWriter.write([A, B, C])
          |
          v
FileWriter.write([A, B, C])
~~~

Mỗi delegate được gọi một lần cho chunk và nhận cùng danh sách item về mặt nội dung. Delegate có thể thực hiện batch insert, ghi file hoặc gửi dữ liệu tới hệ thống khác.

Composite không mặc định thực hiện việc gửi A qua tất cả delegate rồi mới tới B. Thay vào đó, nó gọi từng delegate với cả chunk. Điều này quan trọng khi phân tích lỗi một phần: database writer có thể đã xử lý cả A, B, C trước khi audit writer bắt đầu.

Không nên để một delegate thay đổi object trong chunk theo cách làm thay đổi dữ liệu mà delegate sau nhìn thấy. Hãy coi item được chuyển cho các writer là dữ liệu đã được chuẩn bị và ổn định. Nếu cần biến đổi, tạo object mới ở processor hoặc adapter riêng.

## 4. Điều gì xảy ra khi một writer ném exception?

Giả sử thứ tự là DatabaseWriter, AuditWriter và FileWriter. AuditWriter ném exception:

~~~text
Step gọi CompositeItemWriter
          |
          v
DatabaseWriter.write(chunk)
          |
          | trả về bình thường
          v
AuditWriter.write(chunk)
          |
          | ném exception
          v
Composite dừng
          |
          +--> FileWriter không được gọi
          |
          v
Exception truyền ra Step
          |
          v
Rollback / Retry / Skip / Fail
~~~

Composite không tự bắt lỗi rồi tiếp tục gọi các delegate còn lại. Khi một delegate ném exception, vòng lặp gọi delegate bị dừng và exception thoát ra khỏi write().

Do đó:

- Delegate trước lỗi đã được gọi.
- Delegate gây lỗi đã được gọi nhưng không hoàn thành bình thường.
- Delegate sau lỗi chưa được gọi trong lần composite invocation đó.
- Step nhận exception và xử lý theo cấu hình transaction/fault tolerance.

Đừng giả định một delegate ném lỗi thì composite sẽ tự rollback các delegate đã chạy. Rollback phụ thuộc resource và transaction mà các delegate sử dụng.

## 5. Bảng kết quả theo vị trí writer lỗi

Giả sử có ba delegate theo thứ tự A, B, C:

| Delegate lỗi | A | B | C |
|---|---|---|---|
| A ném lỗi | Có thể đã ghi một phần | Không gọi | Không gọi |
| B ném lỗi | Đã trả về bình thường | Có thể đã ghi một phần | Không gọi |
| C ném lỗi | Đã trả về bình thường | Đã trả về bình thường | Có thể đã ghi một phần |
| Không lỗi | Hoàn tất | Hoàn tất | Hoàn tất |

Bảng này chỉ mô tả việc gọi delegate. Nó chưa kết luận dữ liệu còn tồn tại sau khi transaction kết thúc.

Nếu A, B và C cùng tham gia một transaction database và transaction rollback, các thay đổi database trong transaction có thể được hoàn tác. Nếu A là HTTP API hoặc file writer không tham gia transaction, thay đổi của A có thể vẫn tồn tại.

## 6. Transaction của chunk bao quanh composite writer

Trong chunk-oriented Step, Spring Batch quản lý transaction cho chunk. Writer được gọi trong quá trình xử lý chunk trước khi transaction commit.

~~~text
Begin chunk transaction
       |
       v
Read / process items
       |
       v
CompositeItemWriter.write(chunk)
       |
       +--> Delegate A
       +--> Delegate B
       +--> Delegate C
       |
       v
Update stream state
       |
       v
Commit transaction
~~~

Nếu exception phát sinh và được transaction policy phân loại là lỗi cần rollback, transaction của chunk được rollback. Spring transaction mặc định thường rollback với RuntimeException và Error; checked exception cần được xem xét theo rollback rules của transaction attribute đang dùng.

Vì vậy, không chỉ nhìn thấy exception thoát khỏi writer là đủ để kết luận rollback luôn xảy ra. Hãy kiểm tra loại exception, transaction attribute và rollback classification của Step.

Nếu writer bắt exception rồi trả về bình thường, Step có thể tiếp tục commit như thể write đã thành công. Không nuốt lỗi ghi dữ liệu trừ khi có một chính sách xử lý rõ ràng và đã cập nhật trạng thái đầu ra một cách nhất quán.

## 7. Khi tất cả delegate ghi cùng database transaction

Nếu nhiều delegate ghi vào cùng database và cùng tham gia transaction của Step, lỗi ở delegate sau có thể rollback thay đổi của delegate trước.

Ví dụ:

- DatabaseOrderWriter dùng JdbcTemplate với DataSource của Step.
- AuditOrderWriter dùng cùng DataSource và transaction manager.
- Cả hai không tự commit riêng.
- AuditOrderWriter ném RuntimeException.

Kết quả dự kiến:

~~~text
Transaction T bắt đầu
   |
   +--> INSERT orders
   |
   +--> INSERT order_audit
   |        |
   |        +--> lỗi
   |
   v
ROLLBACK T
   |
   +--> orders không còn thay đổi của chunk
   +--> order_audit không còn thay đổi của chunk
~~~

Điều kiện quan trọng là cả hai thao tác thật sự tham gia cùng transaction. Cùng dùng một database server chưa đủ nếu mỗi delegate tự lấy connection và commit riêng.

Các thành phần Spring JDBC thường tham gia transaction hiện tại khi dùng đúng DataSource được quản lý. Hãy kiểm tra cấu hình DataSource, transaction manager và transaction propagation của service mà writer gọi.

## 8. Khi delegate dùng transaction riêng

Một delegate có thể dùng propagation REQUIRES_NEW hoặc tự mở connection rồi commit độc lập. Khi đó, transaction của delegate có thể hoàn tất trước khi transaction chunk bên ngoài kết thúc.

~~~text
Transaction chunk T1 bắt đầu
        |
        v
Delegate A gọi service REQUIRES_NEW
        |
        v
Transaction T2 commit thành công
        |
        v
Delegate B ném exception
        |
        v
T1 rollback
        |
        v
Thay đổi của A trong T2 vẫn còn
~~~

Tình huống này phá vỡ giả định một writer lỗi thì mọi ghi trước đó đều rollback.

Không dùng REQUIRES_NEW cho delegate chỉ vì muốn tách service. Hãy quyết định rõ liệu dữ liệu đó phải commit độc lập hay phải rollback cùng chunk. Nếu cần all-or-nothing trong cùng database, các delegate nên tham gia transaction của Step thay vì tự commit.

## 9. Khi delegate ghi ra nhiều loại resource

Composite có thể kết hợp các đích khác nhau:

- Database.
- File.
- HTTP API.
- Message broker.
- Object storage.
- Search index.
- Hệ thống audit bên ngoài.

Transaction manager cục bộ của database không tự động rollback các hệ thống ngoài. Ví dụ API đã nhận request hoặc broker đã nhận message thì database rollback không thu hồi được request/message đó.

~~~text
CompositeItemWriter
      |
      +--> Database: tham gia transaction T
      |
      +--> HTTP API: hệ thống ngoài
      |
      +--> Message broker: transaction riêng
~~~

Nếu delegate thứ ba thất bại, database có thể rollback, nhưng API hoặc broker có thể đã giữ side effect. Đây là vấn đề nhất quán giữa nhiều resource, không phải lỗi riêng của CompositeItemWriter.

Thứ tự writer chỉ quyết định side effect nào được thử trước. Nó không tạo distributed atomic commit.

## 10. Chọn thứ tự writer như thế nào?

Không có một thứ tự duy nhất đúng cho mọi ứng dụng. Hãy xem xét dependency và khả năng hoàn tác của từng delegate.

Một số nguyên tắc:

- Đặt các kiểm tra hoặc thao tác có thể fail sớm trước side effect không thể đảo ngược, nếu chúng không cần dữ liệu đã ghi.
- Gom các ghi database cần atomic vào cùng transaction.
- Tránh gửi message hoặc gọi API không idempotent trước khi dữ liệu nghiệp vụ được xác nhận.
- Dùng outbox để tách commit database khỏi publish ra ngoài.
- Đảm bảo các delegate sau có thể chạy lại an toàn sau rollback/retry.
- Ghi rõ dependency giữa các delegate trong cấu hình và test.

Ví dụ thứ tự:

~~~text
Validate / prepare
       |
       v
Database business write
       |
       v
Database outbox write
       |
       v
Commit chunk
       |
       v
Outbox publisher gửi event
~~~

Đây là mô hình thường dễ phục hồi hơn việc gọi API trực tiếp trong cùng CompositeItemWriter. Event chỉ được publish sau khi transaction nghiệp vụ đã commit và outbox worker có thể retry độc lập.

Nếu audit record phải commit cùng business record, hãy ghi audit vào cùng database transaction. Nếu audit là hệ thống ngoài, dùng outbox hoặc cơ chế giao nhận có idempotency.

## 11. Thứ tự không thay thế dependency management

Giả sử FileWriter cần mã ID được DatabaseWriter tạo ra. Nếu DatabaseWriter chạy trước nhưng chỉ tạo ID trong transaction chưa commit, FileWriter vẫn có thể dùng ID đã được trả về từ object hoặc repository tùy cách triển khai. Tuy nhiên, nếu FileWriter truy vấn database qua một connection khác, nó có thể chưa nhìn thấy dữ liệu chưa commit.

Đừng dựa vào thứ tự delegate để đảm bảo một writer sau nhìn thấy thay đổi chưa commit của writer trước trên một resource khác. Cần xác định transaction isolation, connection và dữ liệu được truyền trực tiếp qua item.

Nếu delegate B cần kết quả do A tạo, cách rõ ràng thường là:

- Processor chuẩn bị giá trị cần thiết trước writer.
- A cập nhật object theo hợp đồng rõ ràng nếu thiết kế cho phép.
- Dùng service chung để tạo dữ liệu trước composite.
- Tách thành Step sau nếu B cần đọc dữ liệu đã commit.

Không nên để các writer phụ thuộc ngầm vào side effect của writer đứng trước mà không có test cho transaction visibility.

## 12. Retry gọi lại composite từ đầu

Khi writer lỗi và Step được cấu hình retry, Spring Batch có thể thử lại chunk. Lời gọi retry đi qua CompositeItemWriter một lần nữa, bắt đầu từ delegate đầu tiên.

Ví dụ lần đầu:

~~~text
A.write(chunk) -> thành công
B.write(chunk) -> thành công
C.write(chunk) -> lỗi tạm thời
~~~

Lần retry:

~~~text
A.write(chunk) -> được gọi lại
B.write(chunk) -> được gọi lại
C.write(chunk) -> được gọi lại
~~~

Composite không lưu một cursor kiểu đã chạy tới delegate C để lần retry chỉ chạy lại C. Vì vậy, A và B có thể được gọi lại ngay cả khi chúng đã trả về bình thường trong lần trước.

Nếu A hoặc B thực hiện side effect ngoài transaction, lần retry có thể tạo duplicate. Đây là lý do tất cả delegate cần được đánh giá về idempotency và transaction participation.

## 13. Retry policy cho lỗi của delegate

Có thể cấu hình retry cho exception tạm thời:

~~~java
@Bean
public Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> compositeWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(compositeWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Trong ví dụ, Step thử lại lỗi thuộc nhóm transient theo retry limit đã cấu hình. Cần kiểm tra exception thực tế mà delegate ném ra hoặc bị bọc lại.

Retry phù hợp với deadlock, lỗi kết nối ngắn hạn hoặc lỗi dịch vụ được xác định là tạm thời. Không retry vô hạn lỗi validation, SQL sai, schema mismatch hoặc lỗi cấu hình.

Khi retry, transaction chunk thường được rollback theo rollback policy trước khi thực hiện lần thử tiếp theo. Nếu một delegate đã ghi ra ngoài transaction, retry không tự thu hồi side effect trước đó.

## 14. Write skip và composite writer

Write skip có thể khiến Spring Batch gọi lại writer với tập item nhỏ hơn để cô lập item gây lỗi. Vì composite writer là writer của Step, các delegate của nó có thể được gọi lại trong quá trình xác định item lỗi.

Ví dụ chunk ban đầu:

~~~text
[A, B, C, D]
~~~

Nếu lỗi ghi xuất phát từ B, framework có thể thử lại với các tập con hoặc từng item tùy cơ chế fault-tolerant và writer. Mỗi lần composite được gọi, nó lại chạy delegate theo thứ tự cấu hình.

Điều đó có nghĩa:

- Delegate A có thể nhận chunk gốc nhiều lần.
- Delegate B có thể nhận các subset trong quá trình cô lập lỗi.
- Delegate C chỉ được gọi nếu các delegate trước trong lần invocation đó trả về bình thường.
- Một side effect có thể lặp lại ngay cả khi item cuối cùng bị skip.

Không phải mọi writer đều hỗ trợ xác định item lỗi an toàn. Nếu delegate gửi một batch request tới API mà chỉ trả về lỗi chung, framework có thể không biết item nào gây lỗi. Hãy kiểm thử write skip với composite thực tế và chỉ cấu hình skip cho lỗi có thể phân loại.

## 15. Idempotency của từng delegate

Idempotency nghĩa là thực hiện lại cùng một thao tác không tạo thêm tác động ngoài ý muốn.

Ví dụ database upsert theo business key:

~~~sql
INSERT INTO order_export(order_id, status)
VALUES (:orderId, :status)
ON CONFLICT (order_id)
DO UPDATE SET status = EXCLUDED.status
~~~

Câu lệnh minh họa upsert theo khóa duy nhất; cú pháp cụ thể phụ thuộc database.

Với HTTP API, dùng idempotency key ổn định theo business operation, ví dụ order ID cộng với loại event. Với message broker, dùng event ID và consumer deduplication. Với file, dùng output path riêng theo JobExecution hoặc ghi staging theo cách có thể khôi phục.

Idempotency cần được thiết kế cho từng delegate. Chỉ làm writer thứ nhất idempotent không đủ nếu writer thứ hai hoặc thứ ba vẫn tạo side effect trùng.

## 16. Transactional outbox khi composite có API hoặc broker

Nếu Job cần lưu dữ liệu database và thông báo cho hệ thống khác, transactional outbox giúp giữ hai việc đầu tiên nhất quán trong một transaction.

~~~text
Composite writer trong chunk
       |
       +--> OrderRepository ghi order
       |
       +--> OutboxRepository ghi event
       |
       v
Chunk transaction COMMIT
       |
       v
Outbox publisher đọc event
       |
       v
HTTP API / Message broker
       |
       v
Đánh dấu event đã gửi
~~~

Nếu chunk rollback, order và outbox event cùng rollback. Nếu chunk commit rồi ứng dụng dừng, event vẫn nằm trong outbox để publisher xử lý sau.

Outbox publisher vẫn có thể gửi lại event nếu mất xác nhận hoặc crash giữa lúc gửi và cập nhật trạng thái. Vì vậy, hệ thống đích cần idempotency theo event ID hoặc cơ chế deduplication.

Với mô hình này, CompositeItemWriter có thể chỉ cần ghi các resource database trong transaction của Step. Việc gọi hệ thống ngoài được xử lý ở một worker riêng với retry và monitoring riêng.

## 17. File writer trong composite

FlatFileItemWriter là một writer thường được dùng cùng CompositeItemWriter. Writer chuẩn của Spring Batch có hỗ trợ transaction-aware buffering và ItemStream state khi được cấu hình đúng. Điều này giúp phối hợp việc ghi chunk với transaction của Step và hỗ trợ restart.

Tuy nhiên, không suy rộng behavior đó sang mọi custom file writer.

Một custom writer dùng Files.writeString(), FileOutputStream hoặc append trực tiếp có thể để lại dữ liệu đã ghi khi chunk rollback. Nếu composite retry, file có thể chứa duplicate.

Khi dùng file delegate:

- Ưu tiên FlatFileItemWriter hoặc writer có transaction/restart semantics rõ ràng.
- Dùng tên writer ổn định và saveState khi cần restart.
- Giữ output resource ổn định qua restart.
- Không để consumer đọc file đang được ghi dở.
- Cân nhắc staging và publish sau khi Job hoàn tất.
- Kiểm tra behavior khi delegate sau thất bại.

Nếu file là output cuối cùng cần publish, một Step cuối có thể đổi tên staging file sau khi các Step ghi dữ liệu hoàn tất.

## 18. ItemStream lifecycle của delegate

Một số writer triển khai ItemStream để mở resource, lưu state và đóng resource. CompositeItemWriter cũng hỗ trợ lifecycle để quản lý các delegate stream theo cấu hình.

Với cấu hình mặc định, CompositeItemWriter có thể chuyển tiếp open, update và close tới các delegate triển khai ItemStream. Builder có tùy chọn ignoreItemStream trong các phiên bản hỗ trợ; bật tùy chọn này nghĩa là composite không tự chuyển tiếp lifecycle tới delegate.

Hãy bảo đảm mọi ItemStream delegate được đăng ký và lifecycle được gọi đúng một lần theo thiết kế. Nếu một delegate không nhận open(), file writer có thể chưa mở resource; nếu không nhận update(), checkpoint có thể không được lưu; nếu không nhận close(), resource có thể bị rò rỉ.

Ví dụ cấu hình composite với các delegate:

~~~java
@Bean
public CompositeItemWriter<Order> orderCompositeWriter(
        FlatFileItemWriter<Order> fileWriter,
        JdbcBatchItemWriter<Order> databaseWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
~~~

Với delegate có state, hãy kiểm tra version API và cách composite đăng ký ItemStream. Nếu cấu trúc wrapper lồng nhau hoặc delegate được tạo bên trong custom component, có thể cần đăng ký stream tường minh với Step bằng stream(...). Tránh đăng ký trùng một stream nếu composite đã quản lý nó.

## 19. Không để writer che giấu lỗi

Một delegate không nên bắt exception rồi trả về bình thường nếu thao tác ghi thất bại.

Ví dụ không an toàn:

~~~java
public void write(Chunk<? extends Order> chunk) {
    try {
        externalClient.send(chunk.getItems());
    } catch (Exception exception) {
        log.error("External write failed", exception);
        // Trả về bình thường.
    }
}
~~~

Composite sẽ coi delegate này đã hoàn tất và tiếp tục gọi delegate sau. Step có thể commit chunk dù external write không thành công.

Cách phù hợp hơn là truyền exception ra ngoài:

~~~java
public void write(Chunk<? extends Order> chunk) throws Exception {
    externalClient.send(chunk.getItems());
}
~~~

Nếu cần chuyển đổi exception, hãy giữ cause và dùng loại exception có ý nghĩa để retry/skip classifier phân loại được.

Nếu nghiệp vụ cho phép chấp nhận lỗi của một đích, hãy ghi trạng thái lỗi một cách bền vững và có quy trình retry/repair riêng. Không biến lỗi thành log-only rồi báo chunk thành công.

## 20. noRollback không sửa được side effect một phần

Có thể cấu hình exception không làm rollback transaction bằng noRollback hoặc rollback classifier tương ứng. Tuy nhiên, việc này không biến nhiều delegate thành một giao dịch nguyên tử.

Nếu DatabaseWriter đã ghi dữ liệu và FileWriter ném exception nhưng exception được phân loại no-rollback, transaction có thể commit phần database dù file chưa được tạo đầy đủ. Đây thường là trạng thái không mong muốn.

Chỉ dùng noRollback khi nghiệp vụ thực sự muốn giữ các thay đổi transaction dù exception đó xảy ra và các writer có thể tiếp tục nhất quán. Với lỗi ghi một delegate, mặc định thường nên rollback chunk hoặc dùng một workflow phục hồi riêng.

Không dùng noRollback chỉ để tránh gọi lại delegate trước. Cách đó có thể che giấu dữ liệu dở dang và làm checkpoint tiến lên dù một đích chưa nhận được dữ liệu.

## 21. Ví dụ lỗi ở delegate thứ hai

Giả sử composite có ba writer:

~~~java
@Bean
public CompositeItemWriter<Order> compositeWriter(
        ItemWriter<Order> databaseWriter,
        ItemWriter<Order> auditWriter,
        ItemWriter<Order> notificationWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(
                    databaseWriter,
                    auditWriter,
                    notificationWriter)
            .build();
}
~~~

AuditWriter ném exception sau khi databaseWriter trả về:

~~~text
Chunk transaction T bắt đầu
       |
       v
databaseWriter.write(chunk)
       |
       | insert order trong T
       v
auditWriter.write(chunk)
       |
       | lỗi
       v
notificationWriter không được gọi
       |
       v
Exception thoát khỏi composite
       |
       v
T rollback nếu exception được phân loại rollback
       |
       v
Order insert trong T được hoàn tác
~~~

Nếu databaseWriter tự commit bằng transaction riêng, dữ liệu order có thể còn lại. Nếu auditWriter ghi một phần ra hệ thống ngoài rồi mới ném exception, phần side effect đó cũng có thể còn lại.

Để kiểm thử đúng, cần dùng database transaction thật hoặc test double có semantics rõ ràng, không chỉ mock composite và xác nhận exception được ném.

## 22. Ví dụ theo dõi thứ tự gọi delegate

Có thể dùng test double để xác nhận thứ tự:

~~~java
@Test
void invokesDelegatesInConfiguredOrder() throws Exception {
    List<String> calls = new ArrayList<>();

    ItemWriter<Order> first = chunk -> calls.add("first");
    ItemWriter<Order> second = chunk -> calls.add("second");
    ItemWriter<Order> third = chunk -> calls.add("third");

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(first, second, third)
                    .build();

    composite.write(new Chunk<>(List.of(new Order())));

    assertEquals(
            List.of("first", "second", "third"),
            calls);
}
~~~

Test này xác nhận composite gọi delegate theo thứ tự cấu hình. Nó không kiểm tra transaction hoặc rollback.

Thêm test khi delegate thứ hai ném exception:

~~~java
@Test
void stopsCallingDelegatesAfterFailure() {
    List<String> calls = new ArrayList<>();

    ItemWriter<Order> first = chunk -> calls.add("first");

    ItemWriter<Order> failing = chunk -> {
        calls.add("failing");
        throw new IllegalStateException("write failed");
    };

    ItemWriter<Order> third = chunk -> calls.add("third");

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(first, failing, third)
                    .build();

    assertThrows(
            IllegalStateException.class,
            () -> composite.write(
                    new Chunk<>(List.of(new Order()))));

    assertEquals(List.of("first", "failing"), calls);
}
~~~

Trong test thực tế, dùng item model hợp lệ của dự án. Assertion quan trọng là delegate thứ ba không được gọi sau khi delegate thứ hai ném exception.

## 23. Kiểm thử rollback giữa nhiều database delegate

Một integration test nên xác nhận các writer dùng chung transaction thực sự rollback cùng nhau.

Kịch bản:

1. DatabaseWriter insert order.
2. AuditWriter insert audit record rồi ném RuntimeException.
3. NotificationWriter không được gọi.
4. Step rollback transaction chunk.
5. Truy vấn database bằng transaction độc lập.
6. Xác nhận cả order và audit record của chunk đều không còn.

Điều kiện test:

- Các writer dùng cùng DataSource được quản lý.
- Cùng transaction manager được truyền cho Step.
- Không có REQUIRES_NEW hoặc tự commit.
- Exception thoát ra và được rollback policy xử lý.
- Không bọc test bằng transaction ngoài làm sai quan sát.

Nếu test chỉ dùng mock repository, nó không chứng minh transaction manager đã rollback database.

## 24. Kiểm thử external side effect

Với API hoặc broker, cần chứng minh side effect ngoài transaction có thể tồn tại sau rollback.

Ví dụ:

~~~text
Delegate A: gửi API thành công
Delegate B: ghi database rồi ném lỗi
Chunk transaction: rollback
API: request vẫn đã được nhận
~~~

Test có thể dùng mock server hoặc broker test container:

- Xác nhận API nhận request trước khi delegate sau lỗi.
- Xác nhận database rollback.
- Chạy retry hoặc restart.
- Xác nhận idempotency key ngăn request tạo tác động trùng.

Nếu dùng outbox, test riêng trường hợp transaction rollback không tạo outbox event và transaction commit tạo đúng một event logic. Sau đó test publisher retry và consumer deduplication.

## 25. Kiểm thử ItemStream delegate

Nếu delegate có state, hãy kiểm tra lifecycle:

- open() được gọi khi Step bắt đầu.
- update() được gọi tại checkpoint.
- close() được gọi khi Step kết thúc.
- State được lưu trong ExecutionContext.
- Restart khôi phục đúng vị trí hoặc output state.
- Một delegate ném lỗi không làm các resource khác bị bỏ quên mà không có cleanup.

Với composite lồng nhau, kiểm tra stream được đăng ký đúng. Nếu bật ignoreItemStream, phải có cơ chế đăng ký delegate streams riêng; nếu không, reader/writer có thể không khôi phục được state.

Không chỉ xác nhận file đã được ghi. Hãy restart một Step test và kiểm tra dữ liệu không bị lặp hoặc mất.

## 26. Monitoring lỗi theo delegate

ItemWriteListener của Step quan sát lời gọi write của writer được đăng ký trong Step. Khi Step dùng CompositeItemWriter, listener ở cấp Step thường thấy composite invocation, không tự động cung cấp đầy đủ tên delegate nội bộ gây lỗi.

Có thể bọc từng delegate để ghi log hoặc metrics riêng:

~~~java
public class ObservedOrderWriter implements ItemWriter<Order> {

    private final String writerName;
    private final ItemWriter<Order> delegate;

    public ObservedOrderWriter(
            String writerName,
            ItemWriter<Order> delegate) {
        this.writerName = writerName;
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        try {
            delegate.write(chunk);
        } catch (Exception exception) {
            log.error(
                    "Delegate {} failed for {} items",
                    writerName,
                    chunk.size(),
                    exception);
            throw exception;
        }
    }
}
~~~

Wrapper phải truyền exception ra ngoài để Spring Batch vẫn áp dụng rollback/retry/skip. Không log toàn bộ payload nếu dữ liệu nhạy cảm.

Metrics nên ghi:

- Tên delegate.
- Số lần gọi.
- Số item trong chunk.
- Thời gian thực thi.
- Số lỗi theo exception type.
- JobExecution và StepExecution ID.
- Business key hoặc correlation ID phù hợp.

Các metrics này giúp phân biệt lỗi ở database writer, audit writer hay file writer thay vì chỉ thấy CompositeItemWriter failed.

## 27. Composite writer lồng nhau

Có thể một delegate bản thân nó là CompositeItemWriter khác. Khi đó thứ tự thực tế là thứ tự duyệt theo từng tầng.

~~~text
OuterComposite
    |
    +--> DatabaseWriter
    |
    +--> InnerComposite
            |
            +--> AuditWriter
            |
            +--> FileWriter
    |
    +--> MetricsWriter
~~~

Nếu AuditWriter lỗi, FileWriter trong inner composite và MetricsWriter của outer composite không được gọi trong lần invocation đó. DatabaseWriter đã được gọi trước đó.

Cấu trúc lồng nhau có thể hữu ích khi nhóm các đích theo trách nhiệm, nhưng làm thứ tự và failure path khó quan sát hơn. Hãy giữ cấu trúc đơn giản, đặt tên delegate rõ ràng và có test cho lỗi ở từng tầng.

Đừng tạo nhiều tầng composite chỉ để gom bean nếu không có ranh giới nghiệp vụ hoặc lifecycle rõ ràng.

## 28. Delegate cần nhận cùng kiểu dữ liệu

CompositeItemWriter<T> gửi cùng chunk T tới các delegate. Nếu một đích cần Order và đích khác cần AuditEvent, có thể dùng adapter writer để chuyển đổi từng Order thành AuditEvent.

~~~java
public class OrderAuditWriter implements ItemWriter<Order> {

    private final ItemWriter<AuditEvent> auditWriter;

    public OrderAuditWriter(ItemWriter<AuditEvent> auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        List<AuditEvent> events = chunk.getItems().stream()
                .map(order -> new AuditEvent(
                        order.id(),
                        "ORDER_EXPORTED"))
                .toList();

        auditWriter.write(new Chunk<>(events));
    }
}
~~~

Adapter làm rõ việc chuyển kiểu và cho phép composite vẫn làm việc với Order. Cần bảo đảm adapter không bỏ item hoặc thay đổi thứ tự ngoài ý muốn.

Nếu các đích cần dữ liệu được tạo từ những nguồn hoàn toàn khác nhau, có thể Step riêng hoặc event-driven pipeline rõ ràng hơn một composite với nhiều adapter phức tạp.

## 29. Writer sau có thể không được gọi và dữ liệu cần đối soát

Khi một delegate thất bại, các delegate sau không được gọi trong lần composite invocation đó. Nếu lỗi không được retry hoặc Step bị fail, hệ thống cần biết đích nào đã nhận dữ liệu và đích nào chưa.

Không nên chỉ dựa vào log để tái dựng trạng thái trong hệ thống nhiều resource. Cần có business key, event ID hoặc export batch ID để đối soát.

Một bảng trạng thái có thể theo dõi:

| Đích | Trạng thái |
|---|---|
| Database | COMMITTED / ROLLED_BACK |
| Audit store | PENDING / SENT / FAILED |
| File output | STAGING / PUBLISHED / FAILED |
| External API | PENDING / ACKNOWLEDGED / UNKNOWN |

Đặc biệt với timeout, trạng thái UNKNOWN có thể xảy ra: client không biết hệ thống ngoài đã nhận request hay chưa. Khi đó phải query theo idempotency key hoặc đối soát bằng business key trước khi gửi lại.

## 30. Những lỗi thường gặp

### Nghĩ composite chạy các delegate song song

Composite gọi tuần tự theo thứ tự cấu hình. Delegate sau chỉ chạy khi delegate trước trả về bình thường.

### Nghĩ lỗi một writer tự rollback mọi writer trước

Rollback chỉ áp dụng cho resource tham gia transaction có thể rollback. API, message broker hoặc transaction độc lập có thể giữ side effect.

### Nghĩ retry chỉ gọi lại delegate bị lỗi

Retry gọi lại composite cho chunk, nên các delegate trước có thể được gọi lại. Thiết kế idempotency cho mọi delegate.

### Nghĩ delegate sau vẫn được gọi sau exception

Exception làm dừng chuỗi gọi. Nếu muốn tiếp tục bất chấp lỗi, cần một chính sách ghi nhận lỗi riêng và quyết định rõ chunk có được commit hay không.

### Bắt exception rồi chỉ log

Composite coi delegate đã hoàn tất và có thể tiếp tục. Exception cần được truyền ra ngoài nếu write thực sự thất bại.

### Dùng REQUIRES_NEW mà vẫn mong rollback cùng chunk

Transaction độc lập đã commit không bị rollback bởi transaction chunk. Xác định rõ propagation.

### Đổi thứ tự delegate mà không kiểm thử

Side effect và failure path thay đổi. Viết test xác nhận order và lỗi tại từng vị trí.

### Dùng writer không idempotent trong retry/skip

Delegate có thể được gọi lại với cùng chunk hoặc subset. Dùng unique key, idempotency key, outbox hoặc staging.

### Bỏ qua ItemStream lifecycle

Delegate không mở, cập nhật state hoặc đóng resource đúng cách. Bảo đảm stream được composite quản lý hoặc đăng ký riêng.

### Dùng noRollback để giữ dữ liệu ghi dở

Có thể commit một phần trong khi delegate khác thất bại. Chỉ dùng khi semantics nghiệp vụ đã được xác định và test.

### Không kiểm tra transaction manager thực tế

Hai writer cùng database nhưng dùng connection hoặc transaction khác nhau có thể không rollback cùng nhau. Kiểm tra DataSource, propagation và transaction manager.

## 31. Quy trình thiết kế composite writer

Trước khi ghép nhiều writer vào một Step, hãy xác định:

1. Mỗi delegate ghi vào resource nào?
2. Thứ tự gọi có dependency nghiệp vụ gì?
3. Mỗi delegate nhận cùng chunk hay cần subset/biến đổi riêng?
4. Delegate nào có thể ném exception và loại exception nào?
5. Exception có được truyền ra ngoài composite không?
6. Các database delegate có tham gia cùng transaction của Step không?
7. Có delegate nào dùng REQUIRES_NEW hoặc tự commit không?
8. Resource ngoài transaction có thể giữ side effect sau rollback không?
9. Retry sẽ gọi lại những delegate nào?
10. Write skip có thể gọi writer với chunk subset ra sao?
11. Từng delegate có idempotent không?
12. Có cần outbox, idempotency key hoặc đối soát không?
13. ItemStream lifecycle của delegate được quản lý ở đâu?
14. Metrics/log có chỉ ra chính xác delegate gây lỗi không?
15. Integration test có xác nhận rollback, retry, skip và external side effect không?

CompositeItemWriter thực hiện các delegate tuần tự theo thứ tự cấu hình và dừng ngay khi một delegate ném exception. Step sau đó áp dụng transaction và fault-tolerance policy cho toàn bộ lời gọi writer. Các thay đổi trong cùng transaction có thể rollback cùng nhau, nhưng side effect ở resource độc lập có thể còn tồn tại và delegate trước có thể được gọi lại khi retry hoặc write skip. Hãy thiết kế thứ tự dựa trên dependency, giữ các ghi database cần atomic trong cùng transaction, dùng idempotency/outbox cho hệ thống ngoài và kiểm thử lỗi ở từng vị trí delegate để Job có thể phục hồi mà không tạo dữ liệu trùng hoặc trạng thái không nhất quán.
