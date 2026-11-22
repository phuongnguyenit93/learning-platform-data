# Exception và rollback trong Spring for GraphQL

Trong Spring for GraphQL, một GraphQL error và một database rollback là hai việc khác nhau. GraphQL quyết định response có `data`, `errors` hay partial data; Spring transaction management quyết định các thay đổi database trong một transaction được commit hay rollback. Một mutation có thể trả GraphQL error nhưng dữ liệu vẫn đã commit nếu exception bị bắt trước khi transaction interceptor nhìn thấy nó. Ngược lại, một transaction có thể rollback dù GraphQL framework sau đó chuyển exception thành response error bình thường.

Muốn xử lý đúng, cần đặt transaction boundary quanh use case nghiệp vụ, hiểu rollback rules của `@Transactional`, rồi để exception đi qua transaction interceptor trước khi ánh xạ nó thành GraphQL error. Với mutation cần nhiều thao tác cùng thành công hoặc cùng thất bại, hãy điều phối các thao tác trong một service method có transaction rõ ràng.

## 1. GraphQL error không tự động có nghĩa là rollback

GraphQL response có thể chứa cả dữ liệu và lỗi:

~~~json
{
    "data": {
        "createOrder": {
            "id": "order-101",
            "status": "PENDING",
            "payment": null
        }
    },
    "errors": [
        {
            "message": "Payment provider is unavailable",
            "path": ["createOrder", "payment"]
        }
    ]
}
~~~

Response trên chỉ nói rằng một field gặp lỗi khi GraphQL execution. Nó không cho biết thao tác tạo order đã commit hay rollback. Nếu `createOrder` đã kết thúc transaction và commit trước khi field `payment` được resolve, lỗi ở `payment` không thể tự động rollback transaction đã hoàn tất.

Phân biệt hai lớp:

| Lớp | Câu hỏi | Cơ chế quyết định |
| --- | --- | --- |
| GraphQL execution | Field nào thành công, field nào lỗi, response có partial data không? | GraphQL execution engine và exception resolver |
| Database transaction | Các lệnh ghi dữ liệu có commit hay rollback? | Spring transaction manager và rollback rules |

Không suy luận trạng thái database chỉ từ HTTP status hoặc sự hiện diện của `errors`. GraphQL thường có thể trả HTTP `200` cùng `errors`; điều đó không nói transaction đã commit hay rollback.

## 2. Transaction boundary nằm ở use case nghiệp vụ

Một luồng mutation thường gồm:

~~~mermaid
flowchart TD
    A[GraphQL Mutation request] --> B[Mutation resolver]
    B --> C[Transactional application service]
    C --> D[Repository và domain services]
    D --> E{Có exception thoát khỏi transaction?}
    E -->|Không| F[Commit]
    E -->|Có và rollback rule khớp| G[Rollback]
    E -->|Có nhưng không rollback rule| F
    F --> H[Trả kết quả cho GraphQL]
    G --> I[Exception resolver ánh xạ GraphQL error]
    F --> J[GraphQL tiếp tục resolve response fields]
    I --> K[GraphQL response]
    J --> K
~~~

`@Transactional` tạo transaction quanh lời gọi method đi qua Spring proxy. Khi method kết thúc bình thường, transaction được commit. Khi exception thoát khỏi method, transaction interceptor so sánh exception với rollback rules để quyết định rollback hay commit.

Vì vậy, transaction boundary nên đặt quanh một nghiệp vụ hoàn chỉnh, thường ở application service. Resolver chỉ bind GraphQL arguments, lấy thông tin principal/context cần thiết, gọi service và trả kết quả.

## 3. Khai báo mutation và application service

Ví dụ nghiệp vụ tạo đơn hàng cần lưu order và giữ chỗ tồn kho. Hai thao tác phải cùng thành công hoặc cùng thất bại.

SDL:

~~~graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}

input CreateOrderInput {
    productId: ID!
    quantity: Int!
}

type Order {
    id: ID!
    productId: ID!
    quantity: Int!
    status: OrderStatus!
}

enum OrderStatus {
    PENDING
    CONFIRMED
    CANCELLED
}
~~~

Command và exception nghiệp vụ:

~~~java
public record CreateOrderInput(String productId, Integer quantity) {}

public record CreateOrderCommand(
        Long productId,
        int quantity,
        String customerId
) {}
~~~

~~~java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(Long orderId) {
        super("Order " + orderId + " was not found");
    }
}
~~~

~~~java
public class InsufficientInventoryException extends RuntimeException {
    public InsufficientInventoryException(Long productId) {
        super("Insufficient inventory for product " + productId);
    }
}
~~~

Ví dụ repository giữ chỗ tồn kho bằng một câu update có điều kiện:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {

    @Modifying
    @Query("""
            update Inventory i
               set i.availableQuantity = i.availableQuantity - :quantity
             where i.productId = :productId
               and i.availableQuantity >= :quantity
            """)
    int reserveIfAvailable(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        int updated = inventoryRepository.reserveIfAvailable(productId, quantity);
        if (updated == 0) {
            throw new InsufficientInventoryException(productId);
        }
    }
}
~~~

Điều kiện `availableQuantity >= quantity` nằm ngay trong câu update, giúp tránh kiểu đọc số lượng trước rồi cập nhật sau khiến hai request đồng thời cùng nhìn thấy một lượng tồn kho cũ. Method này tham gia transaction đang có nhờ propagation `REQUIRED`.

Service điều phối nghiệp vụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    public OrderApplicationService(
            OrderRepository orderRepository,
            InventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        if (command.quantity() < 1) {
            throw new InvalidOrderException("quantity must be positive");
        }

        Order order = orderRepository.save(Order.pending(
                command.customerId(),
                command.productId(),
                command.quantity()
        ));

        inventoryService.reserve(command.productId(), command.quantity());

        return order;
    }
}
~~~

Nếu `inventoryService.reserve(...)` ném `InsufficientInventoryException`, exception thoát khỏi `createOrder`. Vì đây là `RuntimeException`, transaction mặc định rollback; việc insert order và cập nhật tồn kho trong cùng transaction bị hoàn tác.

Để hai repository/service tham gia cùng transaction, chúng phải dùng cùng transaction manager và cùng resource transaction (ví dụ cùng `DataSource`/JPA `EntityManagerFactory`). Với propagation mặc định `REQUIRED`, method transactional được gọi bên trong transaction hiện tại sẽ tham gia transaction đó.

Resolver:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final OrderApplicationService orderService;
    private final CurrentCustomerProvider customerProvider;

    public OrderMutationController(
            OrderApplicationService orderService,
            CurrentCustomerProvider customerProvider
    ) {
        this.orderService = orderService;
        this.customerProvider = customerProvider;
    }

    @MutationMapping
    public Order createOrder(@Argument CreateOrderInput input) {
        Long productId;
        try {
            productId = Long.valueOf(input.productId());
        }
        catch (NumberFormatException exception) {
            throw new InvalidOrderException("productId must be a numeric identifier");
        }

        CreateOrderCommand command = new CreateOrderCommand(
                productId,
                input.quantity(),
                customerProvider.currentCustomerId()
        );
        return orderService.createOrder(command);
    }
}
~~~

Customer ID được lấy từ principal phía server, không nhận từ input của client nếu nghiệp vụ yêu cầu customer chỉ được tạo đơn cho chính mình. GraphQL `ID` được bind thành `String`, sau đó resolver chuyển sang ID kiểu `Long` của domain.

## 4. Rollback rules mặc định của @Transactional

Với cấu hình Spring transaction mặc định, transaction rollback khi method kết thúc bằng:

- `RuntimeException` hoặc subclass của nó.
- `Error` hoặc subclass của nó.

Checked exception (ví dụ `IOException`) mặc định không kích hoạt rollback. Nếu checked exception thể hiện nghiệp vụ thất bại và cần hoàn tác database, phải khai báo `rollbackFor`.

| Loại kết thúc method | Mặc định | Cấu hình thường dùng |
| --- | --- | --- |
| `RuntimeException` thoát khỏi method | Rollback | Không cần thêm rule |
| `Error` thoát khỏi method | Rollback | Không cần thêm rule |
| Checked exception thoát khỏi method | Commit theo mặc định | `rollbackFor = ...` nếu cần rollback |
| Method trả về bình thường | Commit | Đánh dấu rollback-only nếu nghiệp vụ cần hủy |
| Exception bị catch và không ném lại | Commit theo mặc định | Ném lại exception hoặc đánh dấu rollback-only |

Ví dụ checked exception:

~~~java
public class CreditCheckException extends Exception {
    public CreditCheckException(String message) {
        super(message);
    }
}
~~~

~~~java
@Transactional(rollbackFor = CreditCheckException.class)
public Order approveOrder(Long orderId) throws CreditCheckException {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markApproved();
    creditService.verify(order.getCustomerId());
    return order;
}
~~~

Nếu `creditService.verify(...)` ném `CreditCheckException`, transaction rollback vì rule `rollbackFor` khớp với exception.

Không nên thêm `rollbackFor = Exception.class` theo thói quen cho mọi method. Hãy xác định loại exception nào biểu thị nghiệp vụ cần hoàn tác; một số checked exception có thể là kết quả có thể xử lý mà vẫn cho phép commit.

## 5. rollbackFor và noRollbackFor

`rollbackFor` bổ sung rollback rule cho exception cụ thể. `noRollbackFor` chỉ định exception không làm transaction rollback dù nó thuộc nhóm unchecked.

~~~java
@Transactional(rollbackFor = CreditCheckException.class)
public Order submitOrder(CreateOrderCommand command)
        throws CreditCheckException {
    // Persist order, reserve stock and perform credit check.
    return doSubmit(command);
}
~~~

Ví dụ không rollback với một exception mang ý nghĩa cảnh báo:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public Notification recordNotification(NotificationCommand command) {
    Notification notification = notificationRepository.save(
            Notification.pending(command)
    );
    notificationPolicy.checkDuplicate(command);
    return notification;
}
~~~

Chỉ dùng `noRollbackFor` khi việc commit dù exception xảy ra là chủ đích nghiệp vụ. Nếu exception có nghĩa thao tác chính thất bại, bỏ qua rollback có thể để lại trạng thái dở dang.

Khi exception thuộc `noRollbackFor` thoát khỏi service, GraphQL vẫn có thể nhận exception và trả `errors`, trong khi database transaction đã commit. Đây là ví dụ rõ ràng cho thấy GraphQL error không chứng minh transaction rollback.

Khi nhiều rule cùng khớp, Spring chọn rule có mức khớp cụ thể nhất với exception thực tế. Tránh khai báo các rule mâu thuẫn rộng như `rollbackFor = Exception.class` cùng `noRollbackFor = RuntimeException.class` nếu không có lý do rõ ràng.

## 6. Catch exception có thể làm transaction commit

Đây là lỗi phổ biến:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));

    try {
        int updated = inventoryRepository.reserveIfAvailable(
                command.productId(), command.quantity());
        if (updated == 0) {
            throw new InsufficientInventoryException(command.productId());
        }
    }
    catch (InsufficientInventoryException exception) {
        // Chỉ log và tiếp tục trả kết quả bình thường.
        log.warn("Cannot reserve inventory", exception);
    }

    return order;
}
~~~

Trong ví dụ này, exception được tạo và catch ngay bên trong cùng transactional method; nó không đi qua transaction proxy như một exception thoát khỏi method. Method kết thúc bình thường nên transaction interceptor commit, và order có thể được lưu dù tồn kho chưa được giữ.

Lưu ý: nếu exception đến từ một bean khác có `@Transactional(REQUIRED)` và đã thoát khỏi proxy của bean đó, transaction tham gia có thể đã bị đánh dấu rollback-only. Khi outer method catch exception rồi trả về, transaction vẫn rollback và có thể ném `UnexpectedRollbackException` lúc commit. Tình huống này được giải thích ở phần propagation.

Nếu nghiệp vụ yêu cầu hủy toàn bộ thao tác, cách rõ ràng nhất là ném lại exception:

~~~java
catch (InsufficientInventoryException exception) {
    throw exception;
}
~~~

Nếu cần catch để thực hiện xử lý bổ sung nhưng vẫn rollback, có thể đánh dấu transaction rollback-only:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

catch (InsufficientInventoryException exception) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    return Order.rejected(command);
}
~~~

Sau khi đánh dấu rollback-only, transaction sẽ rollback khi kết thúc dù method trả về bình thường. Tuy nhiên, response trả về `Order.rejected(...)` không tự mô tả được rằng dữ liệu đã rollback; hãy thiết kế response và trạng thái nghiệp vụ nhất quán. Nếu không cần trả kết quả đặc biệt, ném exception thường dễ hiểu hơn.

## 7. Ánh xạ exception thành GraphQL error

Exception resolver chuyển exception đã thoát khỏi resolver/service thành GraphQL error. Việc ánh xạ diễn ra sau khi lời gọi transactional service đã đi qua transaction interceptor.

Ví dụ `@ControllerAdvice`:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class OrderGraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleInsufficientInventory(
            InsufficientInventoryException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("The requested quantity is not available")
                .extensions(Map.of("code", "INSUFFICIENT_INVENTORY"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleOrderNotFound(
            OrderNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Order was not found")
                .extensions(Map.of("code", "ORDER_NOT_FOUND"))
                .build();
    }
}
~~~

`ErrorType.BAD_REQUEST` và `ErrorType.NOT_FOUND` mô tả lỗi phía client/nghiệp vụ. Với lỗi bất ngờ, để lỗi được xử lý theo chính sách internal error của ứng dụng; không trả stack trace, SQL, connection string hoặc exception message nhạy cảm cho client.

Trình tự quan trọng:

1. Resolver gọi `orderService.createOrder(...)` qua Spring proxy.
2. Transaction interceptor bắt đầu transaction.
3. Service ném `InsufficientInventoryException`.
4. Transaction interceptor rollback vì đây là `RuntimeException`.
5. Exception được ném tiếp ra GraphQL execution.
6. `@GraphQlExceptionHandler` ánh xạ exception thành GraphQL error.

Exception handler không nên là nơi quyết định rollback của transaction nghiệp vụ. Khi handler nhận exception, transaction của service đã kết thúc theo rollback rules.

## 8. Transaction propagation

Propagation quyết định một method transactional tham gia transaction hiện có hay tạo transaction khác.

| Propagation | Hành vi | Trường hợp dùng |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Mặc định, phù hợp phần lớn use case |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và tạo transaction mới | Ghi audit độc lập cần commit dù transaction ngoài rollback |
| `SUPPORTS` | Tham gia nếu có; nếu không thì chạy không transaction | Đọc có thể chạy trong hoặc ngoài transaction |
| `MANDATORY` | Bắt buộc phải có transaction hiện tại | Hàm nội bộ chỉ được gọi trong use case đã mở transaction |
| `NOT_SUPPORTED` | Tạm dừng transaction hiện tại và chạy không transaction | Công việc không nên giữ transaction mở |
| `NEVER` | Báo lỗi nếu đang có transaction | Bảo đảm một operation không chạy trong transaction |
| `NESTED` | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Rollback một phần trong transaction ngoài, khi resource hỗ trợ |

`REQUIRED` là lựa chọn mặc định nên ưu tiên. Ví dụ `OrderApplicationService` gọi `InventoryService` có `@Transactional(REQUIRED)`: cả hai cùng tham gia một transaction. Nếu reserve tồn kho thất bại và exception thoát khỏi transaction ngoài, cả order và thay đổi inventory được rollback.

## 9. REQUIRES_NEW và dữ liệu độc lập

`REQUIRES_NEW` tạo transaction độc lập. Transaction ngoài bị suspend trong lúc transaction mới chạy.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String action, String reference) {
        auditRepository.save(AuditEntry.of(action, reference));
    }
}
~~~

Nếu transaction tạo order rollback, audit record vẫn có thể commit vì nó thuộc transaction riêng. Đây là hành vi có chủ đích nhưng cũng là rủi ro: không dùng `REQUIRES_NEW` cho dữ liệu phải rollback cùng nghiệp vụ chính.

`REQUIRES_NEW` thường cần thêm database connection trong lúc transaction ngoài vẫn đang giữ connection. Dưới tải cao, connection pool quá nhỏ có thể gây chờ hoặc cạn connection. Hãy cân nhắc chi phí và tránh lạm dụng.

## 10. NESTED và savepoint

`Propagation.NESTED` có thể tạo savepoint trong transaction hiện tại. Nếu nested operation thất bại và rollback về savepoint, transaction ngoài có thể tiếp tục.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void updateOptionalMetadata(Long orderId) {
    metadataRepository.updateForOrder(orderId);
}
~~~

Hỗ trợ `NESTED` phụ thuộc transaction manager và resource. JDBC transaction manager có thể hỗ trợ savepoint; JPA transaction manager không cung cấp nested transaction theo cách portable cho mọi persistence provider. Không mặc định rằng `NESTED` hoạt động giống nhau với mọi cấu hình. Kiểm tra transaction manager đang dùng và viết integration test cho semantics cần thiết.

Nếu không cần savepoint, giữ `REQUIRED` và để lỗi lan ra transaction boundary thường đơn giản hơn.

## 11. UnexpectedRollbackException

Một method tham gia transaction hiện tại bằng `REQUIRED` có thể đánh dấu transaction rollback-only. Nếu method ngoài bắt exception và tiếp tục chạy như thể mọi việc thành công, lúc transaction ngoài cố commit, Spring sẽ ném `UnexpectedRollbackException` vì transaction đã bị đánh dấu rollback-only.

Ví dụ luồng:

~~~java
@Transactional
public void placeOrder() {
    try {
        inventoryService.reserveOrFail(); // REQUIRED, tham gia transaction này
    }
    catch (InventoryException exception) {
        log.warn("Reservation failed; continuing", exception);
    }

    orderRepository.save(Order.pending());
}
~~~

Nếu `reserveOrFail()` làm transaction rollback-only trước khi exception được catch, outer method không thể biến transaction đó trở lại trạng thái commit. Kết quả là toàn bộ transaction rollback và lời gọi ngoài có thể nhận `UnexpectedRollbackException`.

Khi lỗi là điều kiện khiến nghiệp vụ thất bại, hãy để exception thoát ra. Nếu cần một transaction độc lập cho phần xử lý phụ, cân nhắc `REQUIRES_NEW` với hiểu biết rõ dữ liệu nào được phép commit độc lập.

## 12. Self-invocation có thể bỏ qua @Transactional

Spring thường áp dụng `@Transactional` thông qua proxy. Một method trong cùng object gọi trực tiếp method khác của chính object đó sẽ không đi qua proxy, vì vậy annotation ở method được gọi có thể không được áp dụng.

~~~java
@Service
public class OrderService {

    public void importOrders() {
        this.saveOneOrder(); // self-invocation, không đi qua transaction proxy
    }

    @Transactional
    public void saveOneOrder() {
        // Không thể giả định lời gọi này mở transaction riêng.
    }
}
~~~

Đặt transaction ở public application service method được gọi từ bean khác, hoặc tách use case thành bean riêng. Tránh tự inject proxy của chính class chỉ để gọi lại method.

`@Transactional` cũng cần được đặt trên method/class được Spring quản lý. Tạo object bằng `new` thay vì dependency injection sẽ bỏ qua proxy. Với proxy-based transaction management, chỉ lời gọi đi qua proxy mới được intercept.

## 13. readOnly, isolation và timeout

`@Transactional` còn cho phép cấu hình các thuộc tính transaction:

~~~java
@Transactional(readOnly = true)
public Order findOrder(Long id) {
    return orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}

@Transactional(timeout = 5)
public Order updateOrder(Long id, UpdateOrderCommand command) {
    // Update within a bounded transaction timeout.
    return doUpdate(id, command);
}
~~~

- `readOnly = true` là hint cho transaction manager/provider; không nên xem nó như cơ chế authorization hoặc bảo đảm tuyệt đối rằng không thể ghi.
- `isolation` điều khiển mức cô lập khi transaction manager và database hỗ trợ; chọn theo anomaly cần ngăn chặn, không tăng isolation một cách tùy tiện.
- `timeout` giới hạn thời gian transaction theo khả năng của transaction manager/resource. Nó không thay thế timeout riêng cho HTTP client hoặc downstream service.

Với GraphQL query chỉ đọc, có thể dùng read-only transaction trong service nếu cần bảo đảm một nhóm thao tác đọc chạy trong cùng transaction. Không mở transaction dài quanh toàn bộ GraphQL request nếu response còn resolve nhiều field bất đồng bộ.

## 14. Mutation có nhiều root fields không tự động là một transaction

GraphQL thực thi các top-level mutation fields theo thứ tự tuần tự. Tuy nhiên, điều đó không có nghĩa toàn bộ mutation operation được bao bởi một database transaction duy nhất.

Ví dụ:

~~~graphql
mutation {
    createOrder(input: { productId: "10", quantity: 2 }) {
        id
    }
    updateCustomer(id: "customer-1", name: "New name") {
        id
    }
}
~~~

Nếu `createOrder` và `updateCustomer` gọi hai service method có `@Transactional` riêng, mỗi method có thể commit độc lập. Nếu field thứ hai thất bại, transaction của field thứ nhất đã commit thì không tự động rollback.

Nếu yêu cầu nghiệp vụ là cả hai thay đổi phải atomic, hãy tạo một mutation field duy nhất và một service method điều phối cả hai:

~~~graphql
type Mutation {
    checkout(input: CheckoutInput!): CheckoutResult!
}
~~~

~~~java
@Transactional
public CheckoutResult checkout(CheckoutCommand command) {
    Order order = orderService.createWithinCurrentTransaction(command.order());
    customerService.updateWithinCurrentTransaction(command.customer());
    return new CheckoutResult(order.getId());
}
~~~

Các method được gọi phải tham gia cùng transaction manager/transaction, ví dụ propagation `REQUIRED`. Đặt boundary tại use case orchestration để biểu đạt đúng tính atomic của nghiệp vụ.

## 15. Nested field resolution có thể chạy sau transaction của mutation

Resolver trả về một entity sau khi transactional service đã commit. GraphQL sau đó có thể resolve các field con như `order.customer`, `order.items` hoặc `order.payment`.

Không nên dựa vào một transaction của service đã kết thúc để giữ persistence context cho các field con. Nếu field con truy cập lazy association sau khi session đóng, ứng dụng có thể gặp `LazyInitializationException`; nếu field con gọi repository riêng, nó có transaction riêng theo service đó.

Các cách xử lý:

- Trả DTO/read model được query đầy đủ trong transaction của use case.
- Dùng projection hoặc fetch plan phù hợp cho dữ liệu cần trả.
- Dùng DataLoader/`@BatchMapping` để nạp quan hệ theo batch bằng service có transaction riêng.
- Không giữ transaction ghi mở trong lúc GraphQL resolve một cây response dài hoặc có async fields.

Transaction boundary nên bao quanh thao tác ghi nghiệp vụ; việc đọc field con nên được thiết kế riêng theo nhu cầu response và hiệu năng.

## 16. Exception handling không nên che giấu lỗi transaction

Một resolver không nên bắt mọi exception rồi trả `null`:

~~~java
@MutationMapping
public Order createOrder(@Argument CreateOrderInput input) {
    try {
        return orderService.createOrder(toCommand(input));
    }
    catch (Exception exception) {
        log.error("Create order failed", exception);
        return null;
    }
}
~~~

Nếu exception đã thoát khỏi service proxy, transaction có thể đã rollback. Nhưng việc resolver nuốt exception khiến GraphQL không nhận được error có ý nghĩa và client chỉ thấy `null`. Nếu exception bị catch bên trong transactional method, transaction thậm chí có thể commit nếu chưa được đánh dấu rollback-only.

Hãy để exception nghiệp vụ được xử lý ở `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`. Tại đó, ánh xạ lỗi có chủ đích thành `ErrorType` và message an toàn cho client.

Không dùng GraphQL `errors` để thay thế trạng thái nghiệp vụ. Nếu một thao tác hợp lệ nhưng tạo kết quả từ chối (ví dụ đơn hàng `REJECTED`), có thể trả kết quả nghiệp vụ bình thường. Nếu thao tác phải rollback vì thất bại, ném exception và ánh xạ nó thành GraphQL error.

## 17. Async execution và transaction imperative

Transaction imperative của Spring thường gắn với thread hiện tại. Nếu transactional method khởi chạy `CompletableFuture`, `@Async` hoặc chuyển việc sang executor khác, transaction context không tự động đi theo thread mới.

~~~java
@Transactional
public CompletableFuture<Order> createOrderAsync(CreateOrderCommand command) {
    return CompletableFuture.supplyAsync(() -> {
        // Không giả định transaction của method bên ngoài có mặt ở thread này.
        return orderRepository.save(Order.pending(command));
    });
}
~~~

Ví dụ trên không an toàn nếu mong đợi repository write chạy trong transaction imperative mở ở thread gọi method. Transaction có thể kết thúc trước khi future hoàn tất.

Với công việc async, hãy để tác vụ async gọi một bean service khác có transaction riêng:

~~~java
@Service
public class AsyncOrderWorker {

    private final OrderWriteService orderWriteService;

    public AsyncOrderWorker(OrderWriteService orderWriteService) {
        this.orderWriteService = orderWriteService;
    }

    @Async
    public CompletableFuture<Long> persist(CreateOrderCommand command) {
        Order order = orderWriteService.createOrder(command);
        return CompletableFuture.completedFuture(order.getId());
    }
}
~~~

`OrderWriteService.createOrder` được gọi qua bean proxy trên worker thread và tự mở transaction tại thread đó. Không dựa vào transaction của request GraphQL để bao lấy công việc đã tách thread.

## 18. Reactive transaction và Reactor context

Với reactive stack dùng R2DBC, transaction được quản lý theo reactive context thay vì thread-local imperative transaction. Dùng reactive transaction manager tương ứng và giữ công việc trong cùng Reactor chain.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final ReactiveInventoryService inventoryService;

    public ReactiveOrderService(
            ReactiveOrderRepository orderRepository,
            ReactiveInventoryService inventoryService
    ) {
        this.orderRepository = orderRepository;
        this.inventoryService = inventoryService;
    }

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        return orderRepository.save(Order.pending(command))
                .flatMap(order -> inventoryService.reserve(
                                command.productId(), command.quantity())
                        .thenReturn(order));
    }
}
~~~

Đừng gọi `.block()` bên trong reactive transaction để chuyển sang imperative flow, hoặc tách publisher sang một context không còn transaction. Cũng không trộn JPA blocking repository và R2DBC reactive repository rồi giả định chúng cùng một transaction; hai công nghệ thường dùng transaction manager và resource khác nhau.

Với reactive method trả `Mono`/`Flux`, transaction interceptor quản lý publisher khi subscription thực thi. Các lỗi được phát ra trong reactive chain có thể kích hoạt rollback theo rollback rules. Nếu dùng nhiều transaction manager, chỉ định manager phù hợp bằng `@Transactional(transactionManager = "...")`.

## 19. DataLoader và transaction boundary

DataLoader gom các field load thành batch để tránh N+1. Batch loader thường được gọi ở giai đoạn GraphQL field execution, có thể sau khi mutation service đã commit.

Không giả định DataLoader batch dùng chung transaction với mutation chỉ vì nó thuộc cùng GraphQL request. Nếu batch loader đọc dữ liệu cần transaction, hãy đặt transaction ở service mà batch loader gọi:

~~~java
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReadService {

    private final CustomerRepository customerRepository;

    public CustomerReadService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public Map<Long, Customer> findAllByIds(Set<Long> ids) {
        return customerRepository.findAllById(ids).stream()
                .collect(Collectors.toMap(Customer::getId, Function.identity()));
    }
}
~~~

Batch loader gọi `CustomerReadService` và nhận một read transaction trong phạm vi truy vấn batch. Transaction đọc này độc lập với transaction ghi trước đó.

Nếu cần đọc trạng thái vừa ghi trong cùng transaction, hãy thực hiện việc đọc đó bên trong application service trước khi trả về, hoặc thiết kế use case để không phụ thuộc vào field resolver chạy sau commit.

## 20. External side effects và transaction commit

Database rollback không thể tự hoàn tác email đã gửi, HTTP request đã gọi hoặc message đã publish sang broker ngoài transaction.

Không nên gửi email trước khi database commit:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(Order.pending(command));
    emailClient.sendOrderConfirmation(order); // Side effect có thể đã xảy ra
    inventoryService.reserve(command.productId(), command.quantity());
    return order;
}
~~~

Nếu reserve inventory thất bại, database rollback nhưng email có thể đã gửi. Dùng transaction synchronization để thực hiện side effect sau commit khi phù hợp:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderNotificationService {

    private final OrderRepository orderRepository;
    private final EmailClient emailClient;

    public OrderNotificationService(
            OrderRepository orderRepository,
            EmailClient emailClient
    ) {
        this.orderRepository = orderRepository;
        this.emailClient = emailClient;
    }

    @Transactional
    public Order createAndNotify(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.pending(command));

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        emailClient.sendOrderConfirmation(order.getId());
                    }
                }
        );

        return order;
    }
}
~~~

Callback `afterCommit` chỉ chạy khi transaction commit. Tuy vậy, nếu process dừng sau commit nhưng trước khi gửi email, callback trong bộ nhớ có thể bị mất. Với side effect cần độ tin cậy cao, dùng transactional outbox: ghi event vào bảng outbox trong cùng transaction với order, sau đó worker riêng publish event và đánh dấu đã xử lý.

Nếu callback `afterCommit` ném exception, transaction database đã commit và không thể rollback lại; exception vẫn có thể truyền về caller khiến GraphQL response có error dù dữ liệu đã được lưu. Hãy bắt/log lỗi callback và có cơ chế retry bền vững; với side effect quan trọng, outbox giúp tránh phụ thuộc vào callback trong bộ nhớ.

Spring cũng cung cấp `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để xử lý application event sau commit. Với yêu cầu giao nhận bền vững, outbox thường phù hợp hơn event listener in-memory.

## 21. Kiểm thử rollback ở service layer

Unit test mock repository có thể kiểm tra service ném exception, nhưng không chứng minh database transaction thực sự rollback. Muốn xác minh rollback, cần integration test dùng transaction manager và database tương ứng.

Ví dụ service-level integration test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.BDDMockito.willThrow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class OrderTransactionTests {

    @Autowired
    OrderApplicationService orderService;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    InventoryService inventoryService;

    @Test
    void rollsBackOrderWhenInventoryReservationFails() {
        long before = orderRepository.count();
        willThrow(new InsufficientInventoryException(10L))
                .given(inventoryService).reserve(10L, 2);

        assertThrows(InsufficientInventoryException.class, () ->
                orderService.createOrder(new CreateOrderCommand(10L, 2, "customer-1"))
        );

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

Test minh họa dùng Spring Boot test context và mock collaborator tồn kho để buộc nhánh thất bại sau khi order đã được lưu. Điều quan trọng là lời gọi `orderService.createOrder(...)` phải đi qua Spring proxy và assertion đọc database sau khi lời gọi đã kết thúc.

Không đặt `@Transactional` trên test method trong ví dụ này. Nếu test tự mở transaction bao quanh toàn bộ test, việc kiểm tra trạng thái commit/rollback của transaction bên trong có thể bị che khuất bởi transaction test. Nếu test cần transaction fixture, hãy commit fixture rõ ràng hoặc dùng `TestTransaction` để kiểm soát thời điểm commit.

## 22. Kiểm thử rollback qua GraphQlTester

Integration test qua GraphQL giúp xác minh cả exception mapping lẫn trạng thái database sau execution:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.willThrow;

@SpringBootTest
@AutoConfigureHttpGraphQlTester
class OrderMutationRollbackGraphQlTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    InventoryService inventoryService;

    @MockitoBean
    CurrentCustomerProvider customerProvider;

    @Test
    void returnsGraphQlErrorAndDoesNotPersistOrder() {
        long before = orderRepository.count();
        org.mockito.BDDMockito.given(customerProvider.currentCustomerId())
                .willReturn("customer-1");
        willThrow(new InsufficientInventoryException(10L))
                .given(inventoryService).reserve(10L, 2);

        graphQlTester.document("""
                mutation {
                    createOrder(input: { productId: "10", quantity: 2 }) {
                        id
                        status
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage().contains("not available")));

        assertThat(orderRepository.count()).isEqualTo(before);
    }
}
~~~

Test cần cấu hình fixture để inventory của product `10` không đủ và `CurrentCustomerProvider` trả về customer hợp lệ. Assertion response xác minh GraphQL error; assertion repository xác minh rollback thực tế. Nếu chỉ assert `.errors()`, test chưa chứng minh dữ liệu đã được hoàn tác.

Đối với checked exception, viết test tương ứng để chứng minh `rollbackFor` có tác dụng. Với `noRollbackFor`, xác minh dữ liệu được commit như thiết kế. Với `REQUIRES_NEW`, kiểm tra audit record vẫn tồn tại khi transaction ngoài rollback.

## 23. Kiểm thử nhiều mutation fields và tính atomic

Nếu API cho phép một operation chứa nhiều root mutation fields, hãy viết integration test chứng minh hành vi commit thực tế. Ví dụ field thứ nhất commit thành công, field thứ hai thất bại: dữ liệu field thứ nhất có thể vẫn tồn tại nếu mỗi field gọi transaction riêng.

Nếu use case yêu cầu atomic, test phải gửi một mutation field orchestration duy nhất và xác minh mọi bảng liên quan đều không thay đổi khi một bước thất bại. Không chỉ kiểm tra field trả error; phải đọc lại state từ database sau GraphQL execution.

## 24. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| GraphQL trả error nhưng dữ liệu vẫn tồn tại | Exception bị catch trong transactional method hoặc lỗi xảy ra sau transaction commit | Kiểm tra transaction boundary và để exception cần rollback thoát khỏi service |
| Checked exception không rollback | Mặc định rollback chỉ áp dụng cho unchecked exception và `Error` | Khai báo `rollbackFor` phù hợp |
| Resolver trả `null` mà không có error hữu ích | Resolver bắt exception và nuốt lỗi | Dùng `@GraphQlExceptionHandler`/`DataFetcherExceptionResolver` |
| Method có `@Transactional` nhưng không mở transaction | Self-invocation, object không do Spring quản lý hoặc lời gọi không qua proxy | Gọi qua bean proxy và đặt boundary ở service bean |
| Outer method nhận `UnexpectedRollbackException` | Inner REQUIRED participant đã đánh dấu transaction rollback-only | Để exception lan ra hoặc thiết kế transaction độc lập có chủ đích |
| Audit record vẫn còn sau rollback | Audit dùng `REQUIRES_NEW` | Đây là hành vi độc lập; chỉ dùng khi đúng yêu cầu nghiệp vụ |
| Nested rollback không hoạt động như mong đợi | Transaction manager/resource không hỗ trợ savepoint | Kiểm tra `NESTED` support và dùng integration test |
| Async task ghi dữ liệu ngoài transaction | Transaction imperative không truyền tự động sang thread khác | Mở transaction trong worker service trên thread thực thi |
| LazyInitializationException ở field con | Persistence context đã đóng sau service transaction | Trả DTO/projection hoặc dùng read service/DataLoader |
| Email đã gửi dù mutation rollback | Side effect xảy ra trước commit | Dùng after-commit callback hoặc transactional outbox |
| Test không phát hiện rollback sai | Test chỉ mock repository hoặc test method tự mở transaction | Dùng integration test và kiểm tra database state sau lời gọi |

## 25. Quy trình thiết kế exception và rollback cho mutation

Khi triển khai một mutation có ghi dữ liệu:

1. Xác định một use case nghiệp vụ cần atomic và đặt transaction ở application service.
2. Giữ resolver mỏng: bind arguments, lấy principal/context, gọi service.
3. Dùng `REQUIRED` mặc định để các service/repository cùng tham gia transaction.
4. Xác định exception nào là unchecked, checked và exception nào được phép commit.
5. Khai báo `rollbackFor`/`noRollbackFor` khi khác với mặc định.
6. Không catch rồi nuốt exception nếu nghiệp vụ phải rollback.
7. Ánh xạ exception sau transaction boundary thành GraphQL error an toàn.
8. Không giả định một GraphQL operation có nhiều mutation fields là một transaction.
9. Không giữ transaction ghi mở qua async field resolution hoặc external network calls.
10. Đưa email/message cần độ tin cậy cao qua after-commit hoặc transactional outbox.
11. Kiểm thử cả GraphQL response lẫn database state sau khi request kết thúc.
12. Kiểm tra propagation, self-invocation, transaction manager và reactive context khi hệ thống dùng nhiều execution model.

Spring transaction quản lý tính atomic của các thao tác database trong transaction boundary. GraphQL exception handling quản lý cách lỗi xuất hiện với client. Thiết kế đúng khi hai cơ chế được phối hợp rõ ràng: service quyết định commit/rollback, còn GraphQL layer chuyển kết quả hoặc exception thành response phù hợp.

## Tài liệu tham khảo

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
