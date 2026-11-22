# Đặt @Transactional theo ranh giới ca sử dụng đã lựa chọn

Trong Domain-Driven Design (DDD), một use case thường thực hiện nhiều bước liên quan: tải aggregate, kiểm tra quyền, gọi hành vi miền, lưu thay đổi và ghi nhận sự kiện cần công bố. Nếu một bước thành công nhưng bước khác thất bại, trạng thái có thể bị dở dang. Transaction giúp nhóm các thao tác thuộc cùng một đơn vị công việc để chúng cùng commit hoặc cùng rollback trong một ranh giới được xác định.

Với Spring, annotation `@Transactional` thường được đặt ở application service hoặc command handler để thể hiện ranh giới transaction của use case. Cách đặt này giúp nhìn thấy rõ một hành động nghiệp vụ cần tính nguyên tử đến đâu. Domain model vẫn quyết định hành vi nào hợp lệ; Spring quản lý transaction và persistence resource; infrastructure adapter thực hiện lưu trữ hoặc gửi thông điệp theo hợp đồng đã chọn.

Không phải mọi method đều cần một transaction riêng, và một annotation cũng không tự làm cho nhiều hệ thống bên ngoài trở thành một transaction nguyên tử. Cần xác định dữ liệu nào phải commit cùng nhau, thao tác nào chỉ đọc, lỗi nào phải rollback và bước nào cần chuyển thành quy trình bất đồng bộ.

## Sau bài học này

Bạn có thể:

- Chọn transaction boundary theo mục tiêu và invariant của use case.
- Đặt `@Transactional` ở application layer theo cách dễ hiểu và dễ kiểm thử.
- Hiểu cơ chế proxy của Spring và giới hạn của self-invocation.
- Chọn propagation, isolation, timeout và readOnly theo nhu cầu.
- Hiểu rollback rules mặc định và cách xử lý checked exception.
- Tránh nuốt exception hoặc tiếp tục xử lý sau khi transaction đã rollback-only.
- Ghi aggregate và outbox trong cùng transaction.
- Tránh giữ transaction mở khi chờ HTTP, broker hoặc công việc bất đồng bộ.
- Kiểm thử transaction bằng Spring integration test và kiểm tra rollback thực tế.

## 1. Transaction boundary là ranh giới của một đơn vị công việc

Transaction boundary xác định nhóm thao tác nào cần được commit hoặc rollback cùng nhau. Ranh giới này nên xuất phát từ use case và invariant nghiệp vụ, không chỉ từ cấu trúc bảng hoặc số lượng repository.

Ví dụ use case xác nhận đơn:

1. Tải aggregate `Order`.
2. Kiểm tra actor có quyền xác nhận đơn.
3. Gọi `order.confirm()` để bảo vệ invariant.
4. Lưu aggregate.
5. Ghi Integration Event vào outbox.
6. Commit transaction.

Nếu lưu đơn thành công nhưng ghi outbox thất bại, hệ thống có thể có đơn đã xác nhận nhưng không có thông điệp để context khác tiếp tục xử lý. Vì vậy, nếu cả hai nằm trong cùng database transaction, cần commit chúng cùng nhau.

~~~mermaid
flowchart TD
    A[ConfirmOrder use case]
    B[Load Order aggregate]
    C[Check authorization]
    D[order.confirm]
    E[Save Order]
    F[Append Outbox message]
    G{Transaction commit?}
    H[All changes visible]
    I[Rollback all local changes]
    A --> B --> C --> D --> E --> F --> G
    G -->|Yes| H
    G -->|No| I
~~~

### Transaction boundary không đồng nghĩa với một method bất kỳ

Một repository method có thể chỉ lưu một aggregate, nhưng use case có thể cần lưu aggregate đó cùng một bản ghi outbox hoặc audit nghiệp vụ. Nếu đặt transaction riêng cho từng repository method, các bước có thể commit độc lập và để lại trạng thái không nhất quán.

Ngược lại, mở một transaction bao trùm toàn bộ request, mọi truy vấn, lời gọi HTTP và tác vụ dài có thể giữ connection/lock quá lâu. Ranh giới nên đủ rộng để bảo vệ tính nguyên tử cần thiết, nhưng đủ ngắn để không giữ tài nguyên khi chờ bên ngoài.

## 2. Vì sao thường đặt @Transactional ở Application Service?

Application Service điều phối một mục tiêu cụ thể của người dùng hoặc hệ thống. Nó biết những thao tác nào thuộc cùng use case và cần hoàn thành trong một đơn vị công việc.

Ví dụ:

~~~java
@Service
public class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;
    private final IntegrationEventTranslator translator;
    private final IntegrationEventOutbox outbox;
    private final Clock clock;

    public ConfirmOrderHandler(
        OrderRepository orders,
        OrderAccessPolicy accessPolicy,
        IntegrationEventTranslator translator,
        IntegrationEventOutbox outbox,
        Clock clock
    ) {
        this.orders = orders;
        this.accessPolicy = accessPolicy;
        this.translator = translator;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public ConfirmOrderResult handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        accessPolicy.ensureCanConfirm(command.actorId(), order);
        order.confirm(clock.instant());
        orders.save(order);

        List<IntegrationEvent> events =
            translator.translate(order.pullDomainEvents());
        outbox.append(events);

        return new ConfirmOrderResult(order.id(), order.status());
    }
}
~~~

Ví dụ đã lược giản các kiểu phụ trợ. Handler xác định transaction bao trùm việc tải aggregate, thực hiện hành vi, lưu thay đổi và append outbox. Aggregate không cần biết Spring hoặc annotation transaction.

### Domain layer không nên phụ thuộc Spring transaction

Không nên đặt `@Transactional` lên entity/aggregate chỉ vì một hành vi miền thay đổi trạng thái. Domain object thường chỉ thay đổi trạng thái trong bộ nhớ; transaction persistence thuộc application/infrastructure boundary.

Ví dụ, `order.confirm()` nên kiểm tra trạng thái và ghi nhận Domain Event. Nó không nên tự mở transaction, gọi EntityManager hoặc publish message. Application Service phối hợp các thao tác cần commit cùng nhau.

### Repository không nên tự quyết định transaction của toàn use case

Repository thường cung cấp thao tác tải/lưu aggregate. Có thể có transaction mặc định ở repository hoặc Spring Data, nhưng transaction boundary của use case nên được thể hiện ở application layer. Khi caller đã mở transaction, repository tham gia transaction đó theo propagation được cấu hình.

Nếu mỗi repository tự mở transaction độc lập, use case có thể mất tính nguyên tử giữa nhiều thao tác.

## 3. @Transactional hoạt động thông qua proxy

Trong chế độ proxy mặc định của Spring, `@Transactional` được thực thi khi một lời gọi đi qua proxy của Spring. Proxy bắt đầu hoặc tham gia transaction trước khi gọi method mục tiêu, rồi commit hoặc rollback sau khi method kết thúc.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring Transaction Proxy
    participant Service as Application Service
    participant DB as Database
    Caller->>Proxy: handle(command)
    Proxy->>DB: Begin or join transaction
    Proxy->>Service: Invoke target method
    Service->>DB: Read/write
    Service-->>Proxy: Return or throw
    alt Normal return
        Proxy->>DB: Commit
    else Rollback rule matches
        Proxy->>DB: Rollback
    end
    Proxy-->>Caller: Result or exception
~~~

Điều này có một hệ quả quan trọng: gọi method được đánh dấu transaction từ một method khác trong cùng object thường không đi qua proxy.

### Self-invocation không kích hoạt transaction mới

~~~java
@Service
public class OrderService {
    public void process() {
        confirm(); // Gọi trực tiếp trên this
    }

    @Transactional
    public void confirm() {
        // Không được proxy intercept khi được gọi nội bộ như trên.
    }
}
~~~

Nếu `process()` được gọi từ bên ngoài qua proxy, transaction của `process()` có thể bao trùm lời gọi nội bộ. Nhưng annotation trên `confirm()` không được áp dụng như một lời gọi proxy độc lập; propagation, isolation hoặc timeout khai báo riêng ở đó sẽ không có hiệu lực cho self-invocation.

### Cách tổ chức dễ hiểu hơn

Đặt transaction ở method use case được gọi từ adapter bên ngoài:

~~~java
@Service
public class ConfirmOrderHandler {
    @Transactional
    public void handle(ConfirmOrder command) {
        // Toàn bộ đơn vị công việc của use case.
    }
}
~~~

Nếu thực sự cần một transaction boundary khác, có thể tách thành bean khác với trách nhiệm rõ:

~~~java
@Service
public class OrderWorkflow {
    private final OrderStep orderStep;

    public void run(ConfirmOrder command) {
        orderStep.confirmInNewTransaction(command);
    }
}

@Service
public class OrderStep {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void confirmInNewTransaction(ConfirmOrder command) {
        // Transaction độc lập theo yêu cầu đã xác định.
    }
}
~~~

Không nên tách bean chỉ để né một chi tiết framework. Hãy tách khi transaction boundary thật sự khác và có ý nghĩa trong use case.

### Proxy mode và giới hạn class/method

Spring có thể dùng JDK dynamic proxy hoặc class-based proxy. JDK proxy dựa trên interface; class-based proxy tạo subclass. Các giới hạn cụ thể phụ thuộc cấu hình và phiên bản, nhưng cần nhớ:

- Method phải có thể được proxy intercept theo cơ chế đang dùng.
- Với class-based proxy, class hoặc method final không thể được override để intercept theo cách subclass thông thường.
- Private method không phải điểm gọi proxy phù hợp.
- Tự gọi method qua this không đi qua proxy.
- Không nên dựa vào việc gọi trực tiếp object được tạo bằng new rồi kỳ vọng annotation hoạt động.

Hãy dùng dependency injection để gọi bean qua Spring container và đặt annotation trên method ở ranh giới public/use-case phù hợp.

## 4. Propagation: transaction tham gia hay tạo mới?

Propagation xác định hành vi khi method transaction được gọi trong lúc đã có transaction hiện hành.

| Propagation | Hành vi | Trường hợp thường gặp |
| --- | --- | --- |
| REQUIRED | Tham gia transaction hiện có; nếu chưa có thì tạo mới | Mặc định phù hợp cho phần lớn use case và repository. |
| REQUIRES_NEW | Tạm dừng transaction hiện tại và tạo transaction mới | Một thao tác cần commit độc lập, sau khi đánh giá rõ hệ quả. |
| SUPPORTS | Tham gia nếu có transaction; nếu không thì chạy không transaction | Một số thao tác có thể chạy trong hoặc ngoài transaction. |
| MANDATORY | Bắt buộc caller đã có transaction; nếu không thì lỗi | Thành phần chỉ hợp lệ bên trong transaction do caller sở hữu. |
| NOT_SUPPORTED | Tạm dừng transaction hiện tại và chạy không transaction | Công việc không nên giữ transaction. |
| NEVER | Từ chối nếu đang có transaction | Bảo đảm một thao tác không chạy trong transaction. |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Một phần công việc có thể rollback về savepoint, không phải transaction độc lập. |

### REQUIRED là lựa chọn mặc định thường hợp lý

Khi command handler gọi repository, repository thường tham gia transaction của handler. Nếu chưa có transaction, method có thể tạo một transaction mới.

~~~java
@Service
public class PlaceOrderHandler {
    @Transactional
    public OrderId handle(PlaceOrder command) {
        Order order = Order.place(command, clock.instant());
        orders.save(order);
        return order.id();
    }
}
~~~

Repository được gọi trong transaction này sẽ tham gia theo REQUIRED nếu không cấu hình khác.

### REQUIRES_NEW có hệ quả riêng

REQUIRES_NEW tạo transaction độc lập. Transaction ngoài bị suspend; transaction trong có thể commit dù transaction ngoài sau đó rollback.

Điều này hữu ích cho một số bản ghi audit kỹ thuật hoặc tác vụ cần tồn tại độc lập, nhưng rất nguy hiểm nếu dùng tùy tiện cho dữ liệu nghiệp vụ phải cùng commit. Ví dụ, nếu ghi Order trong transaction ngoài nhưng ghi OrderConfirmed trong REQUIRES_NEW, event có thể tồn tại dù đơn bị rollback.

REQUIRES_NEW cũng có thể cần thêm database connection trong khi transaction ngoài đang giữ connection. Dùng quá nhiều có thể gây cạn connection pool hoặc deadlock theo cấu hình tải.

### NESTED không giống REQUIRES_NEW

NESTED thường dựa trên savepoint trong cùng transaction vật lý nếu transaction manager hỗ trợ. Rollback phần nested có thể quay về savepoint, nhưng commit của nested không độc lập với transaction ngoài; nếu transaction ngoài rollback thì thay đổi nested cũng rollback.

Không phải mọi transaction manager hoặc JPA setup đều hỗ trợ NESTED theo cùng cách. Cần xác nhận khả năng của transaction manager thực tế trước khi sử dụng.

## 5. Rollback rules mặc định của Spring

Mặc định, Spring rollback transaction khi method thoát ra với `RuntimeException` hoặc `Error`. Checked exception không tự động làm rollback theo mặc định truyền thống.

Ví dụ:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) throws InventoryFileException {
    Order order = createOrder(command);
    orders.save(order);
    throw new InventoryFileException("Could not read inventory file");
}
~~~

Nếu `InventoryFileException` là checked exception, transaction có thể commit theo rollback rules mặc định, dù method ném exception. Nếu nghiệp vụ yêu cầu rollback, khai báo rõ:

~~~java
@Transactional(rollbackFor = InventoryFileException.class)
public void placeOrder(PlaceOrder command) throws InventoryFileException {
    // ...
}
~~~

Hoặc chuyển lỗi thành một unchecked exception có ngữ nghĩa phù hợp nếu đó là quy ước của ứng dụng.

### noRollbackFor

`noRollbackFor` có thể chỉ định một loại exception không làm rollback dù thuộc nhóm mặc định rollback. Chỉ dùng khi nghiệp vụ thực sự muốn commit các thay đổi trước exception đó. Đây là cấu hình dễ gây bất ngờ nếu người đọc nghĩ mọi exception đều rollback.

### Exception bị bắt và nuốt

~~~java
@Transactional
public void handle(Command command) {
    try {
        performWork(command);
    } catch (RuntimeException ex) {
        log.warn("Work failed", ex);
        // Không ném lại và không đánh dấu rollback-only.
    }
}
~~~

Nếu exception bị bắt và không thoát khỏi method, interceptor có thể thấy method kết thúc bình thường và commit transaction. Nếu một resource/inner transactional call đã đánh dấu transaction rollback-only, commit ở ngoài có thể phát sinh `UnexpectedRollbackException`. Không nên dựa vào việc exception bị nuốt để quyết định trạng thái transaction.

Nếu lỗi có nghĩa use case thất bại, hãy ném lại exception hoặc chủ động đánh dấu rollback-only qua cơ chế phù hợp. Nếu lỗi là kết quả nghiệp vụ bình thường và vẫn muốn commit, hãy mô hình hóa kết quả đó rõ ràng thay vì dùng exception rồi nuốt.

### Không chuyển lỗi kỹ thuật thành kết quả thành công giả

Một handler không nên bắt lỗi database, ghi log rồi trả `SUCCESS`. Caller cần biết transaction đã commit hay chưa. Nếu muốn trả một kết quả từ chối nghiệp vụ mà vẫn commit một số dữ liệu như attempt record, cần thiết kế transaction và kết quả riêng cho trường hợp đó.

## 6. Isolation: kiểm soát tương tác giữa các transaction

Isolation level quyết định transaction nhìn thấy thay đổi đồng thời của transaction khác như thế nào. Các mức phổ biến trong JDBC/database gồm:

| Isolation | Đặc điểm khái quát |
| --- | --- |
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ. |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit; cùng một truy vấn có thể thấy kết quả khác ở lần đọc sau. |
| REPEATABLE_READ | Dữ liệu đã đọc có bảo đảm lặp lại theo định nghĩa của database; phantom behavior có thể khác nhau giữa hệ quản trị. |
| SERIALIZABLE | Cố gắng tạo hiệu quả tương đương chạy tuần tự; có thể tăng lock, conflict hoặc retry. |

Tên isolation level không bảo đảm mọi database triển khai giống hệt nhau. Cần hiểu database engine, MVCC, locking và cách transaction manager áp dụng.

### Chọn isolation theo invariant

Ví dụ, hai nhân viên cùng xác nhận một đơn. Aggregate có thể được tải ở cùng trạng thái ACCEPTED. Nếu cả hai cùng ghi, hệ thống cần ngăn cập nhật cạnh tranh làm tạo hai tác động ngoài ý muốn.

Một lựa chọn là optimistic locking bằng version:

~~~java
@Entity
public class OrderEntity {
    @Id
    private UUID id;

    @Version
    private long version;
}
~~~

Version giúp phát hiện một transaction ghi dựa trên trạng thái cũ. Application có thể tải lại và quyết định lại, hoặc trả conflict để caller làm mới. Không nên retry tự động một command có side effect ngoài nếu chưa có idempotency.

### Isolation không thay thế domain invariant

Dù dùng SERIALIZABLE, code vẫn cần thể hiện quy tắc như “không thể xác nhận đơn đã hủy”. Isolation điều phối tương tác giữa transaction; aggregate mô tả ý nghĩa và điều kiện nghiệp vụ.

### Isolation attribute có thể không thay đổi transaction đã tồn tại

Với propagation REQUIRED, method có thể tham gia transaction do caller mở. Isolation khai báo trên method được gọi không nhất thiết thay đổi isolation của transaction hiện có. Nếu cần bảo đảm isolation cụ thể, phải thiết kế transaction boundary và cấu hình transaction manager phù hợp, đồng thời kiểm thử với database thực tế.

## 7. Timeout và readOnly

### Timeout

Timeout giới hạn thời gian transaction được phép chạy theo hỗ trợ của transaction manager/resource. Ví dụ:

~~~java
@Transactional(timeout = 5)
public void confirmOrder(ConfirmOrder command) {
    // Đơn vị công việc cần hoàn tất trong giới hạn được chọn.
}
~~~

Timeout không phải cơ chế hủy mọi lời gọi HTTP hoặc dừng mọi thread ngay lập tức. Cần cấu hình timeout riêng cho HTTP client, JDBC statement, broker và các resource khác. Một transaction timeout có thể đánh dấu transaction rollback-only hoặc làm thao tác persistence thất bại tùy provider.

Đặt timeout dựa trên latency mục tiêu và tải thực tế. Transaction ngắn trong database thường nên có giới hạn rõ; không nên dùng timeout dài để che giấu một use case đang chờ dịch vụ ngoài.

### readOnly

Với query use case, có thể dùng:

~~~java
@Transactional(readOnly = true)
public Optional<OrderDetailsView> handle(GetOrderDetails query) {
    return orderQueries.findDetails(query.orderId());
}
~~~

`readOnly = true` là một gợi ý/hint cho transaction manager và persistence provider. Nó có thể giúp tối ưu flush behavior hoặc cách làm việc với database, nhưng không phải một cơ chế bảo mật đảm bảo không thể ghi. Một số provider có thể bỏ qua hoặc diễn giải khác nhau.

Nếu query phải không thay đổi trạng thái nghiệp vụ, hãy bảo đảm bằng thiết kế: query port chỉ đọc, không gọi hành vi mutation và không gọi repository ghi. Đừng dựa riêng vào readOnly để bảo vệ invariant.

### Có cần transaction cho mọi query?

Không nhất thiết. Query đơn giản có thể chạy qua repository với transaction do Spring Data quản lý hoặc không cần một transaction rộng ở application. Dùng read-only transaction khi cần một snapshot đọc nhất quán qua nhiều truy vấn, lazy loading trong phạm vi rõ hoặc tối ưu persistence phù hợp. Tránh mở transaction chỉ theo thói quen nếu không có nhu cầu.

## 8. Transaction boundary khi use case gọi nhiều repository

Giả sử use case chuyển tiền nội bộ cần giảm số dư tài khoản nguồn và tăng số dư tài khoản đích. Cả hai thay đổi phải cùng commit:

~~~java
@Service
public class TransferMoneyHandler {
    private final AccountRepository accounts;

    @Transactional
    public void handle(TransferMoney command) {
        Account source = accounts.findById(command.sourceId())
            .orElseThrow(SourceAccountNotFoundException::new);
        Account target = accounts.findById(command.targetId())
            .orElseThrow(TargetAccountNotFoundException::new);

        source.debit(command.amount());
        target.credit(command.amount());

        accounts.save(source);
        accounts.save(target);
    }
}
~~~

Ví dụ giả định hai account thuộc cùng bounded context và được lưu trong cùng transaction manager/database. Domain object cần kiểm tra tiền tệ, số dư, trạng thái tài khoản và các invariant liên quan.

Nếu chỉ source commit còn target rollback, tiền có thể biến mất. Transaction boundary phải bao trùm cả hai cập nhật. Đồng thời, cần concurrency control để hai transfer cạnh tranh không tạo số dư âm ngoài chính sách.

### Một transaction có nên bao trùm nhiều aggregate?

DDD thường khuyến nghị giữ aggregate nhỏ và bảo vệ invariant bên trong aggregate. Điều đó không cấm một use case cập nhật nhiều aggregate trong cùng transaction cục bộ khi nghiệp vụ thực sự cần. Nhưng nếu các aggregate thường xuyên phải cập nhật nguyên tử với nhau, hãy xem lại consistency boundary và quyền sở hữu invariant.

Không nên biến mọi thao tác liên quan thành một transaction lớn. Transaction quá rộng làm tăng lock contention, thời gian giữ connection và coupling giữa các phần của mô hình.

## 9. Transactional Outbox: ghi thay đổi và thông điệp cùng nhau

Nếu use case cần công bố Integration Event sau khi commit, không nên gọi broker trực tiếp giữa transaction database:

~~~java
@Transactional
public void confirm(ConfirmOrder command) {
    Order order = orders.get(command.orderId());
    order.confirm(clock.instant());
    orders.save(order);
    broker.publish(new OrderConfirmedMessage(order.id())); // Rủi ro dual write
}
~~~

Nếu broker nhận message nhưng database rollback, consumer có thể xử lý một sự thật chưa commit. Nếu database commit nhưng broker lỗi, thông điệp bị mất.

Transactional Outbox ghi Integration Event vào cùng database transaction:

~~~java
@Transactional
public void confirm(ConfirmOrder command) {
    Order order = orders.get(command.orderId());
    order.confirm(clock.instant());
    orders.save(order);

    List<IntegrationEvent> events =
        translator.translate(order.pullDomainEvents());
    outbox.append(events);
}
~~~

Publisher riêng đọc outbox sau commit và gửi broker. Nếu gửi lỗi, publisher retry. Message có thể được giao lặp nên consumer cần Inbox/deduplication và idempotency.

### @TransactionalEventListener không thay thế Outbox

Spring có thể gọi listener ở phase AFTER_COMMIT:

~~~java
@Component
public class OrderNotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        // Xử lý sau khi transaction đã commit.
    }
}
~~~

Điều này giúp listener chỉ chạy sau commit theo lifecycle của Spring transaction. Nhưng nếu tiến trình dừng ngay sau commit trước khi listener hoàn tất, event trong bộ nhớ có thể không được xử lý bền vững. AFTER_COMMIT không tự cung cấp durable delivery. Với thông điệp tích hợp quan trọng, hãy ghi outbox trong transaction và publish bằng worker bền vững.

### Tránh ghi outbox trong REQUIRES_NEW nếu phải cùng commit

Nếu outbox ghi trong transaction độc lập, nó có thể commit dù aggregate transaction rollback. Điều đó phá vỡ mục tiêu dual-write consistency. Aggregate và outbox phải tham gia cùng transaction vật lý nếu yêu cầu là cùng commit hoặc rollback.

## 10. Không giữ transaction mở khi gọi hệ thống bên ngoài

Một use case có thể cần gọi payment provider, shipping API hoặc dịch vụ định danh. Lời gọi mạng có độ trễ và có thể timeout. Giữ transaction database mở trong lúc chờ làm tăng thời gian giữ connection/lock và có thể làm cạn pool.

### Tách bước chuẩn bị và bước tích hợp

Một luồng thường phù hợp:

1. Trong transaction cục bộ, lưu trạng thái yêu cầu đang chờ và outbox command/event.
2. Commit transaction.
3. Worker gọi hệ thống bên ngoài.
4. Khi nhận kết quả, mở transaction mới để cập nhật aggregate và ghi outbox event tiếp theo.
5. Nếu lỗi, retry hoặc chuyển trạng thái cần xử lý.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant DB as Database + Outbox
    participant Worker
    participant Provider as External Provider
    App->>DB: Save PaymentPending + Outbox
    DB-->>App: Commit
    Worker->>DB: Read pending outbox
    Worker->>Provider: Authorize payment
    Provider-->>Worker: Result / timeout
    Worker->>DB: Save result in a new transaction
    DB-->>Worker: Commit
~~~

Nếu provider timeout, kết quả có thể không xác định. Dùng idempotency key ổn định và khả năng tra cứu theo operation reference. Không coi timeout là bằng chứng giao dịch thất bại.

### Saga cho quy trình nhiều context

Nếu quy trình đi qua Tồn kho, Thanh toán và Vận chuyển, mỗi context nên commit transaction cục bộ. Process Manager/Saga theo dõi trạng thái, gửi command tiếp theo và chạy compensation khi cần. Không dùng một transaction database dài để cố giữ nhiều dịch vụ bên ngoài trong cùng một đơn vị ACID.

## 11. Transaction và asynchronous execution

Transaction Spring truyền thống thường gắn với thread hiện tại. Khi code khởi chạy tác vụ bất đồng bộ, thread mới không tự động tham gia transaction của thread gọi.

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    orders.save(Order.place(command));
    executor.execute(() -> sendConfirmationEmail());
}
~~~

Tác vụ trong executor có thể chạy trước khi transaction commit hoặc chạy dù transaction sau đó rollback. Nó cũng không tự dùng persistence context/transaction của thread gốc.

### Không dùng @Async như một cách kéo dài transaction

Nếu cần công việc sau commit, có thể dùng AFTER_COMMIT listener cho tác vụ best-effort hoặc outbox cho công việc cần giao nhận bền vững. Worker mở transaction riêng khi cập nhật dữ liệu.

~~~java
@Service
public class OrderProjectionWorker {
    @Transactional
    public void apply(OrderConfirmed event) {
        // Transaction riêng của worker.
    }
}
~~~

Nếu dùng reactive stack, transaction context được truyền qua Reactor Context thay vì giả định thread-bound như imperative Spring. Cần dùng reactive transaction manager và API reactive phù hợp; không trộn imperative @Transactional với reactive chain một cách tùy tiện.

## 12. Transaction boundary cho Query và Command

Command use case thường cần transaction ghi:

~~~java
@Transactional
public ConfirmOrderResult handle(ConfirmOrder command) {
    // Load aggregate, call behavior, save and append outbox.
}
~~~

Query use case có thể dùng read-only transaction:

~~~java
@Transactional(readOnly = true)
public OrderDetailsView handle(GetOrderDetails query) {
    return queries.findDetails(query.orderId())
        .orElseThrow(OrderNotFoundException::new);
}
~~~

Không nên đặt một transaction ghi rộng ở controller cho tất cả endpoint. Controller là adapter giao thức; application handler sở hữu use case. Việc tách rõ cũng giúp message consumer, scheduler hoặc CLI gọi cùng use case với cùng transaction policy.

### Read-only không đồng nghĩa consistency tuyệt đối

Một read-only transaction vẫn phụ thuộc isolation level và database. Nếu query chạy nhiều câu SQL dưới READ_COMMITTED, kết quả từng câu có thể nhìn thấy các commit khác nhau. Nếu cần một snapshot nhất quán, chọn isolation phù hợp và kiểm thử với database đang dùng.

### Đừng dùng transaction để che giấu query kém hiệu quả

Transaction không tự ngăn N+1 query, không tự làm projection nhanh hơn và không tự tải association đúng cách. Hãy tối ưu query/fetch plan riêng và giữ transaction đủ ngắn.

## 13. Các lỗi thường gặp khi đặt @Transactional

- **Đặt annotation ở controller:** transaction bị gắn với giao thức thay vì use case, dễ bao trùm serialization hoặc xử lý không cần thiết.
- **Đặt trên mọi repository method:** các bước có thể commit riêng thay vì cùng transaction của use case.
- **Đặt trên domain entity:** domain model phụ thuộc framework và transaction boundary không rõ.
- **Self-invocation:** gọi nội bộ khiến proxy không áp dụng annotation ở method được gọi.
- **Tạo object bằng new:** object không được Spring proxy quản lý nên annotation không được áp dụng.
- **Nuốt RuntimeException:** method có thể kết thúc bình thường và transaction có thể commit nếu chưa rollback-only.
- **Dùng checked exception mà quên rollbackFor:** transaction có thể commit theo mặc định.
- **REQUIRES_NEW tùy tiện:** dữ liệu phụ có thể commit dù dữ liệu chính rollback.
- **NESTED không được hỗ trợ:** giả định savepoint hoạt động nhưng transaction manager/provider không hỗ trợ như mong muốn.
- **Gọi HTTP trong transaction dài:** giữ connection/lock trong lúc chờ mạng.
- **Publish broker trực tiếp trước commit:** tạo dual-write inconsistency.
- **Cho rằng AFTER_COMMIT bảo đảm durable delivery:** process có thể dừng trước khi listener hoàn tất.
- **Dùng readOnly như hàng rào bảo mật:** provider có thể coi đó là hint và vẫn cho phép ghi.
- **Bắt đầu async rồi giả định transaction được truyền sang thread mới:** tác vụ chạy ngoài transaction gốc.
- **Không kiểm tra commit-time exception:** lỗi constraint/flush có thể chỉ xuất hiện khi flush hoặc commit.

## 14. Kiểm thử transaction đúng cách

Unit test cho handler có thể kiểm tra orchestration, nhưng không chứng minh Spring proxy và transaction manager thực sự commit/rollback như mong muốn. Cần integration test cho các quy tắc transaction quan trọng.

### Kiểm thử rollback

Một test có thể:

1. Gọi use case qua Spring bean được inject.
2. Làm cho bước sau khi lưu aggregate ném RuntimeException.
3. Đọc lại dữ liệu trong transaction/test context phù hợp.
4. Xác nhận thay đổi aggregate và outbox đều không tồn tại.

Chú ý: test framework có thể tự mở transaction cho test method và rollback khi kết thúc. Điều đó có thể che giấu việc transaction của service đã commit. Cần kiểm soát transaction của test, flush/clear persistence context và đọc lại từ transaction/connection phù hợp để xác minh hành vi thật.

### Kiểm thử propagation

- REQUIRED tham gia transaction ngoài.
- REQUIRES_NEW commit độc lập trong trường hợp được thiết kế.
- NESTED rollback về savepoint nếu transaction manager hỗ trợ.
- MANDATORY từ chối khi không có transaction.
- Self-invocation không áp dụng propagation riêng như lời gọi qua proxy.

### Kiểm thử rollback rules

- RuntimeException làm rollback theo mặc định.
- Checked exception được kiểm tra theo rollbackFor đã cấu hình.
- noRollbackFor chỉ commit khi đúng chính sách.
- Exception bị catch/nuốt không vô tình làm use case báo thành công.

### Kiểm thử outbox

- Aggregate và outbox commit cùng nhau.
- Nếu append outbox lỗi, aggregate rollback.
- Nếu transaction rollback, không có outbox message được publish.
- Publisher retry được sau lỗi broker.
- Consumer idempotent khi message giao lặp.

### Kiểm thử concurrency và isolation

Dùng database engine phù hợp với production khi test các hành vi lock, isolation và optimistic locking quan trọng. In-memory database có thể có semantics khác và không phát hiện một số vấn đề thực tế.

## 15. Quy trình chọn transaction boundary cho use case

Khi triển khai một use case mới, hãy làm theo trình tự:

1. **Viết mục tiêu use case:** actor muốn đạt kết quả gì?
2. **Liệt kê invariant:** điều gì không được phép sai khi thao tác hoàn tất?
3. **Xác định dữ liệu cùng commit:** aggregate, bảng liên quan và outbox nào phải nằm trong một transaction?
4. **Đặt boundary ở application handler:** method nào được gọi qua Spring proxy và đại diện cho đơn vị công việc?
5. **Chọn propagation:** thường REQUIRED; dùng chế độ khác chỉ khi có lý do rõ.
6. **Chọn rollback rules:** checked exception nào phải rollback, lỗi nào là kết quả nghiệp vụ có thể commit?
7. **Chọn isolation/concurrency control:** optimistic/pessimistic lock hoặc constraint nào bảo vệ invariant?
8. **Đặt timeout:** transaction có thể giữ resource trong bao lâu?
9. **Xác định read-only path:** query có cần transaction và snapshot đọc nhất quán không?
10. **Tách external I/O:** HTTP/broker/email có thể thực hiện sau commit bằng outbox/worker không?
11. **Xác định async semantics:** tác vụ mới có transaction riêng và idempotency không?
12. **Kiểm thử:** rollback, propagation, self-invocation, outbox và concurrency.

## Checklist rà soát

- [ ] Transaction boundary đại diện cho một use case hoặc đơn vị công việc rõ ràng.
- [ ] Invariant cần bảo vệ được xác định trước khi chọn transaction.
- [ ] @Transactional đặt ở application/use-case boundary phù hợp.
- [ ] Method được gọi qua Spring bean proxy.
- [ ] Không dựa vào self-invocation để kích hoạt propagation hoặc isolation riêng.
- [ ] Domain model không phụ thuộc Spring transaction.
- [ ] REQUIRED được dùng làm mặc định khi phù hợp.
- [ ] REQUIRES_NEW/NESTED có lý do và đã đánh giá hệ quả.
- [ ] Rollback rules cho checked exception được xác định rõ.
- [ ] Exception không bị nuốt làm transaction commit ngoài ý muốn.
- [ ] Isolation/concurrency control phù hợp invariant và database thật.
- [ ] Timeout và readOnly được hiểu đúng là chính sách/hint theo provider.
- [ ] Aggregate và outbox cùng transaction nếu cần atomic commit.
- [ ] Không gọi hệ thống ngoài trong transaction dài.
- [ ] Async worker mở transaction riêng và xử lý idempotent.
- [ ] Có integration test xác minh rollback, propagation và commit thực tế.

## Kết luận

Đặt `@Transactional` theo ranh giới use case giúp transaction phản ánh đơn vị công việc mà nghiệp vụ cần commit hoặc rollback cùng nhau. Application Service điều phối transaction; aggregate bảo vệ invariant; repository lưu trạng thái; outbox ghi thông điệp cần công bố trong cùng transaction. Để cấu hình hoạt động đúng, cần hiểu Spring proxy và self-invocation, propagation, rollback rules, isolation, timeout và readOnly. Các lời gọi hệ thống ngoài và tác vụ bất đồng bộ thường cần chạy sau commit trong transaction riêng, với outbox, retry và idempotency khi cần. Ranh giới tốt được chọn từ invariant và hậu quả nghiệp vụ, sau đó mới thể hiện bằng annotation và cấu hình Spring.
