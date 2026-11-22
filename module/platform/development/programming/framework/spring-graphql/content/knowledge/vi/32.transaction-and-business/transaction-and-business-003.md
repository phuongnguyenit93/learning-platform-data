# Transaction boundary của resolver

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao GraphQL không tự định nghĩa transaction semantics.
- Xác định transaction boundary cho `@MutationMapping` và `@SchemaMapping`.
- Dùng `@Transactional` để giới hạn một lần gọi resolver trong một transaction.
- Phân biệt transaction per resolver với transaction cho toàn bộ GraphQL request.
- Hiểu vì sao nested field và DataLoader có thể chạy ngoài transaction của root resolver.
- Thiết kế một Mutation nghiệp vụ bao trọn nhiều thao tác database.
- Phân biệt imperative transaction với reactive transaction.
- Xử lý rollback, exception và GraphQL error đúng cách.
- Nhận biết giới hạn của propagation, self-invocation và external side effects.
- Kiểm thử transaction boundary qua service và GraphQL operation.

## 1. GraphQL không tự định nghĩa transaction

GraphQL định nghĩa cách client chọn operation và field, cách server thực thi selection set và cách trả `data` cùng `errors`. GraphQL không quy định một request phải tương ứng với một database transaction.

Một GraphQL operation có thể gọi nhiều resolver. Mỗi resolver có thể truy cập một repository, service hoặc hệ thống dữ liệu khác nhau. GraphQL cũng cho phép client chỉ yêu cầu một phần object graph, vì vậy server không nhất thiết tải toàn bộ dữ liệu trong một lần truy vấn.

Điều này tạo ra một câu hỏi thiết kế: transaction nên bắt đầu và kết thúc ở đâu?

Một số lựa chọn thường gặp:

- Mỗi resolver method có transaction riêng.
- Một service method nghiệp vụ điều phối nhiều thao tác trong một transaction.
- Toàn bộ GraphQL request chạy trong một transaction.

Mỗi lựa chọn có phạm vi atomicity, isolation và chi phí tài nguyên khác nhau. Ứng dụng cần chọn boundary phù hợp với nghiệp vụ, thay vì giả định GraphQL request tự động là một transaction.

## 2. Transaction boundary của resolver là gì?

Transaction boundary xác định khoảng thời gian mà các thao tác trên resource có hỗ trợ transaction cùng tham gia một đơn vị công việc.

Với một resolver method được Spring quản lý transaction:

1. Lời gọi đi qua Spring transaction proxy.
2. Transaction manager bắt đầu hoặc tham gia transaction hiện có.
3. Resolver thực thi logic và gọi service/repository.
4. Nếu method kết thúc bình thường, transaction được commit.
5. Nếu exception phù hợp với rollback rule thoát khỏi method, transaction được rollback.

Ví dụ:

~~~java
@MutationMapping
@Transactional
public Order createOrder(@Argument("input") CreateOrderInput input) {
    // Các thao tác database trong lần gọi method này
    // cùng tham gia transaction.
    return orderService.create(input);
}
~~~

Trong ví dụ, transaction bắt đầu khi gọi `createOrder` và được hoàn tất khi method trả về hoặc ném exception. Các repository dùng cùng transaction manager có thể tham gia transaction đó.

Transaction này bao quanh lần gọi resolver. Nó không mặc nhiên bao quanh mọi field khác trong GraphQL request.

## 3. Transaction per controller method

Spring for GraphQL hỗ trợ transaction theo từng controller method. Có thể đặt `@Transactional` trên method `@MutationMapping` hoặc một method `@SchemaMapping`.

Ví dụ:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.transaction.annotation.Transactional;

@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @MutationMapping
    @Transactional
    public Account addAccount(@Argument("input") AccountInput input) {
        return accountService.addAccount(input);
    }
}
~~~

Transaction bao trọn lời gọi `addAccount`. Các thao tác database mà `accountService` thực hiện trong lời gọi đó tham gia cùng transaction nếu dùng transaction manager và resource tương ứng.

Spring for GraphQL mô tả đây là cách đơn giản, có entrypoint rõ ràng và thường được khuyến nghị khi cần transaction cho một mutation.

`@Transactional` chỉ là metadata. Ứng dụng cần có transaction manager phù hợp và transaction management được kích hoạt. Spring Boot thường tự cấu hình khi có transaction infrastructure tương ứng; với cấu hình Spring Framework thuần, có thể bật annotation-driven transaction management bằng `@EnableTransactionManagement`.

Có thể dùng `TransactionOperations` thay cho annotation nếu cần điều khiển transaction bằng code:

~~~java
import org.springframework.transaction.support.TransactionOperations;

@Controller
class AccountController {

    private final TransactionOperations transactionOperations;
    private final AccountService accountService;

    AccountController(
            TransactionOperations transactionOperations,
            AccountService accountService) {
        this.transactionOperations = transactionOperations;
        this.accountService = accountService;
    }

    @MutationMapping
    public Account addAccount(@Argument("input") AccountInput input) {
        return transactionOperations.execute(status ->
                accountService.addAccount(input)
        );
    }
}
~~~

Cách khai báo bằng annotation thường dễ đọc hơn. Programmatic transaction hữu ích khi boundary chỉ áp dụng cho một nhánh xử lý hoặc cần thao tác trực tiếp với transaction status.

## 4. Đặt transaction ở resolver hay service?

Có hai cách tổ chức phổ biến. Chọn một nơi làm boundary chính cho use case để người đọc hiểu rõ transaction bắt đầu ở đâu.

**Cách A: transaction ở resolver**

~~~java
@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    @Transactional
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}
~~~

Cách này phù hợp khi transaction gắn trực tiếp với một GraphQL field và controller là entrypoint nghiệp vụ của thao tác đó.

**Cách B: transaction ở application service**

~~~java
@Controller
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return orderService.placeOrder(input);
    }
}

@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.pending(input));
        inventoryRepository.reserve(input.items());
        return order.confirm();
    }
}
~~~

Cách này phù hợp khi cùng use case được gọi từ GraphQL, REST, message consumer hoặc một entrypoint khác. Transaction thuộc về nghiệp vụ nên service có thể tự bảo vệ tính nhất quán của nó.

Nếu cả resolver và service cùng có `@Transactional` với propagation mặc định `REQUIRED` và cùng transaction manager, lời gọi service thường tham gia transaction đang tồn tại. Điều đó không tạo ra hai transaction độc lập, nhưng có thể làm cấu hình khó đọc. Hãy chọn boundary chính và chỉ khai báo thêm khi có lý do rõ ràng.

## 5. Nhiều thao tác database trong một Mutation

Một mutation nghiệp vụ thường cần nhiều thao tác database có quan hệ phụ thuộc.

Ví dụ đặt hàng:

1. Tạo order ở trạng thái pending.
2. Ghi các order line.
3. Giảm hoặc giữ tồn kho.
4. Chuyển order sang trạng thái confirmed.

~~~java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;
    private final InventoryRepository inventoryRepository;

    OrderService(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public Order placeOrder(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.pending(input));

        lineRepository.saveAll(
                OrderLine.from(order.getId(), input.items())
        );

        inventoryRepository.reserve(input.items());

        order.confirm();
        return orderRepository.save(order);
    }
}
~~~

Vì toàn bộ thao tác nằm trong một service method transactional, các repository dùng cùng transaction manager có thể cùng commit hoặc rollback.

Không chia mỗi repository call thành một transaction riêng nếu nghiệp vụ yêu cầu atomicity giữa chúng. Nếu transaction kết thúc sau bước đầu tiên, bước sau thất bại sẽ không tự động hoàn tác thay đổi đã commit.

## 6. Nhiều root Mutation trong một GraphQL request

GraphQL cho phép một mutation operation có nhiều root fields. Theo GraphQL specification, các field ở top-level selection set của Mutation được thực thi tuần tự theo thứ tự xuất hiện trong document.

Ví dụ:

~~~graphql
mutation {
    reserve: reserveStock(orderId: "order-42")
    confirm: confirmOrder(orderId: "order-42")
}
~~~

Thứ tự thực thi là `reserveStock` rồi `confirmOrder`. Tuy nhiên, thực thi tuần tự không đồng nghĩa hai resolver dùng chung một transaction.

Nếu mỗi resolver method có `@Transactional`, boundary thường là:

- `reserveStock` bắt đầu và kết thúc transaction thứ nhất.
- Sau khi field thứ nhất hoàn tất, `confirmOrder` bắt đầu transaction thứ hai.
- Nếu transaction thứ hai thất bại, transaction thứ nhất đã commit sẽ không tự rollback.

Khi hai thao tác phải atomic cùng nhau, nên thiết kế một mutation nghiệp vụ nhận đủ input cần thiết:

~~~graphql
mutation {
    placeOrder(input: {
        customerId: "customer-1"
        items: [{ productId: "book-42", quantity: 2 }]
    }) {
        id
        status
    }
}
~~~

Một resolver gọi một application service transactional để thực hiện toàn bộ use case. Đây thường là cách đơn giản nhất để bảo đảm atomicity giữa các bước database liên quan.

## 7. Root resolver và nested field có boundary riêng

Một mutation có thể trả về object để GraphQL tiếp tục resolve các nested fields.

Ví dụ:

~~~graphql
mutation {
    addAccount(input: { name: "Northwind" }) {
        id
        name
        owner {
            id
            displayName
        }
    }
}
~~~

Resolver `addAccount` có thể được bảo vệ bằng transaction:

~~~java
@MutationMapping
@Transactional
public Account addAccount(@Argument("input") AccountInput input) {
    return accountService.addAccount(input);
}
~~~

Sau khi method trả về, transaction của `addAccount` kết thúc. GraphQL tiếp tục resolve field `owner`:

~~~java
@SchemaMapping(typeName = "Account", field = "owner")
@Transactional(readOnly = true)
public Person owner(Account account) {
    return personService.findOwner(account.getOwnerId());
}
~~~

Method `owner` chạy trong một transaction riêng. Nó không tự động tham gia transaction đã kết thúc của `addAccount`, dù cả hai method thuộc cùng một GraphQL operation.

Vì vậy, dữ liệu đọc ở nested field có thể quan sát trạng thái khác với thời điểm root mutation đã chạy. Nếu cần dữ liệu nhất quán, cân nhắc tải dữ liệu cần thiết trong cùng use case service hoặc trả DTO đã chứa phần dữ liệu phù hợp.

Không mở transaction kéo dài chỉ để giữ transaction context xuyên qua mọi nested field nếu không có yêu cầu isolation cụ thể.

## 8. Transaction với @SchemaMapping và @BatchMapping

`@SchemaMapping` là một resolver method và có thể có transaction riêng nếu được đánh dấu `@Transactional`.

`@BatchMapping` cũng thực hiện một lần fetch riêng cho một nhóm parent objects. Nếu batch resolver cần nhiều thao tác database phải atomic, có thể đặt boundary ở batch method hoặc service mà nó gọi.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
@Transactional(readOnly = true)
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Transaction của batch resolver bao quanh lần gọi batch method. Nó không được kế thừa từ transaction của root resolver chỉ vì batch này được kích hoạt trong cùng request.

DataLoader có thể trì hoãn và gom các lần tải field để thực hiện batch sau khi các resolver cha đã trả về. Vì vậy không giả định transaction của root resolver vẫn mở khi DataLoader chạy.

Nếu batch cần transaction, hãy đặt boundary tại batch resolver/service. Nếu nhiều field phải đọc cùng một snapshot nhất quán, cần thiết kế query hoặc transaction boundary rõ ràng thay vì dựa vào thời điểm DataLoader được dispatch.

## 9. Transaction cho Query và readOnly

Query thường chỉ đọc dữ liệu nên không phải lúc nào cũng cần transaction tường minh. Repository có thể tự dùng transaction cho từng thao tác theo cơ chế của Spring Data hoặc persistence technology.

Nếu use case cần đọc nhất quán qua nhiều thao tác database, có thể dùng:

~~~java
@QueryMapping
@Transactional(readOnly = true)
public Account account(@Argument("id") UUID id) {
    return accountService.findAccountWithDetails(id);
}
~~~

`readOnly = true` là một hint cho transaction manager và persistence provider. Tùy nền tảng, nó có thể giúp tối ưu hoặc hạn chế một số thao tác ghi, nhưng không nên coi nó là cơ chế bảo mật đảm bảo không thể ghi dữ liệu.

Nếu nested field được resolve bằng method khác, transaction của root Query vẫn kết thúc khi method root trả về. Muốn một snapshot nhất quán cho toàn bộ object graph cần chiến lược rõ ràng hơn.

## 10. Transaction propagation

Propagation xác định một method transactional xử lý thế nào khi đã có transaction hiện tại.

| Propagation | Hành vi |
| --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo transaction mới |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và tạo transaction độc lập |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không có transaction |

`REQUIRED` là mặc định. Khi resolver đã mở transaction và gọi một service method cũng có `@Transactional`, service thường tham gia cùng transaction.

`REQUIRES_NEW` hữu ích khi một thao tác cần commit độc lập. Nhưng nếu transaction bên ngoài rollback, transaction mới đã commit vẫn giữ kết quả. Điều đó có thể làm trạng thái nghiệp vụ không còn atomic như mong muốn.

Ví dụ:

~~~java
@Transactional
public void placeOrder(PlaceOrderInput input) {
    orderRepository.save(Order.pending(input));
    auditService.recordAttempt(input);
    inventoryService.reserve(input.items());
}
~~~

Nếu `auditService.recordAttempt` dùng `REQUIRES_NEW`, audit record có thể commit ngay cả khi việc giữ tồn kho sau đó thất bại và transaction đặt hàng rollback. Đây có thể là điều mong muốn khi audit cần lưu lại mọi lần thử, nhưng phải là quyết định nghiệp vụ có chủ đích.

## 11. Isolation, timeout và read-only

Ngoài propagation, `@Transactional` có thể khai báo:

- `isolation`: mức isolation cho transaction mới.
- `timeout`: giới hạn thời gian transaction theo hỗ trợ của transaction manager.
- `readOnly`: hint cho transaction chỉ đọc.
- `rollbackFor` và `noRollbackFor`: quy tắc rollback theo exception.

Ví dụ:

~~~java
@Transactional(
        timeout = 5,
        isolation = Isolation.READ_COMMITTED
)
public Order confirmOrder(UUID orderId) {
    // Đọc và cập nhật trạng thái order.
}
~~~

Không nên tăng isolation level hoặc timeout tùy tiện. Isolation cao có thể tăng lock contention và giảm throughput; timeout ngắn có thể làm use case hợp lệ thất bại khi database đang tải cao.

Hãy chọn các thuộc tính dựa trên yêu cầu consistency và đặc tính database đang dùng.

## 12. Rollback và GraphQL error handling

Mặc định Spring rollback transaction khi method kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không kích hoạt rollback theo mặc định nếu không khai báo quy tắc bổ sung.

Ví dụ:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public Order payOrder(UUID orderId) throws PaymentRejectedException {
    Order order = orderRepository.findById(orderId).orElseThrow();
    paymentService.authorize(order);
    return order.markPaid();
}
~~~

Nếu `PaymentRejectedException` là checked exception, `rollbackFor` yêu cầu Spring rollback khi exception đó thoát khỏi method.

Spring GraphQL có thể chuyển exception từ resolver thành GraphQL error. Việc chuyển đổi response diễn ra sau khi exception đi qua transaction interceptor của method. Nếu exception đã thoát khỏi method transactional, transaction interceptor có cơ hội áp dụng rollback rule trước khi GraphQL xử lý lỗi.

Có một điểm cần chú ý: nếu code bắt exception bên trong method rồi trả về bình thường, transaction interceptor thấy method thành công và có thể commit.

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.pending(input));

    try {
        inventoryService.reserve(input.items());
    }
    catch (InsufficientStockException exception) {
        // Nếu chỉ trả về bình thường, transaction có thể commit.
        return order.markRejected();
    }

    return order.confirm();
}
~~~

Nếu nghiệp vụ yêu cầu rollback, hãy để exception phù hợp thoát khỏi method hoặc đánh dấu transaction rollback-only theo cách phù hợp. Đừng giả định một GraphQL error object hay `DataFetcherResult` có errors sẽ tự động rollback transaction; đó có thể chỉ là một kết quả bình thường đối với transaction interceptor.

## 13. Spring AOP proxy và self-invocation

`@Transactional` trong proxy mode mặc định hoạt động khi lời gọi đi qua Spring proxy. Nếu một method gọi method transactional khác trên cùng instance bằng `this`, lời gọi nội bộ đó không đi qua proxy.

Ví dụ:

~~~java
@Service
class OrderService {

    public Order placeOrder(PlaceOrderInput input) {
        return createOrder(input);
    }

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        // ...
        return orderRepository.save(Order.pending(input));
    }
}
~~~

Nếu `placeOrder` gọi trực tiếp `createOrder` trên cùng object, annotation có thể không được áp dụng cho lời gọi nội bộ đó.

Cách tổ chức dễ kiểm soát là gọi method transactional từ một Spring bean khác:

~~~java
@Service
class OrderFacade {

    private final OrderWriter orderWriter;

    OrderFacade(OrderWriter orderWriter) {
        this.orderWriter = orderWriter;
    }

    public Order placeOrder(PlaceOrderInput input) {
        return orderWriter.createOrder(input);
    }
}

@Service
class OrderWriter {

    @Transactional
    public Order createOrder(PlaceOrderInput input) {
        // ...
        return orderRepository.save(Order.pending(input));
    }
}
~~~

Dùng method được proxy quản lý, thường là public method trên Spring bean. Không tự tạo service bằng `new` nếu cần transaction interception.

## 14. Imperative transaction và reactive transaction

Spring hỗ trợ hai mô hình transaction chính:

| Mô hình | Transaction manager | Context |
| --- | --- | --- |
| Imperative | `PlatformTransactionManager` | Thường gắn với thread hiện tại |
| Reactive | `ReactiveTransactionManager` | Gắn với Reactor Context |

Với method trả về object thông thường, Spring dùng imperative transaction. Với method trả về reactive type như `Mono` hoặc `Flux`, Spring có thể áp dụng reactive transaction nếu có reactive transaction manager phù hợp.

Ví dụ reactive service:

~~~java
@Service
class ReactiveOrderService {

    private final ReactiveOrderRepository orderRepository;

    ReactiveOrderService(ReactiveOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Mono<Order> confirmOrder(UUID orderId) {
        return orderRepository.findById(orderId)
                .flatMap(order -> {
                    order.confirm();
                    return orderRepository.save(order);
                });
    }
}
~~~

Reactive transaction được gắn vào publisher và chạy trong Reactor Context khi publisher được subscribe. Các thao tác database tham gia transaction cần nằm trong cùng reactive pipeline/context.

Không dùng blocking JPA/JDBC bên trong reactive pipeline rồi kỳ vọng imperative transaction được truyền tự động qua scheduler. Với reactive data access, dùng reactive repository và `ReactiveTransactionManager` tương ứng.

## 15. Transaction boundary với Subscription

Subscription là một operation có vòng đời dài và có thể phát nhiều event. Không nên mở một database transaction cho toàn bộ thời gian subscription.

Nếu resolver trả về `Flux` không bao giờ hoàn tất và transaction bao quanh publisher, transaction có thể giữ resource quá lâu. Điều này gây lock kéo dài, connection pool exhaustion và khó phục hồi khi client ngắt kết nối.

Nên phân chia:

- Subscription resolver chịu trách nhiệm đăng ký publisher và quản lý stream.
- Mỗi lần xử lý event hoặc cập nhật trạng thái dùng một transaction ngắn riêng.
- Không giữ transaction database mở trong khi chờ event từ broker hoặc client.
- Xử lý cancellation và cleanup publisher theo lifecycle của subscription.

Nếu event cần đọc snapshot dữ liệu nhất quán, thực hiện truy vấn đó trong một transaction ngắn khi event được xử lý rồi phát DTO đã tạo ra.

## 16. Transaction cho toàn bộ GraphQL request

Có thể cần một transaction duy nhất cho toàn bộ execution request, để nhiều DataFetcher cùng tham gia một đơn vị công việc. Đây là chiến lược nâng cao, không phải hành vi mặc định của Spring for GraphQL.

Với imperative transaction manager, transaction thường dùng thread-bound state (`ThreadLocal`). Vì vậy, nếu muốn mọi DataFetcher tham gia cùng transaction, execution strategy phải chạy các DataFetcher tuần tự trên cùng thread.

Spring for GraphQL đề cập `AsyncSerialExecutionStrategy` như một điểm bắt đầu để xây dựng execution strategy tuần tự. Có thể triển khai bằng GraphQL Java `Instrumentation` hoặc custom `ExecutionStrategy` để mở transaction trước DataFetcher đầu tiên và commit/rollback sau khi toàn bộ unit of work hoàn tất.

Cách này có các đánh đổi:

- Nhiều field độc lập mất khả năng chạy song song.
- Transaction có thể mở lâu trong khi server resolve toàn bộ object graph.
- Database connection và lock bị giữ lâu hơn.
- Lỗi ở nested field có thể làm rollback một phạm vi lớn.
- Cần xử lý transaction cleanup và truyền lỗi về GraphQL response cẩn thận.

Chỉ chọn request-wide transaction khi nghiệp vụ thực sự cần consistency xuyên nhiều resolver và đã đánh giá ảnh hưởng tới concurrency, latency và resource usage.

Với phần lớn mutation, một resolver/use-case method transactional có boundary rõ ràng thường dễ vận hành và kiểm thử hơn.

## 17. Database transaction không bao trọn external service

Một database transaction chỉ kiểm soát các resource tham gia cùng transaction manager. Nó không tự rollback:

- HTTP request đã gửi tới payment provider.
- Email đã gửi.
- Message đã publish lên broker.
- File đã ghi lên object storage.
- Thao tác trên database khác dùng transaction manager độc lập.

Ví dụ, nếu transaction database tạo order rồi gọi payment provider thành công nhưng database rollback, payment provider không tự hoàn tác khoản charge.

Với quy trình liên quan nhiều hệ thống, cân nhắc:

- Transactional outbox để ghi sự kiện cùng transaction database rồi publish sau commit.
- Saga hoặc compensation action cho workflow nhiều dịch vụ.
- Idempotency key để retry không tạo side effect trùng.
- Trạng thái nghiệp vụ trung gian như `PENDING`, `CONFIRMED`, `FAILED`.

Không giữ database transaction mở trong lúc chờ một HTTP call dài nếu không có lý do đặc biệt. Điều đó giữ connection/lock nhưng vẫn không tạo atomicity phân tán.

## 18. Kiểm thử transaction boundary

Cần kiểm thử cả trường hợp thành công và rollback. Một service integration test có thể xác minh thay đổi database không còn sau khi một bước nghiệp vụ ném exception.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderTransactionTests {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void shouldRollbackOrderWhenReservationFails() {
        PlaceOrderInput input = new PlaceOrderInput(
                "request-rollback-1",
                List.of(new OrderItemInput("book-42", 1000))
        );

        assertThatThrownBy(() -> orderService.placeOrder(input))
                .isInstanceOf(InsufficientStockException.class);

        assertThat(orderRepository.findByReference("request-rollback-1"))
                .isEmpty();
    }
}
~~~

Test này giả định `OrderService.placeOrder` có `@Transactional`, `inventoryService.reserve` ném `InsufficientStockException`, và repository truy vấn theo reference. Test không được đánh dấu `@Transactional` ở cấp test nếu muốn quan sát kết quả sau khi transaction của service đã rollback hoặc commit độc lập.

Với GraphQL integration test, gửi Mutation qua `GraphQlTester` hoặc `HttpGraphQlTester`, xác minh response có error theo contract, rồi truy vấn repository để xác minh không có dữ liệu được commit.

Nên kiểm tra thêm:

- Mutation thành công lưu đủ order và order lines.
- Một bước database thất bại làm rollback các bước trước đó.
- Nested `@SchemaMapping` có transaction riêng nếu được cấu hình.
- Hai root mutation fields không bị hiểu nhầm là một transaction chung.
- `REQUIRES_NEW` vẫn commit khi transaction ngoài rollback, nếu đó là hành vi mong đợi.
- Checked exception được rollback khi có `rollbackFor`.
- Reactive transaction rollback khi publisher phát error.
- Subscription cancellation không để transaction hoặc connection bị giữ lâu.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mutation lưu một phần dữ liệu | Mỗi repository call tự commit hoặc boundary quá hẹp | Bao các bước database trong một resolver/use-case transaction |
| Nested field đọc dữ liệu không nhất quán | Transaction của root resolver đã kết thúc trước nested resolver | Thiết kế projection/service query hoặc boundary phù hợp cho nested field |
| Hai root Mutation fields không rollback cùng nhau | Mỗi resolver có transaction riêng | Dùng một mutation nghiệp vụ điều phối các bước cần atomic |
| `@Transactional` không có tác dụng | Method không đi qua Spring proxy hoặc transaction management chưa được bật | Kiểm tra bean, proxy và transaction manager |
| Exception có GraphQL error nhưng dữ liệu vẫn commit | Exception bị bắt và method kết thúc bình thường | Để exception thoát ra hoặc đánh dấu rollback-only |
| Checked exception không rollback | Rollback mặc định không áp dụng cho checked exception | Khai báo `rollbackFor` hoặc cấu hình rollback rule |
| Self-invocation không mở transaction | Lời gọi nội bộ không đi qua proxy | Tách method sang Spring bean khác |
| DataLoader chạy ngoài transaction root | Batch được dispatch sau khi root resolver trả về | Đặt boundary ở batch resolver/service |
| Reactive transaction không bao quanh truy vấn | Dùng sai transaction manager hoặc publisher rời Reactor Context | Dùng `ReactiveTransactionManager` và giữ pipeline reactive |
| Subscription giữ connection database lâu | Transaction bao quanh publisher dài hạn | Dùng transaction ngắn theo từng event |
| Gọi payment thành công nhưng order rollback | External service không tham gia database transaction | Dùng outbox, saga hoặc compensation |
| Test rollback không đáng tin | Test có transaction ngoài cùng hoặc chỉ assert trong cùng transaction | Kiểm tra trạng thái bằng transaction độc lập sau khi service kết thúc |

## 20. Quy trình chọn transaction boundary

Khi thiết kế một GraphQL resolver, hãy thực hiện theo trình tự:

1. **Xác định unit of work.** Liệt kê những thay đổi dữ liệu phải commit hoặc rollback cùng nhau.
2. **Chọn entrypoint.** Dùng resolver method hoặc application service làm transaction boundary chính.
3. **Giữ transaction ngắn.** Chỉ bao quanh thao tác database cần atomicity.
4. **Phân biệt root và nested fields.** Không giả định transaction của root resolver kéo dài qua nested resolver hoặc DataLoader.
5. **Thiết kế nhiều Mutation.** Nếu nhiều bước cần atomic, gom chúng vào một use case/mutation method.
6. **Chọn transaction manager.** Dùng `PlatformTransactionManager` cho imperative hoặc `ReactiveTransactionManager` cho reactive pipeline.
7. **Xác định rollback rules.** Kiểm tra runtime exception, checked exception và các exception bị bắt.
8. **Kiểm tra proxy.** Đảm bảo lời gọi transactional đi qua Spring bean proxy.
9. **Tách external side effects.** Dùng outbox/saga khi cần phối hợp database với hệ thống khác.
10. **Kiểm thử commit/rollback.** Xác minh trạng thái database sau khi method hoặc GraphQL operation kết thúc.

## 21. Tổng kết

GraphQL không tự định nghĩa transaction semantics. Trong Spring for GraphQL, một cách rõ ràng để kiểm soát transaction là đặt `@Transactional` trên `@MutationMapping` hoặc `@SchemaMapping` method. Transaction bắt đầu khi method được gọi và kết thúc khi method hoàn tất; các nested resolver và DataLoader có thể chạy ngoài boundary đó.

Nếu nhiều thao tác database phải atomic, hãy gom chúng vào một resolver hoặc application service method có transaction. Nhiều root Mutation fields được thực thi tuần tự nhưng không mặc nhiên chia sẻ một transaction. Request-wide transaction là giải pháp nâng cao, đòi hỏi kiểm soát execution strategy và có thể làm giảm concurrency. Với reactive service, dùng reactive transaction manager và Reactor Context; với Subscription, tránh giữ transaction trong suốt stream. Cuối cùng, kiểm thử rollback bằng trạng thái database quan sát sau khi transaction kết thúc và xử lý external side effects bằng outbox hoặc saga khi cần.

## Tài liệu tham khảo

- [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [GraphQL Specification – Execution and Serial Mutation Fields](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)

