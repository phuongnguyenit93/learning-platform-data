# Chọn ranh giới @Transactional ở tầng dịch vụ trong Spring Data JDBC

## 1. Vì sao ranh giới transaction nên nằm ở service?

Một nghiệp vụ thường gồm nhiều thao tác persistence. Ví dụ tạo đơn hàng có thể cần lưu đơn hàng, các dòng hàng, giữ tồn kho và ghi nhận lịch sử. Nếu một thao tác thất bại giữa chừng, ứng dụng thường muốn toàn bộ thay đổi trong database cùng thành công hoặc cùng rollback.

Nếu chỉ dựa vào transaction của từng repository method, các lời gọi riêng lẻ có thể có ranh giới commit riêng. Thao tác đầu tiên có thể đã commit trước khi thao tác tiếp theo thất bại.

Tầng service là nơi điều phối **một use case nghiệp vụ**. Vì vậy, đây thường là vị trí phù hợp để khai báo `@Transactional` bao quanh toàn bộ thao tác database cần cùng một kết quả.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(
            OrderRepository orders,
            InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        Order saved = orders.save(order);

        inventory.reserve(
                command.productId(),
                command.quantity()
        );

        return saved;
    }
}
~~~

Nếu lưu đơn hàng thành công nhưng cập nhật tồn kho phát sinh exception làm transaction rollback, thay đổi database của cả hai thao tác được rollback cùng nhau, với điều kiện chúng dùng chung transaction manager và DataSource.

Service định nghĩa ranh giới nghiệp vụ; repository thực hiện các thao tác persistence bên trong ranh giới đó.

## 2. Transaction bao phủ những gì?

Một transaction JDBC thường bao gồm các câu SQL được thực hiện trên cùng connection do transaction manager quản lý. Khi transaction commit, database xác nhận các thay đổi. Khi rollback, database hủy các thay đổi chưa commit trong transaction đó.

Một use case có thể có luồng:

~~~mermaid
flowchart TD
    A["Controller gọi service"] --> B["Mở hoặc tham gia transaction"]
    B --> C["Repository lưu aggregate"]
    C --> D["Repository cập nhật dữ liệu liên quan"]
    D --> E["Repository ghi lịch sử"]
    E --> F{"Có lỗi cần rollback?"}
    F -->|Không| G["Commit"]
    F -->|Có| H["Rollback"]
    G --> I["Trả kết quả cho caller"]
    H --> J["Ném exception"]
~~~

Ví dụ, một nghiệp vụ chuyển tiền có thể cần cập nhật tài khoản nguồn, cập nhật tài khoản đích và ghi giao dịch. Nếu ba thao tác phải cùng thành công hoặc cùng thất bại, chúng nên nằm trong một transaction do service quản lý.

Không nên đặt ranh giới transaction chỉ theo số lượng repository được gọi. Hai repository không có nghĩa luôn cần một transaction chung; một repository cũng có thể cần nhiều thao tác cùng nằm trong một transaction. Hãy dựa trên yêu cầu nhất quán của use case.

## 3. Transaction mặc định của repository và transaction ở service

Spring Data JDBC cung cấp implementation CRUD cho repository. Các method CRUD kế thừa thường đã có cấu hình transaction: thao tác đọc thường là read-only, còn thao tác ghi được chạy trong transaction. Tuy nhiên, query method do ứng dụng khai báo không mặc nhiên có transaction configuration giống các CRUD method kế thừa.

Điều này dẫn tới hai tình huống:

- Gọi một CRUD repository method độc lập: transaction mặc định của repository có thể bao quanh lời gọi đó.
- Gọi nhiều repository method trong một service có `@Transactional`: các lời gọi repository thường tham gia transaction đang tồn tại theo propagation mặc định `REQUIRED`.

Ví dụ không có transaction ở service:

~~~java
public void createOrder(CreateOrderCommand command) {
    orders.save(Order.create(command));
    inventory.reserve(command.productId(), command.quantity());
}
~~~

Mỗi repository call có thể được quản lý trong transaction riêng theo cấu hình của repository. Nếu thao tác đầu tiên đã commit rồi thao tác thứ hai thất bại, database có thể giữ đơn hàng trong khi tồn kho chưa được giữ.

Đặt transaction ở service:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    orders.save(Order.create(command));
    inventory.reserve(command.productId(), command.quantity());
}
~~~

Với transaction manager và DataSource chung, repository method tham gia transaction hiện tại. Commit chỉ xảy ra khi service method hoàn tất bình thường và transaction không bị đánh dấu rollback-only.

**Quy tắc thực hành:** nếu nhiều thao tác database là một đơn vị nghiệp vụ, đặt transaction ở service method đại diện cho đơn vị đó.

## 4. Chọn method service làm ranh giới

Một service có thể có nhiều use case, mỗi use case có transaction policy riêng:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final AddressRepository addresses;

    public CustomerService(
            CustomerRepository customers,
            AddressRepository addresses
    ) {
        this.customers = customers;
        this.addresses = addresses;
    }

    @Transactional
    public Customer register(RegisterCustomerCommand command) {
        Customer customer = customers.save(
                Customer.newCustomer(command.name(), command.email())
        );

        addresses.save(
                Address.forCustomer(customer.getId(), command.address())
        );

        return customer;
    }

    @Transactional(readOnly = true)
    public CustomerDetails getDetails(Long customerId) {
        Customer customer = customers.findById(customerId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));

        List<Address> customerAddresses =
                addresses.findByCustomerId(customerId);

        return CustomerDetails.from(customer, customerAddresses);
    }
}
~~~

`register` ghi nhiều aggregate có liên quan nên cần transaction ghi. `getDetails` chỉ đọc nên được đánh dấu read-only.

Không phải mọi method trong service đều bắt buộc có annotation. Nếu một method chỉ điều phối một thao tác repository vốn đã có transaction phù hợp, annotation bổ sung có thể không cần thiết. Nhưng khi service method là một use case cần nhiều thao tác cùng atomic, khai báo rõ ranh giới ở đó giúp contract dễ hiểu và ổn định hơn.

### 4.1. Đặt ở class hay method?

Có thể đặt `@Transactional` ở cấp class:

~~~java
@Service
@Transactional
public class OrderService {
    // Các public method mặc định tham gia transaction.
}
~~~

Hoặc đặt ở từng method:

~~~java
@Service
public class OrderService {

    @Transactional
    public Order placeOrder(...) {
        // Use case ghi dữ liệu.
    }

    @Transactional(readOnly = true)
    public OrderDetails getDetails(...) {
        // Use case chỉ đọc.
    }
}
~~~

Đặt ở class giúp giảm lặp nếu hầu hết method có cùng policy. Đặt ở method làm rõ sự khác biệt giữa use case đọc và ghi. Method-level annotation có thể ghi đè cấu hình ở class-level.

Với service có cả truy vấn và cập nhật, cách khai báo ở method thường giúp người đọc nhận ra transaction policy ngay tại use case.

## 5. Cách Spring áp dụng @Transactional

Trong cấu hình thông thường, Spring quản lý transaction bằng AOP proxy. Caller gọi method qua proxy; proxy bắt đầu hoặc tham gia transaction, gọi method thật, rồi commit hoặc rollback dựa trên kết quả.

~~~mermaid
sequenceDiagram
    participant C as Controller / Caller
    participant P as Spring Proxy
    participant S as Service
    participant R as Repository
    participant DB as Database
    C->>P: placeOrder()
    P->>P: Begin / join transaction
    P->>S: Gọi method thật
    S->>R: save()
    R->>DB: INSERT / UPDATE
    DB-->>R: Kết quả
    R-->>S: Entity đã lưu
    S-->>P: Return hoặc exception
    alt Method hoàn tất bình thường
        P->>DB: COMMIT
    else Có exception cần rollback
        P->>DB: ROLLBACK
    end
    P-->>C: Kết quả
~~~

Annotation không tự biến mọi lời gọi method thành transaction. Lời gọi phải đi qua cơ chế transaction interceptor của Spring.

### 5.1. Self-invocation không đi qua proxy

Một lỗi thường gặp là method trong cùng class gọi method khác có `@Transactional` bằng `this`:

~~~java
@Service
public class ImportService {

    public void importAll(List<ImportRow> rows) {
        this.importChunk(rows);
    }

    @Transactional
    public void importChunk(List<ImportRow> rows) {
        // Ghi dữ liệu.
    }
}
~~~

Lời gọi `this.importChunk(...)` là lời gọi nội bộ trên cùng object, không đi qua proxy theo cách proxy-based transaction hoạt động mặc định. Do đó annotation trên `importChunk` có thể không được áp dụng như mong đợi.

Cách rõ ràng hơn là đặt transaction trên method được caller bên ngoài gọi:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll(List<ImportRow> rows) {
        // Gọi repository trực tiếp trong transaction của use case.
    }
}
~~~

Hoặc tách phần xử lý chunk sang một bean khác nếu mỗi chunk cần một transaction độc lập:

~~~java
@Service
public class ImportCoordinator {

    private final ImportChunkService chunks;

    public ImportCoordinator(ImportChunkService chunks) {
        this.chunks = chunks;
    }

    public void importAll(List<ImportRow> rows) {
        for (List<ImportRow> chunk : split(rows, 500)) {
            chunks.importChunk(chunk);
        }
    }
}

@Service
public class ImportChunkService {

    @Transactional
    public void importChunk(List<ImportRow> chunk) {
        // Mỗi lời gọi qua bean proxy có thể có transaction riêng.
    }
}
~~~

Đoạn code minh họa ranh giới; hàm `split` cần được triển khai theo ứng dụng. Vì mỗi lần gọi đi qua bean khác, proxy của `ImportChunkService` có thể áp dụng transaction cho từng chunk.

### 5.2. Visibility và cách gọi

Để dễ dự đoán hành vi trong cấu hình proxy thông thường, hãy đặt `@Transactional` trên public method của service và gọi method đó qua Spring-managed bean. Chi tiết hỗ trợ method visibility phụ thuộc kiểu proxy và phiên bản Spring; tránh dựa vào hành vi ít phổ biến nếu không cần thiết.

Không tạo service bằng `new OrderService(...)` rồi mong annotation hoạt động. Bean phải do Spring quản lý và caller phải đi qua proxy tương ứng.

## 6. Propagation: repository tham gia transaction của service

Thuộc tính propagation quyết định cách một method transactional tham gia transaction đang tồn tại.

Mặc định là `Propagation.REQUIRED`:

- Nếu chưa có transaction, Spring tạo transaction mới.
- Nếu đã có transaction, method tham gia transaction hiện tại.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
~~~

Các repository call thông thường tham gia transaction service đang mở nếu chúng sử dụng cùng transaction manager/DataSource và propagation phù hợp.

### 6.1. REQUIRED là lựa chọn thông thường

`REQUIRED` phù hợp với phần lớn use case vì toàn bộ thao tác thuộc cùng transaction. Nếu thao tác bên trong thất bại theo cách đánh dấu transaction rollback-only, transaction ngoài không thể commit như thể mọi thứ đều thành công.

Ví dụ service A gọi service B, cả hai dùng `REQUIRED`:

~~~java
@Service
public class CheckoutService {

    private final PaymentRecordService paymentRecords;

    @Transactional
    public void checkout(Order order) {
        // Ghi order.
        paymentRecords.record(order);
        // Các thao tác cùng transaction.
    }
}

@Service
public class PaymentRecordService {

    @Transactional
    public void record(Order order) {
        // Ghi payment record.
    }
}
~~~

Nếu hai service dùng cùng transaction manager, lời gọi `record` tham gia transaction của `checkout`. Ranh giới commit vẫn thuộc transaction ngoài cùng.

### 6.2. REQUIRES_NEW tạo transaction độc lập

`Propagation.REQUIRES_NEW` tạm treo transaction hiện tại và mở một transaction độc lập cho method được gọi.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

Nếu transaction ngoài rollback, transaction audit độc lập đã commit vẫn có thể tồn tại. Điều này đôi khi hữu ích với một số bản ghi kỹ thuật, nhưng cần hiểu rõ ý nghĩa dữ liệu.

Không dùng `REQUIRES_NEW` chỉ để “tránh lỗi transaction”. Nó có thể commit dữ liệu độc lập với nghiệp vụ chính, cần thêm connection trong khi transaction ngoài đang giữ connection, tạo áp lực lên connection pool và làm cho audit hoặc trạng thái phụ tồn tại dù use case chính thất bại.

Nếu audit phải phản ánh chính xác giao dịch đã commit, hãy cân nhắc transactional outbox hoặc ghi audit trong cùng transaction thay vì tách độc lập một cách tùy tiện.

### 6.3. NESTED và savepoint

`Propagation.NESTED` có thể dùng savepoint trong transaction hiện tại nếu transaction manager và JDBC driver hỗ trợ. Đây không phải một transaction vật lý độc lập như `REQUIRES_NEW`, và không phải môi trường nào cũng hỗ trợ nested transaction theo cách này.

Với phần lớn service Spring Data JDBC, hãy bắt đầu bằng `REQUIRED`. Chỉ chọn propagation khác khi yêu cầu commit/rollback độc lập đã được xác định rõ.

## 7. Rollback rules: exception nào làm transaction rollback?

Theo mặc định của Spring transaction, transaction rollback khi method thoát ra với `RuntimeException` hoặc `Error`. Checked exception thường không tự động làm rollback.

Ví dụ:

~~~java
@Transactional
public void createOrder(Order order) throws IOException {
    orders.save(order);
    throw new IOException("Không thể hoàn tất use case");
}
~~~

Nếu `IOException` là checked exception và không có rollback rule bổ sung, Spring mặc định có thể commit transaction database dù method ném exception ra caller.

Nếu nghiệp vụ yêu cầu checked exception cũng rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void createOrder(Order order) throws IOException {
    orders.save(order);
    throw new IOException("Không thể hoàn tất use case");
}
~~~

Có thể chỉ định nhiều loại exception:

~~~java
@Transactional(rollbackFor = {
        IOException.class,
        ValidationFailureException.class
})
public void process(...) throws IOException, ValidationFailureException {
    // ...
}
~~~

`noRollbackFor` có thể dùng để khai báo một loại exception không làm rollback, nhưng cần thận trọng vì caller có thể nhận lỗi trong khi thay đổi database vẫn commit.

### 7.1. Bắt exception rồi tiếp tục

Ví dụ:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        log.warn("Không giữ được tồn kho", ex);
        // Không ném lại exception.
    }
}
~~~

Nếu exception bị bắt và không làm transaction bị đánh dấu rollback-only, method có thể kết thúc bình thường và transaction commit phần thay đổi đã thực hiện. Kết quả có thể là đơn hàng được lưu dù không giữ được tồn kho.

Nếu nghiệp vụ yêu cầu cả hai cùng thành công, hãy để exception phù hợp thoát ra ngoài hoặc chuyển thành runtime exception:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        throw new OrderPlacementException(
                "Không thể tạo đơn hàng",
                ex
        );
    }
}
~~~

Nếu một transaction tham gia đã bị đánh dấu rollback-only, transaction ngoài có thể gặp `UnexpectedRollbackException` khi cố commit. Đừng nuốt exception rồi giả định transaction vẫn có thể commit.

## 8. readOnly, isolation và timeout

`@Transactional` còn có các thuộc tính điều khiển cách transaction chạy.

### 8.1. readOnly = true

Dùng cho use case chỉ đọc:

~~~java
@Transactional(readOnly = true)
public OrderDetails getOrderDetails(Long orderId) {
    // Đọc order và các dữ liệu liên quan.
}
~~~

`readOnly = true` là một gợi ý/thuộc tính transaction cho transaction manager và provider bên dưới. Tùy nền tảng, nó có thể giúp tối ưu hoặc được database kiểm tra; không nên coi annotation này là cơ chế bảo mật bảo đảm không có câu ghi nào được thực hiện.

Nếu method thực hiện ghi dữ liệu, không đánh dấu read-only. Nếu method read-only tham gia một transaction đã tồn tại với cấu hình khác, policy của transaction đang tồn tại có thể quyết định hành vi thực tế.

### 8.2. Isolation

Isolation xác định mức độ một transaction nhìn thấy thay đổi đồng thời từ transaction khác. Có thể chỉ định:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateInventory(...) {
    // Đọc và cập nhật tồn kho.
}
~~~

Một số mức isolation thường gặp:

| Isolation | Ý nghĩa khái quát |
|---|---|
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit |
| REPEATABLE_READ | Đọc lại cùng hàng trong transaction có tính ổn định cao hơn |
| SERIALIZABLE | Yêu cầu mức cô lập cao nhất theo semantics database |

Mức isolation thực tế và anomaly được ngăn chặn phụ thuộc database. Không tăng isolation chỉ vì muốn “an toàn hơn”; mức cao hơn có thể giảm concurrency, tăng lock hoặc gây serialization failure.

Khi method tham gia một transaction đã tồn tại, yêu cầu isolation mới có thể không được áp dụng như một transaction mới. Đặt isolation ở ranh giới ngoài cùng của use case và hiểu cấu hình transaction manager.

### 8.3. timeout

Có thể đặt giới hạn thời gian cho transaction:

~~~java
@Transactional(timeout = 10)
public void updateOrder(...) {
    // Use case có thời gian xử lý dự kiến ngắn.
}
~~~

Timeout được tính bằng giây trong thuộc tính annotation. Hỗ trợ và cách timeout được thực thi phụ thuộc transaction manager/driver/database. Timeout transaction không thay thế timeout cho HTTP client hoặc các dịch vụ bên ngoài.

## 9. Nhiều repository phải dùng chung transaction manager

Để các thao tác repository cùng nằm trong một transaction, chúng phải tham gia cùng transaction manager và cùng resource phù hợp, thường là cùng DataSource.

Ví dụ:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence"
)
public class JdbcConfiguration {
    // DataSource và transaction manager của ứng dụng.
}
~~~

Trong Spring Boot, cấu hình auto-configuration có thể tạo transaction manager dựa trên DataSource. Nếu ứng dụng khai báo nhiều DataSource hoặc nhiều transaction manager, cần chỉ rõ manager mà service sử dụng:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void placeOrder(...) {
    // Các repository dùng đúng DataSource được manager quản lý.
}
~~~

Nếu hai repository dùng hai DataSource khác nhau và hai transaction manager độc lập, một `@Transactional` thông thường không tự tạo transaction phân tán bao trùm cả hai database. Khi cần atomicity xuyên nhiều resource, phải thiết kế giải pháp phù hợp như XA/JTA nếu hạ tầng hỗ trợ, hoặc dùng mô hình saga/outbox và xử lý bù trừ.

Đừng giả định chỉ vì hai repository cùng được inject vào một service mà chúng tự động chia sẻ một transaction.

## 10. Không kéo dài transaction qua công việc bên ngoài database

Transaction database nên ngắn và tập trung vào các thao tác cần commit/rollback cùng nhau.

Tránh giữ transaction mở trong lúc gọi API bên ngoài qua HTTP, gửi email hoặc thông báo, chờ người dùng nhập dữ liệu, chạy tính toán lâu không cần giữ connection, hay xử lý file lớn trong thời gian dài.

Ví dụ không nên:

~~~java
@Transactional
public void registerAndNotify(Customer customer) {
    customers.save(customer);
    emailClient.sendWelcomeEmail(customer); // Mạng ngoài database.
}
~~~

Nếu gửi email mất nhiều giây hoặc timeout, connection database có thể bị giữ trong suốt thời gian đó. Email cũng không thể rollback cùng transaction JDBC: database rollback không thể thu hồi email đã gửi.

Một cách thiết kế thường dùng là ghi dữ liệu nghiệp vụ và một bản ghi outbox trong cùng transaction:

~~~java
@Transactional
public Customer register(RegisterCustomerCommand command) {
    Customer saved = customers.save(Customer.create(command));

    outbox.save(OutboxMessage.welcomeEmailRequested(
            saved.getId(),
            saved.getEmail()
    ));

    return saved;
}
~~~

Một worker riêng đọc outbox sau khi transaction commit rồi gửi email. Nếu gửi thất bại, worker có thể retry theo chính sách idempotent. Bản ghi outbox cùng transaction giúp sự kiện không bị phát đi nếu nghiệp vụ chính rollback.

Nếu không dùng outbox, có thể phát event sau commit bằng cơ chế phù hợp như transaction-bound event listener, nhưng vẫn cần suy nghĩ về độ tin cậy khi tiến trình dừng giữa commit và gửi event.

## 11. Transaction không tự lan sang thread khác

Transaction JDBC trong mô hình imperative của Spring thường gắn với thread hiện tại thông qua transaction manager. Không giả định một transaction tự lan sang thread mới.

Ví dụ:

~~~java
@Transactional
public void process(Order order) {
    orders.save(order);

    CompletableFuture.runAsync(() -> {
        auditRepository.save(AuditRecord.forOrder(order));
    });
}
~~~

Phần việc trong `CompletableFuture` có thể chạy ở thread khác và không tham gia transaction của method bên ngoài. Method bên ngoài có thể commit trước khi tác vụ async chạy hoặc hoàn tất.

Nếu công việc async cần dữ liệu chỉ được xử lý sau commit, hãy phát sự kiện/outbox và để worker mở transaction riêng. Nếu hai thao tác bắt buộc atomic, hãy thực hiện chúng đồng bộ trong cùng transaction hoặc thiết kế một protocol phân tán phù hợp.

## 12. Kiểm thử ranh giới transaction

Nên kiểm thử hành vi rollback ở mức integration với database mà ứng dụng sử dụng.

Ví dụ tình huống:

1. Service lưu một order.
2. Repository tiếp theo phát sinh exception.
3. Service không bắt exception hoặc chuyển thành runtime exception.
4. Test xác nhận order không còn trong database sau rollback.

~~~java
@SpringBootTest
class OrderServiceTransactionTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orders;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        assertThatThrownBy(() ->
                orderService.placeOrder(commandThatCannotReserveStock())
        ).isInstanceOf(OrderPlacementException.class);

        assertThat(orders.findByExternalReference("REF-001"))
                .isEmpty();
    }
}
~~~

Đây là ví dụ minh họa; fixture, exception và repository method phải khớp ứng dụng thật.

### 12.1. Chú ý transaction của test

Một số test slice như `@DataJdbcTest` tự chạy test trong transaction và rollback khi test kết thúc. Điều này tiện cho việc cô lập dữ liệu, nhưng có thể che khuất hành vi commit thực tế của service.

Nếu cần xác nhận transaction service commit/rollback độc lập, hãy thiết kế test để quan sát đúng ranh giới transaction. Test nên gọi Spring-managed bean để proxy transaction được áp dụng, không gọi trực tiếp object tự tạo.

Kiểm thử trên H2 có thể không phản ánh đầy đủ locking, isolation, SQL dialect hoặc constraint của database production. Với hành vi phụ thuộc database, hãy dùng Testcontainers hoặc môi trường kiểm thử cùng hệ quản trị.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository thứ nhất đã commit nhưng repository thứ hai lỗi | Không có transaction chung ở service | Đặt `@Transactional` quanh use case |
| Annotation không có tác dụng | Service không do Spring quản lý hoặc caller bypass proxy | Inject bean và gọi qua Spring proxy |
| Self-invocation không mở transaction mới | Method gọi method cùng instance bằng `this` | Đặt annotation ở entry method hoặc tách bean |
| Checked exception nhưng dữ liệu vẫn commit | Default rollback rule không rollback checked exception | Dùng `rollbackFor` nếu nghiệp vụ yêu cầu |
| Bắt exception nhưng dữ liệu vẫn commit | Exception bị nuốt và transaction không rollback-only | Ném lại exception hoặc đánh dấu rollback |
| UnexpectedRollbackException ở cuối | Transaction tham gia đã bị đánh dấu rollback-only | Tìm exception gốc và xử lý ranh giới propagation |
| REQUIRES_NEW làm cạn connection pool | Transaction ngoài giữ connection trong khi transaction mới cần connection khác | Chỉ dùng khi cần commit độc lập; đánh giá pool |
| Read-only vẫn ghi được dữ liệu | readOnly là hint tùy transaction manager/database | Không dùng nó làm cơ chế phân quyền hoặc bảo vệ |
| Isolation mong muốn không có hiệu lực | Method tham gia transaction đã mở với isolation khác | Đặt isolation ở transaction boundary ngoài cùng |
| Hai repository không rollback cùng nhau | Chúng dùng DataSource/transaction manager khác nhau | Cấu hình đúng manager hoặc thiết kế distributed workflow |
| Async chạy ngoài transaction | Thread mới không thừa kế JDBC transaction | Mở transaction riêng hoặc dùng outbox/event |
| Transaction giữ connection quá lâu | Gọi HTTP, email hoặc xử lý lâu bên trong transaction | Thu hẹp transaction và chuyển side effect ra ngoài |
| Test pass nhưng production rollback khác | Test framework tự bọc transaction hoặc DB khác semantics | Kiểm thử integration trên DB mục tiêu |

## 14. Quy trình chọn ranh giới @Transactional

1. Xác định use case nghiệp vụ mà caller yêu cầu.
2. Liệt kê các thao tác database phải cùng thành công hoặc cùng rollback.
3. Đặt `@Transactional` ở public service method đại diện cho use case.
4. Đảm bảo các repository tham gia cùng transaction manager và DataSource.
5. Giữ transaction ngắn; đưa HTTP, email và công việc dài ra ngoài.
6. Chọn propagation mặc định `REQUIRED` trừ khi có lý do rõ ràng cho semantics khác.
7. Xác định rollback rule cho checked exception và exception nghiệp vụ.
8. Dùng `readOnly = true` cho use case chỉ đọc khi phù hợp.
9. Chỉ đặt isolation/timeout đặc biệt khi yêu cầu concurrency và database đã được hiểu.
10. Kiểm thử commit/rollback bằng Spring-managed service và database phù hợp.

## 15. Bài tập thực hành

### Bài 1 — Hai repository trong một use case

Tạo service lưu `Order` rồi cập nhật `Inventory`. Cho thao tác thứ hai phát sinh exception. So sánh trạng thái database khi có và không có `@Transactional` ở service.

### Bài 2 — Repository transaction và service transaction

Gọi một CRUD repository method độc lập, sau đó gọi hai repository method trong một service. Bật SQL/transaction logging để quan sát ranh giới transaction.

### Bài 3 — Checked exception

Tạo method transactional lưu entity rồi ném checked exception. Quan sát dữ liệu sau lời gọi. Thêm `rollbackFor` và so sánh.

### Bài 4 — Self-invocation

Tạo một service có method ngoài gọi method trong cùng class mang `@Transactional`. So sánh với việc chuyển method vào bean khác và gọi qua proxy.

### Bài 5 — Propagation

Thử `REQUIRED` và `REQUIRES_NEW`. Cho transaction ngoài rollback sau khi transaction trong hoàn tất. Quan sát bản ghi nào còn tồn tại và giải thích.

### Bài 6 — Read-only và isolation

Tạo use case đọc có `readOnly = true`. Kiểm tra transaction behavior trên database mục tiêu. Thử hai transaction cập nhật cùng một hàng để quan sát isolation và locking.

### Bài 7 — External side effect

Tạo use case lưu order và gửi email. Mô phỏng email gửi thành công nhưng transaction database rollback. Sau đó thiết kế outbox để tách việc gửi email khỏi transaction nghiệp vụ.

### Bài 8 — Async và thread boundary

Gọi một tác vụ async từ service transactional. Quan sát transaction context ở thread mới. Thiết kế worker mở transaction riêng và chỉ xử lý sau khi dữ liệu chính commit.

## 16. Ghi nhớ

- Ranh giới transaction nên phản ánh **một use case nghiệp vụ**, vì service là nơi điều phối các thao tác cần cùng thành công hoặc rollback.
- CRUD repository methods có transaction behavior mặc định, nhưng nhiều repository call độc lập không tự động tạo một transaction nghiệp vụ chung.
- Với `Propagation.REQUIRED`, repository/service method tham gia transaction hiện tại nếu cùng transaction manager và resource phù hợp.
- `@Transactional` được áp dụng qua Spring proxy trong cấu hình thông thường; self-invocation và việc tự tạo object có thể bypass proxy.
- Mặc định rollback với `RuntimeException` và `Error`; dùng `rollbackFor` cho checked exception khi nghiệp vụ yêu cầu.
- Không bắt rồi nuốt exception nếu transaction cần rollback.
- `REQUIRES_NEW` commit độc lập và có thể tồn tại dù transaction ngoài rollback; dùng có chủ đích.
- `readOnly` là hint transaction, không phải bảo đảm bảo mật rằng database không thể ghi.
- Isolation và timeout cần dựa trên concurrency, transaction manager và database thực tế.
- Nhiều repository chỉ cùng rollback khi chúng tham gia đúng transaction manager và DataSource; hai database khác nhau cần chiến lược riêng.
- Không giữ transaction JDBC trong lúc gọi dịch vụ ngoài hoặc chạy công việc dài; dùng outbox/event khi cần phát side effect sau commit.
- Transaction imperative không tự lan sang thread async.
