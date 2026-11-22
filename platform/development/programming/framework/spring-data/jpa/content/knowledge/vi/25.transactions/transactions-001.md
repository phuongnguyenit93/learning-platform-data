# Ranh giới giao dịch theo một thao tác nghiệp vụ

Trong Spring Data JPA, ranh giới giao dịch nên bao quanh một thao tác nghiệp vụ cần được thực hiện nhất quán. Một thao tác như đặt hàng có thể đọc khách hàng, kiểm tra tồn kho, cập nhật sản phẩm, lưu đơn hàng, ghi nhận biến động kho và tạo sự kiện outbox. Nếu các thay đổi đó thuộc cùng một database transaction, chúng cùng commit khi thành công hoặc cùng rollback khi có lỗi phù hợp.

Vì vậy, ranh giới giao dịch thường được đặt ở tầng Service/Application Service, nơi điều phối toàn bộ use case. Repository chịu trách nhiệm truy cập dữ liệu; service quyết định những thao tác nào phải cùng thành công hoặc cùng thất bại.

## 1. Ranh giới giao dịch là gì?

Transaction là một đơn vị công việc mà database xử lý theo các thuộc tính ACID:

- **Atomicity:** các thay đổi trong transaction được commit cùng nhau hoặc rollback cùng nhau.
- **Consistency:** transaction phải giữ các ràng buộc và quy tắc nhất quán của dữ liệu.
- **Isolation:** các transaction đồng thời được cô lập theo mức isolation của database.
- **Durability:** sau khi commit thành công, dữ liệu được lưu bền vững theo cam kết của database.

Ranh giới giao dịch xác định thời điểm transaction bắt đầu và kết thúc. Với Spring, **@Transactional** thường được dùng để khai báo ranh giới đó.

Một transaction nghiệp vụ không nhất thiết tương ứng với một câu SQL hoặc một lần gọi Repository. Một use case có thể gọi nhiều Repository và phát sinh nhiều câu SQL nhưng vẫn nằm trong cùng một transaction.

Ví dụ đặt hàng:

~~~text
Place order (một thao tác nghiệp vụ)
        |
        v
BEGIN TRANSACTION
        |
        +--> Đọc khách hàng
        |
        +--> Đọc và cập nhật tồn kho
        |
        +--> Lưu đơn hàng
        |
        +--> Ghi biến động kho
        |
        +--> Ghi sự kiện outbox
        |
        v
COMMIT
~~~

Nếu một bước quan trọng thất bại và lỗi làm transaction rollback, các thay đổi database trong transaction đó sẽ không được commit riêng lẻ.

## 2. Vì sao nên đặt transaction ở tầng Service?

Service biết một thao tác nghiệp vụ cần làm những gì. Repository chỉ biết cách đọc hoặc ghi một loại dữ liệu.

Giả sử đặt hàng cần ba thao tác:

~~~java
productRepository.updateStock(productId, quantity);
orderRepository.save(order);
inventoryMovementRepository.save(movement);
~~~

Nếu mỗi thao tác tự chạy trong transaction độc lập, có thể xảy ra tình huống:
1. Tồn kho đã giảm và transaction thứ nhất commit.
2. Lưu đơn hàng thất bại.
3. Hệ thống còn dữ liệu tồn kho đã giảm nhưng không có đơn hàng tương ứng.

Đặt **@Transactional** ở service giúp cả ba thao tác tham gia cùng một transaction:

~~~java
@Service
public class OrderApplicationService {

    private final ProductRepository productRepository;
    private final OrderRepository orderRepository;
    private final InventoryMovementRepository movementRepository;

    public OrderApplicationService(
            ProductRepository productRepository,
            OrderRepository orderRepository,
            InventoryMovementRepository movementRepository) {
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.movementRepository = movementRepository;
    }

    @Transactional
    public Long placeOrder(CreateOrderCommand command) {
        Product product = productRepository.findById(command.productId())
                .orElseThrow(() ->
                        new ProductNotFoundException(command.productId()));

        product.decreaseStock(command.quantity());

        PurchaseOrder order = PurchaseOrder.create(
                command.customerId(),
                product,
                command.quantity()
        );

        PurchaseOrder saved = orderRepository.save(order);

        movementRepository.save(
                InventoryMovement.forOrder(
                        product.getId(),
                        saved.getId(),
                        command.quantity()
                )
        );

        return saved.getId();
    }
}
~~~

Đây là đoạn service minh họa; các Entity, command, Repository và factory method cần được định nghĩa theo mô hình của ứng dụng. Điều quan trọng là phương thức placeOrder() là điểm điều phối và bao quanh toàn bộ thay đổi cần nguyên tử.

Khi placeOrder() được gọi qua Spring transaction proxy, transaction được mở trước khi phần thân phương thức chạy. Các Repository dùng cùng transaction manager và cùng persistence resource sẽ tham gia transaction hiện tại. Khi phương thức kết thúc bình thường, Spring yêu cầu commit; khi lỗi phù hợp thoát khỏi phương thức, Spring yêu cầu rollback.

## 3. Một transaction có thể bao gồm nhiều Repository

Không cần tạo một transaction cho mỗi Repository. Các thao tác trên nhiều Repository có thể tham gia cùng một transaction nếu chúng dùng cùng transaction manager và cùng resource transaction được quản lý.

Ví dụ:

~~~java
@Transactional
public void approveInvoice(Long invoiceId) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
            .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));

    invoice.approve();

    accountRepository.increaseReceivable(
            invoice.getCustomerId(),
            invoice.getTotalAmount()
    );

    auditRepository.save(
            AuditRecord.invoiceApproved(invoiceId)
    );
}
~~~

Nếu các Repository cùng dùng một **PlatformTransactionManager** cho cùng database, thao tác cập nhật Invoice, Account và AuditRecord có thể commit hoặc rollback cùng nhau.

Cần phân biệt điều này với trường hợp ứng dụng có nhiều database hoặc nhiều transaction manager. Một **@Transactional** thông thường gắn với một transaction manager cụ thể; nó không tự biến nhiều database độc lập thành một transaction phân tán.

## 4. Transaction bắt đầu và kết thúc khi nào?

Với transaction được quản lý bởi Spring proxy, luồng điển hình là:

1. Caller gọi phương thức service qua proxy.
2. Proxy đọc metadata **@Transactional**.
3. Transaction manager bắt đầu transaction mới hoặc tham gia transaction hiện tại theo propagation.
4. Phần thân phương thức service chạy.
5. Các Repository/JPA operation tham gia transaction hiện tại.
6. Nếu phương thức trả về bình thường, proxy thực hiện commit.
7. Nếu exception thoát ra và khớp rollback rule, proxy thực hiện rollback.
8. Kết quả hoặc exception được trả về caller.

Transaction kết thúc ở ranh giới proxy, không nhất thiết ngay khi lệnh save() được gọi.

Ví dụ:

~~~java
@Transactional
public Long createProduct(String name) {
    Product product = productRepository.save(new Product(name));
    return product.getId();
}
~~~

save() không đồng nghĩa với commit. Hibernate có thể trì hoãn việc gửi SQL xuống database cho đến flush hoặc commit. Khi transaction commit, các thay đổi đang chờ được đồng bộ với database.

saveAndFlush() yêu cầu flush persistence context ngay tại thời điểm gọi, nhưng **flush không phải commit**. Transaction vẫn có thể rollback sau đó.

## 5. Atomicity của một thao tác nghiệp vụ

Hãy xác định các thay đổi nào tạo thành một invariant nghiệp vụ.

Ví dụ khi đặt hàng, invariant có thể là:
- Đơn hàng được tạo.
- Tồn kho được giảm tương ứng.
- Biến động kho được ghi nhận.
- Sự kiện cần phát ra được lưu vào outbox.

Nếu ứng dụng lưu đơn hàng nhưng không giảm tồn kho, dữ liệu không còn phản ánh đúng nghiệp vụ. Nếu giảm tồn kho nhưng không có đơn hàng, hệ thống cũng sai.

Đưa các thay đổi database này vào cùng transaction giúp bảo đảm tính nguyên tử:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    Product product = productRepository.findById(command.productId())
            .orElseThrow();

    product.reserve(command.quantity());

    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.create(command, product)
    );

    inventoryMovementRepository.save(
            InventoryMovement.forOrder(order, product, command.quantity())
    );

    outboxRepository.save(
            OutboxEvent.orderPlaced(order.getId())
    );

    return order.getId();
}
~~~

Nếu việc lưu InventoryMovement thất bại và exception làm rollback, việc cập nhật tồn kho, lưu Order và lưu OutboxEvent trong cùng transaction cũng bị rollback.

Đừng chia nhỏ transaction chỉ theo số lượng Repository. Hãy chia theo ranh giới nhất quán của nghiệp vụ.

## 6. Rollback mặc định với exception

Theo quy tắc mặc định phổ biến của Spring, transaction rollback khi một **RuntimeException** hoặc **Error** thoát khỏi phương thức được quản lý. Checked exception không tự động làm rollback theo quy tắc mặc định.

Ví dụ unchecked exception:

~~~java
@Transactional
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }
}
~~~

IllegalArgumentException là RuntimeException, nên nếu thoát khỏi phương thức, transaction được rollback. Trong code thực tế, nên validate amount trước khi thực hiện thay đổi để tránh công việc không cần thiết.

Với checked exception:

~~~java
@Transactional
public void importStatement() throws IOException {
    accountRepository.updateBalance(...);
    throw new IOException("Cannot read statement");
}
~~~

Theo rollback rule mặc định, checked IOException không nhất thiết làm transaction rollback. Nếu muốn rollback khi lỗi đó xảy ra, khai báo:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importStatement() throws IOException {
    accountRepository.updateBalance(...);
    throw new IOException("Cannot read statement");
}
~~~

Có thể dùng noRollbackFor để khai báo một loại exception không làm rollback, nhưng cần thận trọng vì điều đó có thể khiến một phần thao tác nghiệp vụ được commit dù caller nhận lỗi.

Quy tắc rollback có thể được cấu hình ở cấp ứng dụng trong các phiên bản Spring mới; hãy kiểm tra cấu hình transaction của dự án. Khi không có cấu hình đặc biệt, hãy dựa trên quy tắc mặc định RuntimeException/Error và khai báo rollbackFor cho checked exception cần rollback.

## 7. Bắt exception bên trong transaction

Nếu exception được bắt rồi không ném lại, proxy có thể thấy phương thức kết thúc bình thường và thực hiện commit.

Ví dụ dễ gây lỗi:

~~~java
@Transactional
public void processOrder(Long orderId) {
    try {
        orderRepository.markProcessing(orderId);
        paymentRecordRepository.createRecord(orderId);
    } catch (DataAccessException exception) {
        log.error("Could not process order", exception);
        // Không ném lại và không đánh dấu rollback-only.
    }
}
~~~

Nếu exception không làm transaction bị đánh dấu rollback-only bởi provider hoặc transaction manager, các thay đổi trước đó có thể được commit. Điều này thường không đúng với ý định “thao tác thất bại thì không lưu gì”.

Nếu lỗi phải làm thao tác nghiệp vụ thất bại, hãy ném lại exception phù hợp:

~~~java
catch (DataAccessException exception) {
    throw new OrderProcessingException(
            "Could not process order",
            exception
    );
}
~~~

Nếu thực sự cần bắt lỗi và trả về kết quả bình thường, hãy quyết định rõ transaction có được phép commit hay không. Có thể đánh dấu rollback-only bằng API transaction khi cần, nhưng không nên dùng việc bắt rồi nuốt exception như một cách xử lý lỗi mặc định.

Một số lỗi database khiến transaction đã bị đánh dấu rollback-only. Khi code tiếp tục và cố commit, Spring có thể ném UnexpectedRollbackException để thông báo rằng transaction không thể commit như caller mong đợi.

## 8. Propagation: các transaction lồng nhau tham gia ra sao?

Propagation xác định hành vi khi một phương thức transactional được gọi trong lúc đã có transaction.

| Propagation | Hành vi |
|---|---|
| REQUIRED | Tham gia transaction hiện tại; nếu chưa có thì tạo mới |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và tạo transaction độc lập |
| SUPPORTS | Tham gia nếu có; nếu không thì chạy không có transaction |
| MANDATORY | Yêu cầu phải có transaction hiện tại; nếu không thì lỗi |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại và chạy không có transaction |
| NEVER | Yêu cầu không có transaction; nếu có thì lỗi |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ |

REQUIRED là propagation mặc định của **@Transactional**. Đây thường là lựa chọn phù hợp cho các service method cùng thực hiện một thao tác nghiệp vụ.

Ví dụ:

~~~java
@Service
public class InventoryService {

    @Transactional
    public void reserve(Long productId, int quantity) {
        // Đọc và cập nhật tồn kho.
    }
}

@Service
public class OrderService {

    private final InventoryService inventoryService;

    @Transactional
    public void placeOrder(...) {
        inventoryService.reserve(...);
        // Lưu đơn hàng và các thay đổi liên quan.
    }
}
~~~

Với REQUIRED, reserve() tham gia transaction do placeOrder() mở. Nếu bước lưu đơn hàng sau đó thất bại và rollback, thay đổi tồn kho cũng rollback trong cùng transaction.

## 9. Khi nào REQUIRES_NEW làm thay đổi ý nghĩa nghiệp vụ?

REQUIRES_NEW tạo transaction độc lập. Transaction bên ngoài bị tạm ngưng trong lúc transaction mới chạy; transaction bên trong có thể commit dù transaction ngoài sau đó rollback.

Ví dụ:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(Long orderId) {
        auditRepository.save(AuditRecord.attempted(orderId));
    }
}
~~~

Nếu OrderService gọi recordAttempt() rồi transaction đặt hàng thất bại, audit record vẫn có thể được commit vì nó thuộc transaction độc lập.

Điều này chỉ phù hợp nếu audit attempt thực sự cần tồn tại dù thao tác chính thất bại. Nếu audit record là một phần của dữ liệu cần nguyên tử với Order, hãy dùng REQUIRED mặc định.

REQUIRES_NEW có thể giữ connection của transaction ngoài trong khi transaction trong cần thêm connection. Dưới tải cao, điều này có thể làm tăng nhu cầu connection pool và nguy cơ cạn connection. Không dùng REQUIRES_NEW chỉ để “chắc chắn save được”.

## 10. NESTED không giống REQUIRES_NEW

NESTED thường được triển khai bằng savepoint trong cùng một transaction vật lý nếu transaction manager hỗ trợ. Nó cho phép rollback một phần công việc về savepoint trong khi transaction bên ngoài có thể tiếp tục.

Nó khác REQUIRES_NEW:
- NESTED dùng savepoint trong transaction hiện tại khi được hỗ trợ.
- REQUIRES_NEW tạo transaction độc lập có commit/rollback riêng.

Khả năng hỗ trợ NESTED phụ thuộc transaction manager và resource. Với JPA/Hibernate, không nên giả định mọi nested transaction được hỗ trợ như savepoint cho từng thao tác Entity. Chỉ dùng sau khi xác minh transaction manager và hành vi provider thực tế.

Trong đa số use case Spring Data JPA thông thường, REQUIRED là đủ.

## 11. Ranh giới giao dịch không nên đặt ở từng Repository method

Một cách tổ chức dễ gây phân mảnh là để từng Repository operation tự tạo transaction riêng, rồi service gọi nhiều operation liên tiếp mà không có transaction bao ngoài.

Ví dụ:

~~~java
public void placeOrder(...) {
    inventoryRepository.decreaseStock(...);
    orderRepository.save(...);
    movementRepository.save(...);
}
~~~

Nếu không có transaction bao ngoài, các phương thức repository có thể được thực thi trong các transaction riêng theo cấu hình mặc định của chúng. Khi bước cuối thất bại, các bước trước có thể đã commit.

Nên đặt transaction ở service:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.decreaseStock(...);
    orderRepository.save(...);
    movementRepository.save(...);
}
~~~

Các Repository cùng transaction manager sẽ tham gia transaction này. Transaction bao ngoài tạo một ranh giới nguyên tử có ý nghĩa nghiệp vụ.

Không có nghĩa mọi phương thức Repository phải bỏ **@Transactional**. Spring Data có transaction configuration riêng cho các phương thức CRUD kế thừa; transaction ở service bao ngoài sẽ điều phối các lần gọi đó thông qua propagation phù hợp. Điểm quan trọng là không dựa vào các transaction riêng của từng Repository để tạo tính nguyên tử cho cả use case.

## 12. Transaction đọc và readOnly

Với thao tác chỉ đọc, có thể dùng:

~~~java
@Transactional(readOnly = true)
public OrderDetails getOrder(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return OrderDetails.from(order);
}
~~~

readOnly = true là gợi ý cho transaction manager/provider và có thể giúp tối ưu một số hành vi như flush mode. Nó không phải cơ chế bảo mật bảo đảm không thể ghi database trong mọi cấu hình.

Với thao tác ghi, dùng transaction read-write mặc định:

~~~java
@Transactional
public void updateOrder(...) {
    // Thay đổi trạng thái và dữ liệu nghiệp vụ.
}
~~~

Khi service class được đánh dấu **@Transactional(readOnly = true)**, có thể ghi đè ở method cần ghi bằng **@Transactional** không đặt readOnly:

~~~java
@Service
@Transactional(readOnly = true)
public class OrderQueryService {

    public OrderDetails findDetails(Long id) {
        // Chỉ đọc.
    }
}

@Service
public class OrderCommandService {

    @Transactional
    public void cancel(Long id) {
        // Thay đổi dữ liệu.
    }
}
~~~

Tách query service và command service là một cách tổ chức, nhưng không bắt buộc. Điều quan trọng là transaction mode phản ánh đúng công việc.

## 13. Transaction proxy và self-invocation

Spring thường áp dụng **@Transactional** thông qua proxy. Lời gọi từ một bean khác đi qua proxy sẽ được interceptor mở hoặc tham gia transaction.

Một lỗi thường gặp là gọi một phương thức transactional khác bằng this trong cùng object:

~~~java
@Service
public class ImportService {

    public void importAll() {
        this.importOneBatch();
    }

    @Transactional
    public void importOneBatch() {
        // Người viết có thể kỳ vọng method này luôn mở transaction riêng.
    }
}
~~~

Lời gọi this.importOneBatch() không đi qua Spring proxy, nên annotation trên method được gọi nội bộ có thể không được áp dụng như mong đợi.

Cách tổ chức rõ ràng hơn là đưa ranh giới transaction vào một bean riêng:

~~~java
@Service
public class BatchWorker {

    @Transactional
    public void importOneBatch(List<ImportRow> rows) {
        // Xử lý một batch trong transaction.
    }
}

@Service
public class ImportCoordinator {

    private final BatchWorker batchWorker;

    public ImportCoordinator(BatchWorker batchWorker) {
        this.batchWorker = batchWorker;
    }

    public void importAll(List<List<ImportRow>> batches) {
        for (List<ImportRow> batch : batches) {
            batchWorker.importOneBatch(batch);
        }
    }
}
~~~

Mỗi lần gọi qua bean BatchWorker đi qua proxy và có thể tạo transaction riêng theo propagation. Đây là cách phù hợp khi muốn mỗi batch commit độc lập.

Với proxy mode thông thường, hãy đặt **@Transactional** trên method được gọi từ bên ngoài bean và tránh dựa vào self-invocation. Cũng cần kiểm tra loại proxy và visibility method theo phiên bản Spring/cấu hình dự án.

## 14. Không để transaction bao trùm các thao tác chờ lâu

Transaction giữ tài nguyên database như connection và có thể giữ lock. Nếu mở transaction rồi gọi dịch vụ HTTP chậm, gửi email hoặc chờ người dùng xác nhận, transaction có thể kéo dài không cần thiết.

Ví dụ không nên:

~~~java
@Transactional
public void placeOrder(...) {
    orderRepository.save(...);
    paymentGateway.charge(...); // Gọi mạng có thể mất nhiều giây.
    orderRepository.markPaid(...);
}
~~~

Vấn đề:
- Connection database có thể bị giữ trong lúc chờ network.
- Lock có thể tồn tại lâu.
- Nếu payment gateway thành công nhưng database rollback, hai hệ thống không đồng bộ.
- Database transaction không thể rollback một khoản thanh toán đã được hệ thống bên ngoài thực hiện.

Nên thiết kế quy trình nhiều bước có trạng thái và tính idempotent. Ví dụ:
1. Trong transaction database, tạo Order ở trạng thái PENDING và ghi outbox event.
2. Commit transaction.
3. Worker đọc outbox và gọi payment provider.
4. Sau kết quả, worker mở transaction mới để cập nhật trạng thái Order.
5. Nếu lỗi tạm thời, retry theo idempotency key và chính sách rõ ràng.

Đây là workflow bất đồng bộ/saga tùy nghiệp vụ, không phải một transaction ACID xuyên suốt database và payment provider.

## 15. Transactional outbox và sự kiện sau commit

Nếu cần phát sự kiện sau khi lưu dữ liệu, không nên tùy tiện publish message trước khi transaction database commit.

Tình huống lỗi:
- Ứng dụng publish OrderPlaced.
- Database commit thất bại.
- Consumer đã nhận sự kiện nhưng Order không tồn tại.

Hoặc ngược lại:
- Database commit thành công.
- Ứng dụng chết trước khi publish event.
- Hệ thống khác không bao giờ nhận được thông báo.

Transactional outbox xử lý bằng cách ghi dữ liệu nghiệp vụ và bản ghi sự kiện vào cùng database transaction:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orderRepository.save(
            PurchaseOrder.create(command)
    );

    outboxRepository.save(
            OutboxEvent.orderPlaced(order.getId())
    );

    return order.getId();
}
~~~

Sau commit, một worker riêng đọc outbox, gửi message và đánh dấu đã xử lý. Cần thiết kế retry, khóa/claim bản ghi, xử lý message trùng và idempotency ở consumer.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** cũng hữu ích khi muốn xử lý event chỉ sau khi transaction commit. Tuy nhiên, listener in-memory không tự bảo đảm event được giao bền vững nếu tiến trình dừng ngay sau commit; outbox phù hợp hơn khi không được phép mất sự kiện.

## 16. Lazy loading và phạm vi transaction

Entity có quan hệ LAZY thường chỉ tải dữ liệu liên quan khi thuộc tính được truy cập. Nếu service trả Entity ra ngoài và controller/serializer truy cập quan hệ sau khi transaction đã kết thúc, có thể gặp LazyInitializationException hoặc phát sinh truy vấn ngoài dự kiến.

Một cách rõ ràng là tải dữ liệu cần thiết và chuyển sang DTO bên trong service transaction:

~~~java
@Transactional(readOnly = true)
public OrderDetails getDetails(Long orderId) {
    PurchaseOrder order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return new OrderDetails(
            order.getId(),
            order.getCustomer().getName(),
            order.getItems().stream()
                    .map(item -> new OrderLineDetails(
                            item.getProduct().getName(),
                            item.getQuantity()
                    ))
                    .toList()
    );
}
~~~

Ví dụ cần mapping và fetch strategy phù hợp. Nếu nhiều quan hệ được truy cập, dùng fetch join, EntityGraph hoặc projection có chủ đích để tránh N+1.

Không kéo dài transaction chỉ để giữ Entity sống cho đến khi response được serialize. Hãy định nghĩa rõ dữ liệu cần trả và tải nó trong phạm vi service.

## 17. Isolation và đồng thời

Transaction boundary bảo đảm nhóm thay đổi thuộc cùng một transaction, nhưng không tự giải quyết mọi vấn đề cạnh tranh giữa nhiều transaction.

Ví dụ hai khách hàng cùng mua sản phẩm cuối cùng:
1. Transaction A đọc stock = 1.
2. Transaction B đọc stock = 1.
3. Cả hai cùng kiểm tra đủ hàng.
4. Cả hai cố giảm stock.

Nếu không có cơ chế đồng thời phù hợp, có thể bán vượt tồn kho.

Các lựa chọn:
- **Optimistic locking:** thêm **@Version**; khi hai transaction cùng sửa một Entity, một transaction có thể thất bại vì version đã thay đổi.
- **Pessimistic locking:** dùng lock database phù hợp khi cần khóa dòng trong thời gian transaction.
- **Atomic update:** dùng câu UPDATE có điều kiện như WHERE stock >= :quantity, rồi kiểm tra số dòng cập nhật.
- **Database constraint:** dùng ràng buộc để bảo vệ invariant ở tầng dữ liệu.

Isolation level mặc định phụ thuộc database và cấu hình. Chỉ tăng isolation khi yêu cầu nhất quán cần thiết và đã hiểu tác động đến lock, throughput và deadlock.

**@Transactional(isolation = Isolation.SERIALIZABLE)** không phải nút bật “an toàn tuyệt đối” miễn phí. Nó có thể làm giảm concurrency hoặc khiến transaction phải retry. Chọn cơ chế phù hợp với invariant cụ thể.

## 18. @Version và cập nhật đồng thời

Ví dụ Entity có optimistic locking:

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private int stock;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (stock < quantity) {
            throw new InsufficientStockException(id);
        }
        stock -= quantity;
    }
}
~~~

Khi Hibernate cập nhật Entity có **@Version**, câu UPDATE thường kiểm tra cả ID và version cũ, sau đó tăng version. Nếu một transaction khác đã cập nhật cùng dòng, số dòng được cập nhật có thể bằng 0 và provider báo lỗi optimistic locking.

Service cần để lỗi đó thoát khỏi transaction để rollback. Nếu muốn retry, chỉ retry những thao tác có thể thực hiện an toàn và phải đánh giá lại trạng thái tồn kho sau khi đọc mới.

## 19. Nhiều database và transaction manager

Một transaction Spring thông thường quản lý một transaction manager. Nếu hai Repository dùng hai datasource độc lập, đặt một **@Transactional** không mặc nhiên bảo đảm cả hai database commit hoặc rollback cùng nhau.

Các tình huống:

- Nhiều Repository cùng một datasource và transaction manager: thường có thể tham gia cùng transaction.
- Hai datasource với hai local transaction manager: mỗi datasource có transaction riêng; một bên commit thành công và bên kia thất bại có thể tạo trạng thái lệch.
- Cần atomicity phân tán: có thể xem xét JTA/XA nếu hạ tầng và database hỗ trợ, hoặc thiết kế saga/outbox và cơ chế bù trừ.

XA/distributed transaction tăng độ phức tạp vận hành và chi phí. Với kiến trúc microservice, thường ưu tiên workflow có trạng thái, outbox, retry và compensating action thay vì cố giữ một transaction database mở qua nhiều service.

## 20. Transaction trong tác vụ batch

Với batch lớn, không nên luôn mở một transaction duy nhất cho hàng trăm nghìn bản ghi. Transaction dài có thể:
- Giữ connection lâu.
- Tăng lock duration.
- Làm persistence context phình lớn.
- Tăng chi phí dirty checking và bộ nhớ.
- Khó retry nếu lỗi xảy ra ở cuối batch.

Có thể chia thành các batch nhỏ, mỗi batch là một thao tác nghiệp vụ có transaction riêng:

~~~java
@Service
public class ImportCoordinator {

    private final ImportBatchWorker worker;

    public ImportCoordinator(ImportBatchWorker worker) {
        this.worker = worker;
    }

    public void importRows(List<List<ImportRow>> batches) {
        for (List<ImportRow> batch : batches) {
            worker.processBatch(batch);
        }
    }
}

@Service
public class ImportBatchWorker {

    @Transactional
    public void processBatch(List<ImportRow> batch) {
        // Validate và ghi một batch.
    }
}
~~~

Tách bean giúp lời gọi đi qua proxy. Nếu cần một batch thất bại mà không ảnh hưởng các batch đã commit trước đó, đây là ranh giới phù hợp. Nếu toàn bộ file phải atomic, cần một thiết kế khác và chấp nhận transaction lớn hoặc quy trình staging/đổi trạng thái sau khi import hoàn tất.

## 21. Timeout và lock timeout

Một thao tác nghiệp vụ có thể bị treo hoặc chờ lock lâu. **@Transactional** hỗ trợ timeout theo giây:

~~~java
@Transactional(timeout = 10)
public void confirmOrder(Long orderId) {
    // Thao tác cần hoàn tất trong thời gian giới hạn.
}
~~~

Timeout là gợi ý/thiết lập cho transaction manager và resource; cách thực thi cụ thể phụ thuộc nền tảng. Nó không thay thế timeout riêng cho HTTP client, message broker hoặc các hệ thống bên ngoài.

Lock timeout có thể được cấu hình qua JPA query hints hoặc lock settings tùy provider. Hãy xác định rõ hành vi khi hết timeout: rollback, retry, báo lỗi cho người dùng hay chuyển sang trạng thái chờ.

## 22. Kiểm thử ranh giới transaction

Cần kiểm tra không chỉ việc từng Repository lưu được dữ liệu mà còn việc toàn bộ thao tác nghiệp vụ có rollback cùng nhau hay không.

Ví dụ integration test:

~~~java
@SpringBootTest
class OrderTransactionIntegrationTest {

    @Autowired
    private OrderApplicationService orderService;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ProductRepository productRepository;

    @Test
    void rollsBackAllDatabaseChangesWhenOrderCreationFails() {
        Product product = productRepository.saveAndFlush(
                new Product("Keyboard", 5)
        );

        int stockBefore = product.getStock();

        assertThrows(
                OrderCreationException.class,
                () -> orderService.placeOrder(
                        CreateOrderCommand.invalidForTest(product.getId())
                )
        );

        Product reloaded = productRepository.findById(product.getId())
                .orElseThrow();

        assertEquals(stockBefore, reloaded.getStock());
        assertEquals(0, orderRepository.count());
    }
}
~~~

Đây là cấu trúc minh họa; cần tạo fixture và một điểm lỗi có kiểm soát trong service để kiểm tra rollback. Không đánh dấu test class hoặc test method **@Transactional** nếu mục tiêu là quan sát transaction service đã commit/rollback độc lập mà không hiểu rõ transaction test của Spring. Các test slice như **@DataJpaTest** thường tự chạy trong transaction và rollback sau test, nên cần cân nhắc cách kiểm tra trạng thái sau khi service kết thúc.

Nên kiểm tra:
1. Thành công: tất cả thay đổi cần thiết đều tồn tại.
2. Thất bại ở bước sau: các thay đổi database trước đó rollback.
3. Checked exception có rollback khi được cấu hình rollbackFor.
4. REQUIRED tham gia transaction ngoài.
5. REQUIRES_NEW có thể commit độc lập khi đó là yêu cầu.
6. Optimistic locking phát hiện cập nhật đồng thời.
7. Outbox được ghi cùng transaction với dữ liệu nghiệp vụ.
8. Event chỉ được xử lý sau commit.
9. Các batch có transaction riêng commit/rollback đúng phạm vi.
10. Không có truy vấn lazy ngoài transaction ngoài dự kiến.

## 23. Những lỗi thường gặp

**Đặt transaction riêng cho từng Repository operation**

Các thao tác có thể commit độc lập, khiến một use case chỉ hoàn thành một phần. Đặt transaction ở service bao quanh các thay đổi cần nguyên tử.

**Cho rằng save() đồng nghĩa commit**

save() thường chỉ persist/merge trong persistence context; SQL có thể được flush sau đó và commit xảy ra ở ranh giới transaction.

**Nhầm flush với commit**

flush gửi thay đổi đang chờ xuống database nhưng transaction vẫn có thể rollback.

**Bắt exception rồi trả về bình thường**

Transaction có thể commit nếu lỗi không làm transaction bị đánh dấu rollback-only. Ném lại lỗi hoặc đánh dấu rollback-only khi nghiệp vụ yêu cầu rollback.

**Dùng checked exception mà quên rollbackFor**

Checked exception không rollback theo quy tắc mặc định phổ biến. Khai báo rollbackFor hoặc cấu hình rollback rule phù hợp.

**Dùng REQUIRES_NEW cho thao tác phải nguyên tử với thao tác chính**

Transaction con có thể commit dù transaction ngoài rollback. Dùng REQUIRED nếu các thay đổi thuộc cùng invariant nghiệp vụ.

**Gọi self-invocation và kỳ vọng proxy áp dụng annotation**

Lời gọi nội bộ qua this không đi qua proxy thông thường. Tách bean hoặc thiết kế ranh giới method rõ ràng.

**Giữ transaction trong lúc gọi HTTP hoặc chờ người dùng**

Connection và lock có thể bị giữ lâu; hệ thống ngoài không thể rollback cùng database. Dùng outbox/saga hoặc workflow nhiều bước.

**Cho rằng một @Transactional bao trùm mọi database**

Transaction chỉ áp dụng theo transaction manager/resource được cấu hình. Nhiều datasource cần thiết kế phân tán riêng.

**Không kiểm soát cập nhật đồng thời**

Atomicity không tự ngăn lost update hoặc bán vượt tồn kho. Dùng @Version, lock, atomic update hoặc constraint.

## 24. Quy trình xác định ranh giới giao dịch

Khi thiết kế một use case, hãy trả lời:

1. Đây là một thao tác nghiệp vụ nào và kết quả thành công cần bảo đảm điều gì?
2. Những thay đổi database nào phải cùng commit hoặc rollback?
3. Các Repository có dùng chung datasource và transaction manager không?
4. Phương thức service nào là điểm vào của use case?
5. REQUIRED có đủ để các service con tham gia transaction hiện tại không?
6. Có checked exception nào cần rollback không?
7. Có thao tác HTTP, email hoặc message broker cần đưa ra ngoài transaction không?
8. Có cần outbox hoặc saga để phối hợp hệ thống ngoài không?
9. Có nguy cơ cập nhật đồng thời, deadlock hoặc transaction kéo dài không?
10. Cần Page/DTO/fetch plan nào để đọc dữ liệu trong transaction mà không gây lazy loading ngoài dự kiến?
11. Integration test có chứng minh được cả commit và rollback của toàn bộ use case không?

Nguyên tắc thiết kế là đặt transaction tại nơi hiểu rõ invariant nghiệp vụ, giữ nó đủ ngắn để tránh chiếm tài nguyên lâu và bao quanh đúng các thay đổi database cần nguyên tử.

## 25. Kết luận

Ranh giới transaction trong Spring Data JPA thường nên được đặt ở phương thức service đại diện cho một thao tác nghiệp vụ. Một transaction có thể bao gồm nhiều Repository nếu chúng cùng dùng transaction manager và resource phù hợp. REQUIRED mặc định giúp các service con tham gia transaction hiện tại; REQUIRES_NEW tạo transaction độc lập và có thể commit dù thao tác ngoài rollback. Cần hiểu rollback rule, proxy/self-invocation, flush so với commit, isolation và cập nhật đồng thời. Các lời gọi mạng và message broker không tự rollback cùng database; hãy dùng outbox hoặc workflow saga khi cần phối hợp. Kiểm thử cả đường thành công lẫn lỗi giữa chừng để chứng minh toàn bộ thao tác được commit hoặc rollback đúng như invariant nghiệp vụ.
