# Transaction propagation trong service được gọi

Trong Spring Batch, một step thường gọi các service Spring để đọc, kiểm tra hoặc cập nhật dữ liệu nghiệp vụ. Khi service có `@Transactional`, propagation quyết định service tham gia transaction đang tồn tại như thế nào: dùng chung transaction của step, mở transaction độc lập, tạo savepoint hay chạy mà không có transaction.

Đây là quyết định quan trọng vì chunk-oriented step đã có transaction boundary do Spring Batch quản lý. Nếu service dùng cùng transaction manager với step và propagation mặc định `REQUIRED`, thao tác của service thường tham gia transaction của chunk. Nếu service dùng `REQUIRES_NEW`, phần việc bên trong có thể commit độc lập dù chunk bên ngoài rollback.

## 1. Transaction propagation là gì?

Propagation là thuộc tính của một lời gọi phương thức transactional, mô tả cách lời gọi đó tương tác với transaction hiện có. Trong Spring, propagation thường được cấu hình bằng `@Transactional(propagation = ...)`.

Ví dụ một service được gọi từ processor hoặc writer:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void updateOrder(Order order) {
        orderRepository.save(order);
    }
}
```

Mặc định, `@Transactional` dùng `Propagation.REQUIRED`. Nếu lời gọi đến `updateOrder` diễn ra trong transaction của chunk và dùng cùng transaction manager, service tham gia transaction đó. Nếu được gọi ngoài transaction, Spring mở transaction mới cho phương thức.

Propagation không tự xác định ai được phép gọi service, cũng không thay thế việc chọn transaction manager, rollback rule hoặc thiết kế idempotency. Nó chỉ quy định cách một lời gọi transactional tham gia vào ranh giới transaction.

## 2. Transaction của chunk và lời gọi service

Trong chunk-oriented step, Spring Batch quản lý transaction cho mỗi chunk. Reader đọc item, processor xử lý item và writer ghi nhóm item trong phạm vi transaction của chunk theo cấu hình step.

```text
Chunk transaction bắt đầu
       |
       v
ItemReader.read()
       |
       v
ItemProcessor.process()
       |
       +----> OrderService.updateOrder()
       |          Propagation.REQUIRED
       |          tham gia transaction hiện tại
       |
       v
ItemWriter.write(chunk)
       |
       v
Chunk transaction commit
```

Nếu service dùng cùng transaction manager với step, thao tác database trong service có thể commit cùng chunk. Nếu processor hoặc writer ném exception khiến chunk rollback, thay đổi của service trong cùng transaction cũng được rollback.

Ví dụ khai báo step trong Spring Batch 5:

```java
@Bean
Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrders", jobRepository)
        .<OrderRow, Order>chunk(100, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Trong ví dụ này, service được gọi từ processor hoặc writer cần dùng cùng `businessTransactionManager` nếu muốn tham gia transaction chunk. Chỉ đặt `@Transactional` trên service chưa đủ để bảo đảm nó tham gia đúng transaction; transaction manager và datasource phải tương ứng.

## 3. Các kiểu propagation trong Spring

Six propagation mode thường gặp mô tả cách xử lý khi đã có transaction và khi chưa có transaction:

| Propagation | Nếu đã có transaction | Nếu chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại | Tạo transaction mới |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại, tạo transaction mới | Tạo transaction mới |
| `NESTED` | Tạo nested scope, thường dựa trên savepoint nếu transaction manager hỗ trợ | Tạo transaction mới |
| `SUPPORTS` | Tham gia transaction hiện tại | Chạy không có transaction mới |
| `NOT_SUPPORTED` | Tạm treo transaction hiện tại và chạy không transaction | Chạy không transaction |
| `MANDATORY` | Bắt buộc tham gia transaction hiện tại | Ném exception vì không có transaction |
| `NEVER` | Ném exception nếu đang có transaction | Chạy không transaction |

Với phần lớn service nghiệp vụ được gọi từ step, `REQUIRED` là lựa chọn mặc định hợp lý. Các mode còn lại cần được chọn theo ranh giới commit/rollback mà nghiệp vụ thực sự yêu cầu.

## 4. REQUIRED: tham gia transaction hiện tại

`Propagation.REQUIRED` là mặc định của `@Transactional`. Nếu caller đã có transaction, service tham gia transaction đó. Nếu chưa có, Spring tạo transaction mới cho lời gọi service.

```java
@Service
public class InventoryService {

    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve(Order order) {
        // Cập nhật tồn kho trong transaction hiện tại
    }
}
```

Khi `reserve` được gọi trong chunk transaction dùng cùng transaction manager, thay đổi tồn kho thuộc transaction chunk. Nếu writer sau đó thất bại và chunk rollback, cập nhật tồn kho cũng rollback.

`REQUIRED` phù hợp khi các thao tác của service là một phần của cùng đơn vị công việc với chunk: cập nhật trạng thái, ghi dữ liệu đích hoặc lưu quan hệ nghiệp vụ. Nó giúp nhiều service cùng tham gia một transaction nhất quán.

## 5. REQUIRES_NEW: mở transaction độc lập

`Propagation.REQUIRES_NEW` luôn yêu cầu một transaction độc lập. Nếu caller đang có transaction, Spring tạm treo transaction bên ngoài, mở transaction mới cho service và tiếp tục transaction bên ngoài sau khi transaction mới hoàn tất.

```java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String orderId, String message) {
        // Ghi audit trong transaction độc lập
    }
}
```

Ví dụ, processor gọi `recordAttempt` trong lúc xử lý một chunk. Nếu audit transaction commit thành công, bản ghi audit có thể vẫn tồn tại ngay cả khi transaction chunk sau đó rollback.

```text
Transaction chunk bắt đầu
       |
       v
Gọi AuditService.recordAttempt()
       |
       +-- treo transaction chunk
       |
       +-- bắt đầu transaction audit mới
       |       ghi audit
       |       commit transaction audit
       |
       +-- tiếp tục transaction chunk
       |
       v
Chunk gặp lỗi -> rollback transaction chunk

Kết quả: audit đã commit vẫn còn
```

Đây là hành vi hữu ích khi cần lưu một số thông tin độc lập với transaction nghiệp vụ, nhưng cũng tạo rủi ro nếu dùng sai. Ví dụ, ghi “đơn hàng đã xử lý thành công” bằng `REQUIRES_NEW` trước khi chunk commit có thể để lại audit thành công dù dữ liệu nghiệp vụ đã rollback.

Không nên dùng `REQUIRES_NEW` cho mọi lời gọi service trong processor hoặc writer. Mỗi transaction độc lập có thể tăng số lần commit, làm giảm hiệu năng và tiêu thụ thêm connection. Khi transaction bên ngoài vẫn giữ connection, transaction mới có thể cần một connection khác; pool quá nhỏ có thể gây chờ hoặc deadlock tài nguyên.

## 6. NESTED: transaction lồng nhau bằng savepoint

`Propagation.NESTED` cho phép service chạy trong một nested transaction scope bên trong transaction hiện tại, thường được triển khai bằng savepoint của JDBC.

```java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalDetails(Order order) {
    // Các thay đổi có thể rollback về savepoint
}
```

Giả sử chunk transaction đang hoạt động. Khi gọi service `NESTED`, transaction manager tạo savepoint. Nếu phần nested thất bại và exception được xử lý tại caller, transaction có thể rollback về savepoint trong khi phần việc trước savepoint vẫn tiếp tục. Nếu transaction bên ngoài rollback, mọi thay đổi trong nested scope cũng rollback.

`NESTED` không giống `REQUIRES_NEW`: nested scope không commit độc lập với transaction ngoài. Nó thường chỉ cung cấp khả năng rollback một phần về savepoint.

Khả năng nested transaction phụ thuộc transaction manager và tài nguyên. `DataSourceTransactionManager`/`JdbcTransactionManager` có thể hỗ trợ savepoint khi driver/database hỗ trợ; không phải mọi transaction manager, đặc biệt các cấu hình JPA, đều hỗ trợ nested transaction theo cách này. Hãy kiểm tra transaction manager thực tế trước khi dùng.

## 7. SUPPORTS và NOT_SUPPORTED

`SUPPORTS` tham gia transaction hiện tại nếu có. Nếu caller không có transaction, phương thức chạy mà không tạo transaction mới.

```java
@Transactional(propagation = Propagation.SUPPORTS)
public OrderSummary loadSummary(String orderId) {
    return summaryRepository.findSummary(orderId);
}
```

Mode này có thể phù hợp với thao tác đọc có thể chạy trong hoặc ngoài transaction. Tuy nhiên, nếu cần một snapshot nhất quán hoặc yêu cầu transaction rõ ràng, hãy cân nhắc `REQUIRED` thay vì dựa vào caller.

`NOT_SUPPORTED` tạm treo transaction hiện tại và chạy phương thức không có transaction. Nó có thể dùng cho thao tác không nên giữ transaction mở, nhưng nếu phương thức ghi dữ liệu, các thao tác đó không được bảo vệ bởi transaction của caller và có thể không được rollback cùng chunk.

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void callLongRunningExternalService() {
    // Không tham gia transaction đang có
}
```

Không nên dùng `NOT_SUPPORTED` chỉ để né lock hoặc lỗi transaction mà chưa đánh giá tính nhất quán. Khi chunk rollback, thao tác đã thực hiện ngoài transaction có thể vẫn tồn tại.

## 8. MANDATORY và NEVER

`MANDATORY` yêu cầu caller phải có transaction từ trước. Nếu không có transaction, Spring ném `IllegalTransactionStateException`. Nó hữu ích khi service chỉ được phép chạy như một phần của đơn vị công việc do caller quản lý.

```java
@Transactional(propagation = Propagation.MANDATORY)
public void persistWithinBatchTransaction(Order order) {
    orderRepository.save(order);
}
```

Với cách này, gọi service từ một controller hoặc scheduler không có transaction sẽ thất bại, giúp phát hiện việc gọi sai ngữ cảnh.

`NEVER` làm ngược lại: yêu cầu không có transaction. Nếu caller đang có transaction, Spring ném `IllegalTransactionStateException`. Mode này hiếm dùng trong xử lý nghiệp vụ batch vì các thao tác ghi thường cần transaction, nhưng có thể hữu ích cho một API phải được gọi ngoài transaction theo thiết kế.

## 9. Chọn propagation cho service trong batch

Việc chọn mode nên dựa trên ý nghĩa của thao tác và yêu cầu rollback:

| Công việc trong service | Propagation thường phù hợp | Lý do |
|---|---|---|
| Cập nhật dữ liệu nghiệp vụ thuộc chunk hiện tại | `REQUIRED` | Cùng commit/rollback với chunk |
| Ghi audit cần tồn tại độc lập với rollback nghiệp vụ | Có thể dùng `REQUIRES_NEW` | Transaction audit commit riêng; cần xác định rõ ý nghĩa audit |
| Một phần cập nhật có thể rollback về savepoint nhưng giữ phần ngoài | `NESTED` nếu được hỗ trợ | Cho phép rollback cục bộ trong transaction ngoài |
| Đọc dữ liệu có thể tham gia transaction nếu caller có | `SUPPORTS` | Không tự tạo transaction khi chạy độc lập |
| Gọi thao tác ngoài transaction hiện tại | `NOT_SUPPORTED` | Tạm treo transaction caller |
| Service bắt buộc chỉ được gọi trong chunk/service transaction | `MANDATORY` | Phát hiện caller thiếu transaction |

Đừng chọn propagation chỉ dựa trên tên phương thức hoặc mong muốn “tăng độ an toàn”. Hãy viết rõ thao tác nào phải commit cùng chunk, thao tác nào được phép tồn tại độc lập và điều gì xảy ra khi chunk rollback.

## 10. Cùng transaction manager mới có thể tham gia cùng transaction

Propagation được áp dụng trong phạm vi transaction manager mà phương thức transactional sử dụng. Trong một ứng dụng có nhiều datasource, step có thể dùng `businessTransactionManager` trong khi service lại chọn `batchTransactionManager` hoặc một manager khác.

```java
@Transactional(
    transactionManager = "businessTransactionManager",
    propagation = Propagation.REQUIRED
)
public void updateOrder(Order order) {
    orderRepository.save(order);
}
```

Để service tham gia transaction của chunk, cần bảo đảm:

- Step dùng đúng transaction manager cho dữ liệu nghiệp vụ.
- Service chọn cùng transaction manager đó (hoặc cùng transaction resource theo cấu hình tương ứng).
- Repository/JdbcTemplate của service sử dụng datasource được manager quản lý.
- Lời gọi diễn ra trên cùng thread và qua proxy transactional của Spring.

Nếu metadata của Spring Batch nằm ở database riêng, transaction manager cho JobRepository có thể khác transaction manager của chunk. Hai transaction manager cục bộ không tự tạo thành một transaction nguyên tử xuyên hai database. Có thể xảy ra trường hợp dữ liệu nghiệp vụ commit nhưng metadata chưa commit, hoặc ngược lại; cần thiết kế idempotency và đối soát phù hợp.

## 11. @Transactional hoạt động qua Spring proxy

Trong cấu hình proxy mặc định, Spring áp dụng `@Transactional` khi phương thức được gọi qua proxy của bean Spring. Nếu một method trong cùng object gọi trực tiếp một method khác có `@Transactional`, lời gọi nội bộ (self-invocation) thường không đi qua proxy và propagation được khai báo trên method được gọi có thể không được áp dụng.

Ví dụ dễ gây hiểu nhầm:

```java
@Service
public class OrderService {

    public void process(Order order) {
        saveAudit(order); // Gọi nội bộ cùng object
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // Có thể không mở REQUIRES_NEW do self-invocation
    }
}
```

Trong ví dụ này, `saveAudit` được gọi trực tiếp từ `process` trên cùng instance. Với proxy mode thông thường, annotation trên `saveAudit` không được interceptor áp dụng cho lời gọi nội bộ đó.

Cách rõ ràng hơn là tách phần cần propagation riêng thành bean khác:

```java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // Ghi audit độc lập
    }
}

@Service
public class OrderService {

    private final AuditService auditService;

    public OrderService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void process(Order order) {
        auditService.saveAudit(order); // Qua Spring proxy
    }
}
```

Gọi qua bean Spring khác giúp lời gọi đi qua proxy. Khi dùng `@Transactional`, hãy kiểm tra method được gọi là method có thể được proxy/intercept trong cấu hình đang dùng và bean được quản lý bởi Spring.

## 12. Rollback rule và propagation là hai cấu hình khác nhau

Propagation quyết định transaction được tham gia hoặc tạo mới như thế nào. Rollback rule quyết định loại exception nào khiến transaction rollback. Hai khái niệm này độc lập.

Mặc định, Spring đánh dấu transaction rollback khi phương thức transactional ném `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo mặc định. Có thể khai báo `rollbackFor` nếu cần rollback với checked exception:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = IOException.class
)
public void importFile(Path path) throws IOException {
    // Đọc và cập nhật dữ liệu
}
```

Trong Spring Batch, step cũng có cơ chế xử lý exception, skip và retry. Việc một exception được skip không đồng nghĩa mọi thay đổi trong transaction tự động được giữ lại; framework có thể rollback chunk để recovery rồi xử lý lại các item theo chính sách. Hãy kiểm tra cả rollback rule của service và fault-tolerance policy của step.

## 13. Ảnh hưởng của REQUIRES_NEW đến connection pool

Khi transaction bên ngoài bị tạm treo, connection của nó có thể vẫn được giữ trong lúc transaction `REQUIRES_NEW` cần một connection khác. Nếu nhiều worker cùng giữ transaction ngoài rồi chờ transaction mới lấy connection, pool quá nhỏ có thể gây cạn connection hoặc chờ kéo dài.

Ví dụ, nếu có 10 thread xử lý chunk và mỗi thread giữ một connection ngoài, sau đó mỗi thread gọi service `REQUIRES_NEW`, pool chỉ có 10 connection có thể không còn connection trống cho các transaction mới.

Khi dùng `REQUIRES_NEW` trong luồng batch song song, cần đánh giá kích thước pool, số worker đồng thời, thời gian giữ connection và số lần gọi service độc lập. Giảm số lần gọi độc lập, gom audit theo chunk hoặc dùng outbox có thể phù hợp hơn.

## 14. Transaction propagation không tự truyền qua thread

Transaction context trong Spring thường gắn với thread. Nếu service tạo tác vụ bằng `@Async`, executor hoặc gửi công việc sang thread khác, transaction hiện tại của chunk không tự động được truyền sang thread mới.

```text
Thread xử lý chunk
   transaction A
       |
       +---- gọi executor.submit(...)
                     |
                     v
              Worker thread mới
              không có transaction A
              có thể mở transaction riêng
```

Worker thread cần transaction manager và ranh giới transaction riêng nếu nó ghi dữ liệu. Nếu tác vụ bất đồng bộ phải chỉ bắt đầu sau khi chunk commit, hãy dùng cơ chế phát sự kiện sau commit, outbox hoặc queue. Không giả định lời gọi service trên thread khác vẫn tham gia transaction chunk.

Với partitioning hoặc multi-threaded step, mỗi worker thread có thể có transaction riêng cho chunk của nó. Hãy thiết kế propagation dựa trên transaction của thread thực thi hiện tại, không dựa trên transaction của thread điều phối.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `REQUIRES_NEW` cho mọi thao tác ghi | Tách commit khỏi chunk, tăng connection và overhead | Dùng `REQUIRED` cho dữ liệu cần commit cùng chunk |
| Dùng transaction manager khác với step | Service không tham gia transaction chunk như mong đợi | Chỉ rõ `transactionManager` đúng cho step và service |
| Gọi method transactional bằng self-invocation | Propagation trên method được gọi có thể không có hiệu lực | Tách method sang bean khác hoặc gọi qua proxy |
| Dùng `NESTED` khi manager không hỗ trợ savepoint | Lỗi runtime hoặc không có rollback cục bộ như kỳ vọng | Xác nhận hỗ trợ của transaction manager/driver |
| Cho rằng `REQUIRES_NEW` rollback cùng chunk | Dữ liệu trong transaction mới có thể đã commit độc lập | Thiết kế audit và side effect theo semantics độc lập |
| Cho rằng transaction truyền qua `@Async` | Worker thread chạy ngoài transaction caller | Tạo transaction riêng hoặc phát tác vụ sau commit |
| Nhầm propagation với rollback rule | Checked exception có thể không rollback như mong muốn | Cấu hình `rollbackFor`/`noRollbackFor` phù hợp |
| Tách metadata và business database nhưng kỳ vọng atomic commit | Hai database có thể ở trạng thái lệch nhau | Dùng idempotency, outbox hoặc giải pháp transaction phân tán được thiết kế |

## 16. Quy trình chọn propagation cho một service

Khi một service được gọi từ processor, writer hoặc tasklet, hãy trả lời các câu hỏi sau:

1. Service có cần commit cùng chunk/tasklet hiện tại không? Nếu có, thường dùng `REQUIRED` và cùng transaction manager.
2. Phần việc có cần tồn tại ngay cả khi transaction bên ngoài rollback không? Nếu có, cân nhắc `REQUIRES_NEW` và ghi rõ ý nghĩa của dữ liệu độc lập.
3. Chỉ cần rollback một phần nhưng giữ transaction ngoài? Cân nhắc `NESTED` nếu transaction manager hỗ trợ savepoint.
4. Service có thể chạy cả trong và ngoài transaction không? Cân nhắc `SUPPORTS`.
5. Service có bắt buộc chạy ngoài transaction? Cân nhắc `NOT_SUPPORTED` hoặc `NEVER` tùy có muốn từ chối caller đang có transaction hay không.
6. Service có bắt buộc caller cung cấp transaction không? Dùng `MANDATORY` để phát hiện gọi sai ngữ cảnh.
7. Lời gọi có đi qua proxy Spring, cùng thread, cùng transaction manager và cùng datasource không?
8. Exception nào làm rollback, và step sẽ retry/skip hay dừng khi exception đó xảy ra?

## Kết luận

Transaction propagation điều khiển cách service tham gia transaction đang tồn tại. Trong chunk-oriented step, `REQUIRED` thường là lựa chọn phù hợp cho cập nhật nghiệp vụ cần commit hoặc rollback cùng chunk, miễn là service dùng cùng transaction manager và transaction resource với step.

`REQUIRES_NEW` tạo transaction độc lập, `NESTED` dùng savepoint khi được hỗ trợ, còn các mode khác kiểm soát việc tham gia hoặc tránh transaction. Hãy tính đến Spring proxy, self-invocation, rollback rule, connection pool và ranh giới thread/datasource trước khi chọn propagation. Điều quan trọng là mỗi thao tác phải có hành vi commit/rollback đúng với ý nghĩa nghiệp vụ của nó.
