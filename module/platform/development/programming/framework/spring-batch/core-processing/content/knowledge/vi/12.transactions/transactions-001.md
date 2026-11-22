# Transaction boundary của chunk step trong Spring Batch

Trong Spring Batch, chunk-oriented step xử lý dữ liệu theo từng nhóm item. Một nhóm được đọc, xử lý và ghi trong một transaction; khi transaction commit, những thay đổi của chunk đó trở thành kết quả đã xác nhận. Nếu chunk thất bại và transaction rollback, các thay đổi transactional của chunk hiện tại được hoàn tác, còn những chunk đã commit trước đó vẫn được giữ lại.

Hiểu đúng **transaction boundary** giúp xác định dữ liệu nào được commit cùng nhau, vì sao một phần job có thể đã hoàn tất trước khi lỗi xảy ra, và điều gì cần thiết để retry hoặc restart an toàn. Ranh giới transaction của chunk cũng giải thích vì sao một lần rollback database không thể tự hoàn tác email, HTTP request hay message đã gửi đến hệ thống bên ngoài.

## 1. Transaction boundary là gì?

Transaction boundary là khoảng thời gian mà một nhóm thao tác được quản lý như một đơn vị commit hoặc rollback. Với chunk-oriented step, Spring Batch thường mở một transaction cho mỗi chunk.

Ví dụ, một step có commit interval bằng 100:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Giá trị `100` xác định số item đầu vào tối đa được gom cho một chunk trước khi commit. Nó không có nghĩa toàn bộ job nằm trong một transaction, cũng không có nghĩa mỗi item có một transaction riêng.

Nếu nguồn có 250 item, một cách chia thông thường là:

```text
Chunk 1: item 1..100     -> transaction 1 -> COMMIT
Chunk 2: item 101..200  -> transaction 2 -> COMMIT
Chunk 3: item 201..250  -> transaction 3 -> COMMIT
```

Mỗi chunk có transaction boundary riêng. Nếu chunk 3 thất bại, chunk 1 và chunk 2 đã commit vẫn tồn tại. Spring Batch không tự quay ngược toàn bộ job về trạng thái trước chunk 1.

## 2. Vòng đời của một chunk transaction

Ở mức khái niệm, một lần xử lý chunk diễn ra như sau:

1. Spring Batch bắt đầu transaction bằng `PlatformTransactionManager` được cấu hình cho step.
2. Reader cung cấp các item cho đến khi đủ commit interval hoặc reader báo hết input.
3. Processor xử lý từng item nếu step có processor.
4. Writer ghi các output item của chunk.
5. Spring Batch cập nhật trạng thái và execution context cần thiết cho step.
6. Transaction commit; chunk được xác nhận hoàn tất.
7. Step bắt đầu transaction tiếp theo để xử lý chunk kế tiếp.

```text
Step bắt đầu
    |
    v
BEGIN TRANSACTION
    |
    v
READ -> PROCESS -> WRITE
    |
    v
Cập nhật checkpoint / step state
    |
    v
COMMIT
    |
    +---- còn input? ---- Có ----> BEGIN transaction tiếp theo
    |
    +---- Không ----------------> Step hoàn tất
```

Nếu thao tác trong chunk gây ra exception cần rollback, transaction hiện tại bị rollback theo transaction attribute và fault-tolerance policy. Nếu exception được retry hoặc skip, Spring Batch điều phối lại theo cấu hình; nếu không thể phục hồi, step/job kết thúc thất bại.

Chi tiết nội bộ có thể khác theo reader, writer, transaction manager và chính sách retry/skip, nhưng nguyên tắc quan trọng vẫn là các thao tác transactional của một chunk được gom trong cùng ranh giới commit.

## 3. Những thao tác nào nằm trong transaction của chunk?

Với chunk step thông thường, việc đọc, xử lý và ghi được thực hiện trong vòng xử lý chunk do transaction quản lý. Điều đó không đồng nghĩa mọi tài nguyên mà các thành phần chạm tới đều tự động tham gia transaction.

| Thành phần/thao tác | Có nằm trong transaction chunk không? | Điều kiện hoặc lưu ý |
| --- | --- | --- |
| Reader đọc từ database | Có thể | Cần dùng tài nguyên và transaction manager phù hợp; cursor/paging reader có quy tắc riêng. |
| Processor tính toán trong bộ nhớ | Chạy trong vòng xử lý chunk | Thay đổi object trong bộ nhớ không tự trở thành dữ liệu bền vững. |
| Writer ghi cùng database transaction | Có | Phải tham gia cùng transaction manager và cùng tài nguyên transaction. |
| Cập nhật metadata step | Được Spring Batch quản lý | Tính nguyên tử với dữ liệu nghiệp vụ phụ thuộc cấu hình repository và tài nguyên transaction. |
| Gọi HTTP API | Thông thường không | HTTP service bên ngoài không tự tham gia transaction database. |
| Gửi email hoặc SMS | Không | Không thể thu hồi bằng rollback database. |
| Publish message đến broker | Chỉ khi có cơ chế enlistment phù hợp | Một lời gọi publish thông thường không tự động cùng transaction với database. |
| Ghi file hoặc object storage | Thông thường không | Cần cơ chế staging, commit/rename hoặc bù trừ riêng. |

Ví dụ, nếu writer dùng `JdbcTemplate` với cùng `DataSource` và transaction manager của step, các câu lệnh ghi có thể tham gia transaction chunk. Nếu writer gọi một REST API, transaction database không thể buộc API đó hoàn tác khi chunk rollback.

## 4. Vai trò của PlatformTransactionManager

`PlatformTransactionManager` là abstraction Spring dùng để bắt đầu, commit và rollback transaction. Khi tạo chunk step, ứng dụng truyền transaction manager cho builder:

```java
new StepBuilder("processStep", jobRepository)
    .<Input, Output>chunk(50, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
```

Transaction manager phải phù hợp với tài nguyên cần được bảo vệ. Ví dụ:

- `DataSourceTransactionManager` (hoặc `JdbcTransactionManager` trong Spring Framework hiện đại) quản lý transaction JDBC cho một datasource.
- `JpaTransactionManager` quản lý transaction JPA cho `EntityManagerFactory` tương ứng.
- `JtaTransactionManager` có thể điều phối transaction phân tán khi các resource hỗ trợ XA và được cấu hình đúng.

Nếu ứng dụng có nhiều datasource, việc inject nhầm transaction manager có thể khiến writer ghi vào database không được quản lý bởi transaction của step. Khi đó, chunk rollback không hoàn tác được phần ghi ở datasource kia.

Trong ứng dụng có nhiều transaction manager, nên dùng `@Qualifier` để chỉ định rõ manager dành cho chunk step và bảo đảm các repository/writer cần tham gia transaction được cấu hình tương ứng.

## 5. Rollback ảnh hưởng đến chunk như thế nào?

Giả sử commit interval bằng 3. Chunk đầu ghi ba item và commit thành công. Chunk thứ hai ghi hai item nhưng item thứ ba gây lỗi trong writer:

```text
Chunk 1: [A, B, C]
  BEGIN -> WRITE A,B,C -> COMMIT

Chunk 2: [D, E, F]
  BEGIN -> WRITE D,E -> lỗi khi ghi F -> ROLLBACK

Kết quả database transactional:
  A, B, C: còn lại (chunk 1 đã commit)
  D, E, F: không có thay đổi của chunk 2 được commit
```

Điều kiện để ví dụ này đúng là các thao tác ghi A, B, C, D, E, F đều tham gia cùng transaction manager và cùng tài nguyên transactional. Nếu writer ghi sang hệ thống ngoài transaction, phần ghi đó có thể vẫn tồn tại sau rollback.

Rollback không nhất thiết đưa mọi thành phần trong bộ nhớ về trạng thái ban đầu. Một object Java đã bị sửa, biến đếm trong singleton hoặc cursor của nguồn ngoài database có thể vẫn thay đổi. Transaction manager chỉ hoàn tác những thao tác thuộc tài nguyên mà nó quản lý.

## 6. Retry và skip trong ranh giới transaction

Fault-tolerant chunk step có thể được cấu hình để retry lỗi tạm thời hoặc skip item lỗi:

```java
@Bean
Step resilientImportStep(JobRepository jobRepository,
                         PlatformTransactionManager transactionManager,
                         ItemReader<Order> reader,
                         ItemProcessor<Order, OrderEntity> processor,
                         ItemWriter<OrderEntity> writer) {
    return new StepBuilder("resilientImportStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
```

Khi lỗi cần retry xảy ra, chunk có thể rollback rồi được thử lại theo chính sách. Với lỗi được phép skip, framework xử lý exception theo skip policy và tiếp tục nếu reader/processor/writer có thể phục hồi an toàn.

Các điểm cần nhớ:

- Retry có thể khiến một phần logic trong chunk được thực hiện lại.
- Skip không có nghĩa transaction không rollback; một số tình huống vẫn cần rollback để framework cô lập item lỗi.
- `skipLimit` là giới hạn tổng số skip của step theo chính sách, không phải giới hạn độc lập cho từng phase đọc, xử lý và ghi.
- Các chunk đã commit trước đó vẫn được giữ lại khi chunk sau rollback.
- Không được đặt side effect ngoài transaction trong processor hoặc writer rồi giả định rollback sẽ xóa tác động đó.

Không nên cấu hình skip quá rộng chỉ để job luôn chạy đến cuối. Lỗi kết nối, lỗi xác thực hoặc lỗi làm mất khả năng xác định vị trí đọc thường cần dừng job thay vì bỏ qua.

## 7. Transaction boundary và restart

Spring Batch dùng `JobRepository` cùng `ExecutionContext` để lưu metadata và checkpoint. Với reader hỗ trợ restart, trạng thái đọc thường được cập nhật ở ranh giới chunk để lần restart có thể tiếp tục từ checkpoint cuối đã commit.

Ví dụ, job đọc file với commit interval 100:

```text
Chunk 1: dòng 1..100    -> ghi + checkpoint -> COMMIT
Chunk 2: dòng 101..200  -> ghi + checkpoint -> COMMIT
Chunk 3: dòng 201..300  -> lỗi trước commit

Restart:
  Khôi phục checkpoint của chunk 2
  Tiếp tục đọc từ vị trí phù hợp sau dòng 200
```

Nếu chunk 3 chưa commit, trạng thái bền vững thường vẫn là checkpoint của chunk 2. Reader có thể đọc lại các item thuộc chunk 3. Writer cần an toàn khi thực hiện lại nếu có nguy cơ tác động đã xảy ra bên ngoài transaction.

`ItemStream` cung cấp các callback liên quan đến trạng thái reader/writer:

- `open(ExecutionContext)` khôi phục hoặc khởi tạo trạng thái.
- `update(ExecutionContext)` ghi checkpoint vào execution context.
- `close()` giải phóng tài nguyên.

Reader tùy chỉnh cần lưu trạng thái đủ để tiếp tục từ checkpoint. Nếu reader tiêu thụ message từ queue hoặc gọi API có cursor, rollback database không tự đưa nguồn bên ngoài về vị trí cũ. Cần thiết kế ack, offset, token hoặc idempotency phù hợp với nguồn đó.

## 8. Job không nằm trong một transaction duy nhất

Một job có thể chạy nhiều step và mỗi step có nhiều chunk. Spring Batch không mặc định mở một transaction kéo dài từ đầu đến cuối toàn job. Với chunk step, mỗi chunk có transaction riêng; các step cũng có vòng đời và transaction riêng.

Ví dụ:

```text
Job: dailyImport
  |
  +-- ValidateStep
  |     transaction theo cấu hình step
  |
  +-- ImportStep
  |     Chunk 1 -> transaction -> commit
  |     Chunk 2 -> transaction -> commit
  |     Chunk 3 -> transaction -> commit
  |
  +-- ReportStep
        transaction theo cấu hình step
```

Nếu `ReportStep` thất bại, các chunk của `ImportStep` đã commit vẫn tồn tại. Muốn chạy lại toàn bộ nghiệp vụ từ đầu cần một thiết kế reprocess riêng, identifying parameters phù hợp và cơ chế xử lý dữ liệu đã ghi. Không thể dùng một rollback toàn job để hoàn tác các chunk đã commit trước đó.

## 9. Điều chỉnh commit interval và ảnh hưởng đến transaction

Commit interval quyết định kích thước chunk và tần suất commit. Chọn giá trị phù hợp là một quyết định về hiệu năng, tài nguyên và khả năng phục hồi.

| Commit interval | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Nhỏ | Transaction ngắn, rollback ít item hơn, checkpoint thường xuyên. | Tăng số lần commit và overhead transaction/metadata. |
| Lớn | Giảm số lần commit, có thể tăng throughput với writer hiệu quả theo batch. | Transaction dài hơn, giữ tài nguyên lâu hơn và rollback có thể ảnh hưởng nhiều item hơn. |

Ví dụ:

- Interval 1 phù hợp khi mỗi item cần transaction riêng hoặc muốn ranh giới commit rất nhỏ, nhưng chi phí commit có thể cao.
- Interval 100 thường phù hợp với nhiều tác vụ nhập dữ liệu, nhưng cần đo với kích thước record và database thực tế.
- Interval 5.000 có thể hiệu quả với writer bulk, nhưng transaction dài có thể giữ lock, connection và bộ nhớ lâu hơn.

Không có một commit interval tối ưu cho mọi job. Hãy đo throughput, thời gian transaction, lock wait, connection usage, rollback rate và khả năng restart trước khi chọn.

## 10. Cấu hình transaction attribute cho chunk step

Ngoài transaction manager, step có thể nhận `TransactionAttribute` để điều chỉnh isolation level, timeout và propagation behavior theo nhu cầu.

Ví dụ đặt isolation level và timeout:

```java
@Bean
Step controlledImportStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager,
                          ItemReader<Order> reader,
                          ItemWriter<Order> writer) {
    DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
    transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
    transactionAttribute.setTimeout(120);

    return new StepBuilder("controlledImportStep", jobRepository)
        .<Order, Order>chunk(200, transactionManager)
        .reader(reader)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
}
```

`READ_COMMITTED` và timeout 120 giây chỉ là ví dụ. Isolation level được database hỗ trợ và thực thi theo cách riêng; chọn mức cao hơn có thể tăng lock hoặc giảm concurrency. Timeout cần phù hợp với thời gian xử lý bình thường của một chunk và timeout ở database/driver.

Propagation mặc định thường là `REQUIRED`, nghĩa là thao tác transactional bên trong tham gia transaction hiện tại nếu dùng cùng transaction manager. Hãy thận trọng khi một service được gọi từ processor hoặc writer dùng `REQUIRES_NEW`: transaction mới có thể commit độc lập và vẫn tồn tại dù transaction chunk bên ngoài rollback.

Nếu cần rollback cho checked exception hoặc loại exception cụ thể, hãy cấu hình rollback rule phù hợp với `TransactionAttribute` và fault-tolerance policy. Không nên giả định mọi loại exception đều có cùng hành vi rollback mà không kiểm tra transaction configuration.

## 11. Transaction boundary của service được gọi từ processor hoặc writer

Một service có thể được đánh dấu `@Transactional`. Việc service tham gia transaction chunk phụ thuộc propagation, transaction manager và cách gọi qua Spring proxy.

Ví dụ service dùng `REQUIRED`:

```java
@Service
public class OrderPersistenceService {

    private final OrderRepository repository;

    public OrderPersistenceService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void save(OrderEntity order) {
        repository.save(order);
    }
}
```

Nếu service được gọi từ writer đang chạy trong chunk transaction và cùng dùng transaction manager, `REQUIRED` thường tham gia transaction hiện tại. Khi chunk rollback, thao tác save cũng rollback.

Ngược lại:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(AuditEvent event) {
    auditRepository.save(event);
}
```

`REQUIRES_NEW` tạm ngưng transaction hiện tại và mở transaction riêng. Nếu transaction audit commit rồi chunk bên ngoài rollback, bản ghi audit vẫn tồn tại. Đây có thể là hành vi mong muốn cho audit sự cố, nhưng có thể gây sai lệch nếu bản ghi audit được hiểu là xác nhận nghiệp vụ đã hoàn tất.

Ngoài propagation, cần lưu ý self-invocation: gọi một method `@Transactional` từ method khác trong cùng object thường không đi qua Spring proxy nên annotation có thể không được áp dụng như mong đợi. Hãy đặt transaction boundary ở service bean phù hợp và kiểm tra cấu hình thật.

## 12. Tài nguyên bên ngoài transaction và transactional outbox

Rollback database chỉ hoàn tác tài nguyên được transaction manager quản lý. Ví dụ, nếu processor gửi email rồi writer ghi database thất bại, email đã gửi không thể được thu hồi bằng rollback.

Với message hoặc API cần phát đi sau khi dữ liệu được commit, có thể dùng transactional outbox:

```text
Chunk transaction
  |
  +-- Ghi dữ liệu nghiệp vụ
  |
  +-- Ghi outbox event
  |
  +-- COMMIT cả hai trong cùng database
           |
           v
Outbox dispatcher
  |
  +-- Đọc event PENDING
  +-- Gửi message / gọi API
  +-- Đánh dấu đã gửi
```

Outbox bảo đảm dữ liệu nghiệp vụ và ý định gửi event được lưu cùng transaction nếu cùng database và transaction manager. Dispatcher có thể gửi lại khi timeout hoặc dừng giữa lúc publish và cập nhật trạng thái; vì vậy consumer/API đích vẫn cần idempotency key ổn định.

Nếu nhiều resource phải commit nguyên tử, có thể cân nhắc JTA/XA khi tất cả resource hỗ trợ và vận hành được. Tuy nhiên, XA làm tăng độ phức tạp và không áp dụng cho mọi API hoặc dịch vụ. Outbox thường là lựa chọn thực tế hơn cho tích hợp message/API.

## 13. Listener và thời điểm trong transaction

Chunk step cung cấp các listener để quan sát vòng đời xử lý. Cần hiểu callback chạy ở thời điểm nào trước khi đặt logic vào đó:

| Callback | Thời điểm khái quát | Cách dùng phù hợp |
| --- | --- | --- |
| `beforeChunk` | Sau khi transaction chunk bắt đầu, trước khi xử lý chunk. | Ghi trace/metric bắt đầu chunk. |
| `afterChunk` | Sau khi chunk commit thành công. | Ghi nhận metric hoặc thông tin quan sát sau commit. |
| `afterChunkError` | Khi xử lý chunk gặp lỗi/rollback. | Ghi log, metric lỗi hoặc chẩn đoán. |
| `ItemWriteListener.afterWrite` | Sau lời gọi writer nhưng trước khi chunk transaction chắc chắn commit. | Quan sát kết quả writer; không giả định commit đã thành công. |

Không nên gửi email hoặc publish message trực tiếp từ listener với kỳ vọng callback sẽ cung cấp exactly-once. Ngay cả `afterChunk`, tiến trình vẫn có thể dừng sau database commit nhưng trước khi tác động bên ngoài hoàn tất. Nếu tác động phải được thực hiện đáng tin cậy, hãy ghi outbox event trong transaction và dispatch riêng.

## 14. Kiểm thử transaction boundary

Một cách hữu ích để kiểm tra ranh giới transaction là dùng database test và writer thực hiện nhiều thao tác ghi trong cùng chunk, sau đó cố ý ném exception ở giữa. Kết quả mong đợi: các thao tác thuộc chunk thất bại bị rollback, còn chunk trước đã commit vẫn còn dữ liệu.

Ví dụ writer giả lập lỗi sau khi ghi:

```java
public class FailingDatabaseWriter implements ItemWriter<OrderEntity> {

    private final JdbcTemplate jdbcTemplate;
    private int calls;

    public FailingDatabaseWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends OrderEntity> chunk) {
        calls++;
        for (OrderEntity order : chunk) {
            jdbcTemplate.update(
                "insert into imported_order(order_id, amount) values (?, ?)",
                order.getId(),
                order.getAmount()
            );
        }

        if (calls == 2) {
            throw new IllegalStateException("Simulated failure after write");
        }
    }
}
```

Với commit interval bằng 2 và bốn item, chunk đầu ghi hai hàng và commit. Chunk thứ hai ghi hai hàng rồi ném exception; nếu `JdbcTemplate` dùng cùng datasource và transaction manager với step, hai hàng của chunk thứ hai sẽ rollback. Sau job thất bại, test có thể xác nhận database chỉ còn hai hàng của chunk đầu.

Để test phản ánh transaction thật:

- Dùng database test và schema phù hợp.
- Đảm bảo `JdbcTemplate` và step dùng cùng `DataSource`/transaction manager.
- Không bọc test method bằng một transaction bên ngoài khiến dữ liệu đã commit của step bị rollback khi test kết thúc.
- Xác nhận trạng thái `JobExecution`/`StepExecution` và số hàng thực tế trong database.
- Dùng tham số identifying riêng để test không xung đột với execution trước.

Một unit test chỉ mock repository không chứng minh rollback database. Cần integration test với resource thực sự tham gia transaction.

## 15. Những lỗi thường gặp khi thiết kế transaction boundary

**Cho rằng cả job là một transaction:** chunk step commit từng nhóm riêng. Lỗi ở chunk sau không hoàn tác chunk trước.

**Dùng nhầm transaction manager:** writer có thể ghi vào datasource không được transaction của step quản lý. Xác nhận đúng datasource, manager và repository.

**Gọi API trong processor rồi kỳ vọng rollback:** HTTP call không tự tham gia transaction database. Tách thành outbox hoặc dùng idempotency.

**Dùng `REQUIRES_NEW` mà không hiểu hệ quả:** transaction con có thể commit độc lập và sống sót sau rollback của chunk.

**Chọn commit interval quá lớn:** transaction dài có thể giữ lock, connection và bộ nhớ lâu, đồng thời làm phạm vi rollback lớn hơn.

**Chọn commit interval quá nhỏ:** số lần commit và cập nhật metadata tăng, làm giảm throughput ở một số workload.

**Bỏ qua checkpoint:** rollback database không tự khôi phục cursor, file pointer hoặc offset của nguồn ngoài. Reader cần hỗ trợ restart.

**Gửi message trong listener:** callback không tạo transaction nguyên tử với broker và database. Dùng outbox hoặc cơ chế phối hợp tương ứng.

**Không kiểm tra rollback thực tế:** mock không thể chứng minh database đã hoàn tác. Dùng integration test với cùng transaction manager.

## 16. Cách lựa chọn transaction boundary trong production

Khi thiết kế chunk step, hãy xác định trước tài nguyên nào phải commit cùng nhau. Chọn transaction manager tương ứng với database hoặc resource chính; bảo đảm writer và repository cần tham gia transaction được cấu hình nhất quán. Nếu dữ liệu nghiệp vụ và metadata ở các resource khác nhau, đánh giá rõ khả năng commit độc lập và phương án phục hồi.

Chọn commit interval dựa trên throughput, lock duration, connection usage, kích thước dữ liệu và chi phí restart. Cấu hình isolation level, timeout và rollback rule theo yêu cầu thực tế. Với reader không transactional, lưu checkpoint qua `ExecutionContext` và bảo đảm nguồn có thể tiếp tục từ vị trí đã commit.

Cuối cùng, kiểm thử các tình huống writer thất bại giữa chunk, retry, restart và side effect đã xảy ra ở hệ thống ngoài. Với email, message hoặc API cần phát sau commit, dùng outbox và idempotency để xử lý delivery lặp an toàn.

Transaction boundary của chunk step xác định một nhóm item được commit hoặc rollback cùng nhau. Khi hiểu rõ phạm vi của transaction manager, cách chunk rollback, checkpoint và các tài nguyên nằm ngoài transaction, ứng dụng Spring Batch có thể kiểm soát dữ liệu nhất quán hơn và phục hồi đúng từ những lỗi xảy ra giữa quá trình xử lý.
