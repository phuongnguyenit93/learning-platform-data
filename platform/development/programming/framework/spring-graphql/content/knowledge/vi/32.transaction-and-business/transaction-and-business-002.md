# Transaction trong mutation

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao GraphQL không tự định nghĩa transaction cho mutation.
- Phân biệt thực thi tuần tự các mutation field với atomic transaction ở database.
- Thiết kế transaction boundary cho một mutation bằng @Transactional.
- Hiểu transaction kết thúc ở đâu khi mutation trả về object có nested field.
- Chọn cách gộp nhiều bước nghiệp vụ vào một transaction.
- Cấu hình rollback rule, propagation và transaction manager phù hợp.
- Phân biệt transaction imperative với reactive transaction.
- Xử lý side effect tới message broker hoặc hệ thống bên ngoài bằng outbox.
- Kiểm thử commit, rollback và partial GraphQL response.

## Vì sao mutation cần transaction?

Mutation thường tạo, cập nhật hoặc xóa dữ liệu. Một thao tác nghiệp vụ có thể bao gồm nhiều câu lệnh database phải cùng thành công hoặc cùng thất bại.

Ví dụ đặt đơn hàng có thể thực hiện:

1. Tạo Order.
2. Tạo các OrderItem.
3. Giảm tồn kho.
4. Ghi nhận thanh toán nội bộ.
5. Ghi audit record.

Nếu bước 1 đến 3 đã ghi dữ liệu nhưng bước 4 thất bại, hệ thống có thể ở trạng thái không nhất quán. Transaction giúp gom các thao tác trên cùng transaction manager thành một đơn vị công việc có atomicity và isolation.

GraphQL cung cấp mutation để biểu diễn thao tác thay đổi dữ liệu, nhưng GraphQL không quy định database transaction phải bắt đầu hoặc kết thúc ở đâu. Server và ứng dụng quyết định transaction boundary dựa trên use case. Spring for GraphQL tích hợp với Spring transaction management để thực hiện quyết định đó. [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)

## Thứ tự mutation không đồng nghĩa với transaction

GraphQL thực thi các field ở root Mutation theo thứ tự tuần tự trong document. Field tiếp theo chỉ bắt đầu sau khi field trước hoàn tất. Quy tắc này giúp tránh việc hai mutation root field trong cùng operation tự chạy đua với nhau.

Theo GraphQL, side effect thuộc về các field ở root Mutation. Nested field trong selection set của mutation vẫn là field phân giải dữ liệu và nên giữ side-effect-free; không dùng resolver nested để âm thầm thực hiện thêm thao tác ghi.

Ví dụ:

~~~graphql
mutation {
  reserveDraft: reserveBook(id: "book-101") {
    id
  }
  publishDraft: publishBook(id: "book-101") {
    id
    status
  }
}
~~~

publishDraft chạy sau reserveDraft. Tuy nhiên, tuần tự chỉ là thứ tự thực thi; nó không có nghĩa toàn bộ operation được bao bởi một transaction database.

Giả sử:

- reserveDraft hoàn tất và transaction của nó commit.
- publishBook chạy sau đó nhưng gặp lỗi.

GraphQL trả lỗi cho field publishDraft, nhưng không có cơ chế tự động hoàn tác dữ liệu đã commit bởi reserveDraft. GraphQL cũng không tự rollback các side effect thành công trước đó. [GraphQL Specification – Mutation Execution](https://spec.graphql.org/September2026/#sec-Mutation)

| Khái niệm | Điều được bảo đảm |
| --- | --- |
| Mutation root fields chạy tuần tự | Field sau bắt đầu sau field trước |
| Database transaction | Các thao tác thuộc cùng transaction cùng commit hoặc rollback |
| Một GraphQL operation | Có thể chứa nhiều field và trả partial data cùng errors |

Nếu một use case yêu cầu nhiều bước phải atomic, hãy biểu diễn nó thành một mutation nghiệp vụ duy nhất và chạy toàn bộ bước ghi trong cùng transaction.

## Transaction boundary theo mutation controller method

Spring for GraphQL khuyến nghị cách đơn giản là dùng Spring transaction management trên method có @MutationMapping hoặc @SchemaMapping. Transaction bắt đầu khi method được gọi và kết thúc khi method trả về. Mọi thao tác sử dụng cùng transaction manager trong thời gian đó có thể tham gia cùng transaction.

Ví dụ schema:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): BookPayload!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  initialStock: Int!
}

type BookPayload {
  book: BookView!
}

type BookView {
  id: ID!
  title: String!
  status: String!
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.transaction.annotation.Transactional;

@Controller
public class BookMutationController {

    private final BookService bookService;
    private final InventoryService inventoryService;
    private final AuditService auditService;

    public BookMutationController(
            BookService bookService,
            InventoryService inventoryService,
            AuditService auditService) {
        this.bookService = bookService;
        this.inventoryService = inventoryService;
        this.auditService = auditService;
    }

    @MutationMapping
    @Transactional
    public BookPayload createBook(
            @Argument("input") @Valid CreateBookInput input) {

        Book book = bookService.create(input.title(), input.authorId());
        inventoryService.initializeStock(book.id(), input.initialStock());
        auditService.recordBookCreated(book.id());

        return new BookPayload(BookView.from(book));
    }
}
~~~

Trong ví dụ, ba thao tác ghi được thực hiện trong cùng transaction nếu chúng dùng cùng transaction manager và tham gia theo propagation mặc định REQUIRED. Nếu bất kỳ lời gọi nào ném runtime exception ra khỏi method, transaction có thể rollback toàn bộ các thao tác đã thực hiện trước đó.

Transactional có thể đặt trên mutation controller method để transaction boundary trùng với một mutation field. Đây là cách được tài liệu Spring for GraphQL khuyến nghị cho trường hợp thông thường. Một ứng dụng cũng có thể đặt transaction ở một application service/facade duy nhất được mutation gọi; khi đó cần bảo đảm toàn bộ use case nằm trong một lần gọi qua Spring proxy và không vô tình chia thành nhiều transaction độc lập.

### Transaction kết thúc trước khi nested field được phân giải

Giả sử mutation trả về object có nested field:

~~~graphql
type BookPayload {
  book: Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Controller mutation:

~~~java
@MutationMapping
@Transactional
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Sau khi method createBook trả về, transaction của method được hoàn tất. GraphQL tiếp tục phân giải selection set, ví dụ book.author.name. Resolver Book.author chạy sau đó và không tự động thuộc transaction của createBook.

Nếu nested resolver cũng được đánh dấu @Transactional, nó sẽ tạo hoặc tham gia một transaction theo propagation và transaction context hiện có tại thời điểm resolver được gọi. Thông thường đây là transaction riêng, không phải transaction đã kết thúc của mutation method. Hai transaction riêng có thể nhìn thấy trạng thái khác nhau nếu dữ liệu bị thay đổi giữa các lần đọc.

Điều này đặc biệt quan trọng khi trả JPA entity có lazy association. Transaction đã đóng trước khi nested resolver truy cập association có thể gây LazyInitializationException. Có thể giải quyết bằng cách:

- Trả DTO hoặc projection đã được materialize trong transaction mutation.
- Đọc trước dữ liệu cần thiết trong service method và trả object không phụ thuộc lazy loading.
- Dùng nested resolver riêng để tải dữ liệu, với transaction boundary và consistency phù hợp.

Không dựa vào việc GraphQL sẽ giữ transaction mở đến khi toàn bộ JSON response được serialize.

## Gộp nhiều bước nghiệp vụ trong một transaction

Khi nhiều thao tác phải cùng thành công hoặc cùng thất bại, hãy tạo một mutation đại diện cho toàn bộ use case:

~~~graphql
type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderPayload!
}

input PlaceOrderInput {
  customerId: ID!
  items: [OrderItemInput!]!
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
}
~~~

Controller:

~~~java
@MutationMapping
@Transactional
public OrderPayload placeOrder(
        @Argument("input") @Valid PlaceOrderInput input) {

    Order order = orderService.createPendingOrder(input);
    inventoryService.reserve(order.items());
    paymentService.recordInternalAuthorization(order.id());
    auditService.recordOrderPlaced(order.id());

    return OrderPayload.from(order);
}
~~~

Các service method được gọi trong transaction hiện tại. Nếu chúng cũng có @Transactional với propagation REQUIRED, chúng tham gia transaction đang tồn tại thay vì tạo transaction mới.

Đây là một ranh giới nghiệp vụ rõ ràng:

- GraphQL client gửi một mutation placeOrder.
- Server thực hiện các bước cần thiết trong một transaction.
- Nếu một bước ghi thất bại và exception làm transaction rollback, toàn bộ thay đổi thuộc transaction đó được rollback.
- GraphQL chuyển exception thành error theo cấu hình exception resolver.

Nếu client gửi nhiều root mutation field riêng biệt, mỗi controller method có thể có transaction riêng. Nếu yêu cầu atomic, hãy thay các thao tác rời rạc bằng một mutation tổng hợp.

## Transaction ở controller hay service?

Cả hai cách đều có thể hoạt động khi method được gọi qua Spring transaction proxy. Chọn một boundary đại diện cho use case:

| Cách đặt transaction | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| @Transactional trên @MutationMapping | Muốn transaction boundary khớp với một mutation field | Spring for GraphQL khuyến nghị đây là cách đơn giản, rõ ràng |
| @Transactional trên application service/facade | Muốn giữ business use case độc lập với GraphQL và có thể gọi từ nhiều entry point | Resolver gọi đúng một method facade; các bước con tham gia cùng transaction |
| TransactionOperations hoặc TransactionTemplate | Cần transaction boundary tường minh trong một đoạn code | Dùng callback để xác định rõ phần công việc nằm trong transaction |
| Transactional instrumentation toàn GraphQL request | Cần một transaction bao quanh nhiều data fetcher trong một operation | Cấu hình phức tạp, có ràng buộc execution strategy và concurrency |

Không cần đặt @Transactional lên mọi repository call hoặc mọi nested resolver. Repository Spring Data thường đã có transaction semantics cho từng thao tác riêng lẻ, nhưng các thao tác riêng đó không tự tạo thành một business transaction lớn.

### TransactionOperations

Có thể quản lý transaction bằng API lập trình:

~~~java
import org.springframework.transaction.support.TransactionOperations;

@Controller
public class AccountController {

    private final TransactionOperations transactionOperations;
    private final AccountRepository accountRepository;
    private final AuditRepository auditRepository;

    public AccountController(
            TransactionOperations transactionOperations,
            AccountRepository accountRepository,
            AuditRepository auditRepository) {
        this.transactionOperations = transactionOperations;
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @MutationMapping
    public Account addAccount(@Argument("input") AccountInput input) {
        return transactionOperations.execute(status -> {
            Account account = accountRepository.save(Account.from(input));
            auditRepository.save(AuditRecord.accountCreated(account.id()));
            return account;
        });
    }
}
~~~

TransactionOperations.execute bắt đầu hoặc tham gia transaction theo cấu hình, thực thi callback và commit/rollback khi callback kết thúc. Đây là API imperative, thường dùng cùng PlatformTransactionManager.

## Transactional instrumentation cho toàn request

Spring for GraphQL cũng mô tả một hướng nâng cao: mở transaction trước khi GraphQL gọi data fetcher đầu tiên và đóng transaction sau khi hoàn thành request execution. Khi đó nhiều @SchemaMapping có thể tham gia cùng transaction.

Đây không phải transaction tự động mặc định của GraphQL. Ứng dụng phải tự triển khai transaction instrumentation hoặc custom ExecutionStrategy, và phải bảo đảm việc gọi data fetcher phù hợp với loại transaction manager.

Với imperative transaction do PlatformTransactionManager quản lý, transaction context thường được gắn với thread qua ThreadLocal. Vì vậy, để mọi data fetcher tham gia cùng transaction, execution strategy phải gọi chúng tuần tự trên cùng thread. AsyncSerialExecutionStrategy là một điểm bắt đầu có thể xem xét cho cách tiếp cận này.

Các đánh đổi:

- Nhiều nested field có thể cần đọc dữ liệu độc lập nhưng phải chờ tuần tự.
- Transaction có thể mở lâu hơn và giữ connection/lock trong thời gian lớn hơn.
- Một field chậm có thể kéo dài transaction của cả operation.
- Cần xử lý commit/rollback và chuyển lỗi transaction thành GraphQL response một cách nhất quán.
- Không nên dùng cách này chỉ để tránh thiết kế transaction boundary cho mutation.

Với đa số mutation, transaction per controller method dễ hiểu và dễ kiểm thử hơn. Chỉ cân nhắc transaction instrumentation toàn request khi yêu cầu consistency thực sự cần tất cả data fetcher trong cùng một transaction.

## Quy tắc commit và rollback

Spring declarative transaction dùng AOP proxy và transaction manager để bao quanh lời gọi method. Khi method kết thúc bình thường, transaction được commit; khi exception phù hợp với rollback rule thoát khỏi method, transaction được đánh dấu rollback.

Mặc định của @Transactional:

| Thuộc tính | Giá trị mặc định |
| --- | --- |
| Propagation | REQUIRED |
| Isolation | DEFAULT của transaction system |
| Read-only | false |
| Timeout | Theo mặc định của transaction system hoặc không giới hạn nếu không hỗ trợ |
| Rollback | RuntimeException và Error làm rollback |
| Checked exception | Không rollback mặc định |

Ví dụ rollback cho checked exception:

~~~java
@MutationMapping
@Transactional(rollbackFor = InventoryUnavailableException.class)
public OrderPayload placeOrder(@Argument("input") PlaceOrderInput input)
        throws InventoryUnavailableException {

    Order order = orderService.createPendingOrder(input);
    inventoryService.reserve(order.items()); // Có thể ném checked exception.
    return OrderPayload.from(order);
}
~~~

Có thể dùng noRollbackFor nếu một exception cụ thể không nên làm rollback, nhưng chỉ chọn khi nghiệp vụ thật sự muốn commit các thay đổi trước exception đó.

### Exception phải thoát khỏi transactional method

Ví dụ dễ gây lỗi:

~~~java
@MutationMapping
@Transactional
public BookPayload createBook(@Argument("input") CreateBookInput input) {
    try {
        Book book = bookService.create(input);
        auditService.recordBookCreated(book.id());
        return BookPayload.success(book);
    }
    catch (AuditException ex) {
        return BookPayload.failure("AUDIT_FAILED");
    }
}
~~~

Method bắt exception và trả về bình thường. Transaction interceptor không nhìn thấy exception thoát khỏi method, nên transaction có thể commit. GraphQL response có thể biểu diễn lỗi nghiệp vụ trong payload, nhưng điều đó không tự động rollback database.

Nếu lỗi phải rollback:

- Để exception thoát khỏi transactional method.
- Hoặc cấu hình rollback rule cho exception phù hợp.
- Chỉ dùng TransactionStatus.setRollbackOnly() hoặc API tương ứng khi thật sự cần đánh dấu rollback bằng lập trình.

GraphQL exception resolver hoặc @GraphQlExceptionHandler có thể chuyển exception thành GraphQL error sau khi exception đi ra khỏi resolver. Việc chuyển đổi response không phải là cơ chế rollback; quyết định rollback thuộc transaction manager tại boundary.

### Propagation

REQUIRED là mặc định: nếu transaction đã tồn tại thì tham gia transaction đó; nếu chưa có thì tạo transaction mới.

REQUIRES_NEW tạm dừng transaction hiện tại và tạo transaction mới. Transaction mới có thể commit độc lập ngay cả khi transaction bên ngoài rollback. Điều này hữu ích cho một số audit hoặc tác vụ độc lập, nhưng có thể làm mất tính atomic nếu dùng tùy tiện.

Ví dụ:

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

Nếu audit phải luôn đi cùng thay đổi nghiệp vụ, hãy để nó tham gia transaction REQUIRED. Chỉ dùng REQUIRES_NEW khi chấp nhận audit commit độc lập với mutation.

### Spring AOP proxy và self-invocation

Transaction annotation được áp dụng qua Spring proxy. Lời gọi method từ bean khác đi qua proxy sẽ kích hoạt transaction advice. Lời gọi nội bộ cùng object như this.saveAndAudit() có thể bỏ qua proxy và không tạo transaction mới theo annotation trên method được gọi.

Hãy đặt transaction boundary ở method được gọi từ bên ngoài bean, hoặc tách use case sang một Spring bean riêng. Không dựa vào annotation trên private helper method hoặc self-invocation để mở transaction.

Trong Spring Boot, transaction auto-configuration thường thiết lập transaction management khi có transaction manager phù hợp. Ứng dụng Spring không dùng Boot có thể cần cấu hình transaction management và transaction manager tường minh.

## Transaction manager và loại dữ liệu

Transaction chỉ quản lý tài nguyên được transaction manager tương ứng hỗ trợ:

| Công nghệ | Transaction manager thường dùng |
| --- | --- |
| JDBC | DataSourceTransactionManager hoặc JdbcTransactionManager |
| JPA/Hibernate | JpaTransactionManager |
| R2DBC | R2dbcTransactionManager |
| JTA nhiều tài nguyên được quản lý | JtaTransactionManager |

Spring Boot thường tự cấu hình transaction manager theo starter và data source có trên classpath. Nếu ứng dụng có nhiều transaction manager, chỉ rõ manager cần dùng qua thuộc tính transactionManager của @Transactional.

Một transaction JPA không tự động bao gồm một lời gọi REST tới dịch vụ thanh toán hoặc một lần publish Kafka. Muốn atomic giữa nhiều hệ thống cần một thiết kế phân tán phù hợp; transaction local của database không thể tự rollback side effect đã xảy ra ở hệ thống từ xa.

## Reactive transaction trong mutation

Với Spring WebFlux và Spring Data R2DBC, mutation có thể trả về Mono hoặc Flux. Khi dùng reactive transaction, cần ReactiveTransactionManager. Spring dùng Reactor Context để truyền transaction thay vì ThreadLocal.

Ví dụ:

~~~java
@MutationMapping
@Transactional
public Mono<BookView> createBook(
        @Argument("input") CreateBookInput input) {

    return bookRepository.save(Book.from(input))
            .flatMap(saved ->
                    inventoryRepository.initialize(saved.id())
                            .thenReturn(BookView.from(saved)));
}
~~~

Các thao tác reactive tham gia cùng transaction phải nằm trong cùng Reactor pipeline/context. Không gọi block() để ép reactive repository thành imperative bên trong transaction reactive. Nếu có cả imperative và reactive transaction manager, chỉ rõ manager phù hợp với method.

Có thể dùng TransactionalOperator để bọc pipeline:

~~~java
public Mono<BookView> createBook(CreateBookInput input) {
    Mono<BookView> work = bookRepository.save(Book.from(input))
            .flatMap(saved ->
                    inventoryRepository.initialize(saved.id())
                            .thenReturn(BookView.from(saved)));

    return work.as(transactionalOperator::transactional);
}
~~~

Đối với subscription trả Flux dài hạn, không mở một database transaction kéo dài theo toàn bộ stream event. Hãy thực hiện transaction ngắn cho từng thao tác ghi hoặc đọc cần consistency, sau đó phát event ra ngoài transaction.

## Side effect tới message broker và hệ thống bên ngoài

Một mutation có thể vừa ghi database vừa gửi email, gọi payment gateway hoặc publish message. Transaction database không tự đảm bảo hai hệ thống cùng commit.

Ví dụ không an toàn:

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.from(input));
    paymentClient.charge(order); // Gọi hệ thống bên ngoài.
    messageBroker.publish(new OrderPlaced(order.id()));
    return order;
}
~~~

Nếu database rollback sau khi payment hoặc message đã thành công, hệ thống bên ngoài vẫn giữ side effect. Nếu remote call chậm, transaction database còn giữ connection và lock lâu hơn.

### Transactional outbox

Một cách phổ biến là ghi outbox record cùng transaction với dữ liệu nghiệp vụ:

~~~java
@Transactional
public Order placeOrder(PlaceOrderInput input) {
    Order order = orderRepository.save(Order.from(input));
    outboxRepository.save(OutboxEvent.orderPlaced(order.id()));
    return order;
}
~~~

Một publisher riêng đọc outbox chưa gửi và phát message sau khi transaction commit. Sau khi gửi thành công, publisher đánh dấu record đã xử lý.

Ưu điểm:

- Order và outbox record commit hoặc rollback cùng nhau.
- Nếu process dừng sau commit, outbox record vẫn còn để publisher xử lý lại.
- Có thể retry việc publish mà không phải tạo lại order.

Publisher thường cần cơ chế idempotency vì message có thể được gửi lại khi lỗi xảy ra sau khi broker nhận message nhưng trước khi outbox được đánh dấu hoàn tất. Consumer nên nhận diện event ID đã xử lý.

### AFTER_COMMIT event listener

Với side effect nhẹ hoặc không yêu cầu bảo đảm giao nhận tuyệt đối, có thể dùng @TransactionalEventListener:

~~~java
@Component
public class BookCreatedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onBookCreated(BookCreated event) {
        notificationService.notifyBookCreated(event.bookId());
    }
}
~~~

Listener chạy sau khi transaction commit. Tuy nhiên, process có thể dừng sau commit nhưng trước khi listener hoàn tất; event in-memory không thay thế được outbox bền vững khi yêu cầu giao nhận tin cậy.

## Isolation, concurrency và idempotency

Transaction giúp nhóm thao tác và kiểm soát tính nhất quán, nhưng không tự giải quyết mọi xung đột đồng thời.

Ví dụ hai client cùng cập nhật một Book:

1. Cả hai đọc version 4.
2. Client A cập nhật và commit version 5.
3. Client B cố ghi dữ liệu dựa trên version 4.

Với optimistic locking, JPA entity có thể dùng @Version:

~~~java
@Entity
public class BookEntity {

    @Id
    private Long id;

    @Version
    private long version;

    private String title;
}
~~~

Nếu version đã thay đổi, lần ghi của client B có thể thất bại với optimistic locking exception. API nên chuyển lỗi đó thành conflict phù hợp, chẳng hạn mã VERSION_CONFLICT, để client tải lại dữ liệu và quyết định cập nhật lại.

Transaction cũng không tự chống việc client gửi cùng mutation nhiều lần do retry hoặc timeout. Với thao tác thanh toán/đặt hàng, cân nhắc idempotency key có unique constraint ở database. Khi nhận lại cùng key, server trả kết quả đã tạo trước đó thay vì thực hiện side effect lần nữa.

Chỉ tăng isolation level khi yêu cầu nghiệp vụ cần và đã đo tác động. Isolation cao hơn có thể làm tăng lock contention, retry hoặc deadlock. Cần có chiến lược xử lý lỗi transaction conflict thay vì giả định mọi request đều commit.

## Kiểm thử commit và rollback

Để kiểm tra transaction boundary, test phải đi qua Spring proxy và GraphQL resolver thật. Gọi method trực tiếp trên object tự tạo bằng new không kích hoạt transaction advice.

Với integration test, có thể khởi động application context và gửi GraphQL operation qua WebGraphQlTester hoặc HttpGraphQlTester. Sau request, đọc repository để xác minh trạng thái database.

Ví dụ minh họa test rollback khi audit service ném runtime exception:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.WebGraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.willThrow;

@SpringBootTest
class BookMutationTransactionTests {

    @Autowired
    WebGraphQlHandler handler;

    @Autowired
    BookRepository bookRepository;

    @MockitoBean
    AuditService auditService;

    WebGraphQlTester tester;

    @BeforeEach
    void setUp() {
        tester = WebGraphQlTester.builder(handler).build();
    }

    @Test
    void rollsBackBookWhenAuditFails() {
        willThrow(new AuditException("Audit unavailable"))
                .given(auditService).recordBookCreated(anyString());

        GraphQlTester.Response response = tester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            id
                            title
                        }
                    }
                }
                """)
                .variable("input", Map.of(
                        "title", "Transaction sample",
                        "authorId", "author-1",
                        "initialStock", 5))
                .execute();

        response.errors().satisfy(errors ->
                assertThat(errors).isNotEmpty());

        assertThat(bookRepository.existsByTitle("Transaction sample"))
                .isFalse();
    }
}
~~~

Các fixture và repository method trong ví dụ cần được thay bằng model thực tế của ứng dụng. Điểm quan trọng là test gửi operation qua handler đã cấu hình, để lời gọi controller đi qua Spring transaction proxy. WebGraphQlTester không kiểm tra HTTP filter hoặc network; nó đủ cho test transaction ở web GraphQL handler layer.

Không gắn @Transactional lên chính test method nếu mục tiêu là xác minh commit/rollback của mutation độc lập. Transaction test bên ngoài có thể khiến service tham gia transaction của test, che khuất thời điểm commit thực tế. Nếu test method đã có transaction, cần chủ động kiểm soát TestTransaction và trạng thái sau khi kết thúc transaction.

### Bộ trường hợp nên có

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Mutation thành công | Dữ liệu được commit và có thể đọc sau request |
| Runtime exception ở bước cuối | Các ghi trước đó trong cùng transaction bị rollback |
| Checked exception không có rollback rule | Transaction có thể commit theo mặc định; test xác minh đúng cấu hình |
| Checked exception có rollbackFor | Dữ liệu được rollback |
| Exception bị catch và trả payload lỗi | Transaction không tự rollback chỉ vì payload biểu diễn lỗi |
| Hai root mutation field trong một operation | Field đầu có thể commit dù field sau thất bại |
| Một mutation tổng hợp | Tất cả bước ghi cùng rollback khi một bước thất bại |
| Nested field lỗi sau khi mutation trả về | Transaction mutation đã commit vẫn không tự rollback |
| Outbox record | Dữ liệu nghiệp vụ và outbox cùng commit/rollback |
| Reactive mutation | Các thao tác trong pipeline cùng reactive transaction context |

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mutation ghi một phần dữ liệu | Mỗi repository call tự commit trong transaction riêng | Đặt transaction boundary quanh toàn bộ use case |
| Field mutation chạy tuần tự nhưng field đầu không rollback | Tuần tự không phải atomic transaction | Gộp thao tác vào một mutation và một transaction |
| @Transactional không có tác dụng | Method không được gọi qua Spring proxy hoặc thiếu transaction manager | Kiểm tra bean/proxy và cấu hình transaction manager |
| Nested field lỗi sau khi mutation đã ghi | Nested resolver chạy sau khi transaction mutation kết thúc | Trả DTO đã materialize hoặc thiết kế transaction riêng cho nested read |
| LazyInitializationException khi đọc nested field | Trả JPA entity có lazy association sau khi transaction đóng | Dùng DTO/projection hoặc fetch dữ liệu trong boundary phù hợp |
| Exception xảy ra nhưng dữ liệu vẫn commit | Checked exception không có rollback rule hoặc exception bị catch | Cấu hình rollbackFor và để exception thoát khỏi method |
| Audit commit dù mutation rollback | Audit dùng REQUIRES_NEW | Dùng REQUIRED nếu audit phải cùng atomic unit |
| Remote API thành công nhưng database rollback | Transaction local không bao gồm hệ thống bên ngoài | Dùng outbox, saga hoặc cơ chế bù trừ |
| Reactive mutation không rollback như mong đợi | Dùng sai transaction manager hoặc thao tác ra khỏi Reactor Context | Dùng ReactiveTransactionManager và giữ cùng reactive pipeline |
| Transaction kéo dài khi subscription mở | Bọc cả Flux dài hạn trong transaction | Dùng transaction ngắn theo từng event/operation |
| Hai client ghi đè dữ liệu của nhau | Không có concurrency control | Dùng optimistic locking, constraint hoặc lock phù hợp |
| Retry tạo đơn hàng/thanh toán trùng | Không có idempotency key | Lưu và kiểm tra idempotency key với unique constraint |

## Thực hành tổng hợp

Xây dựng mutation placeOrder cho API bán sách:

1. Khai báo Mutation.placeOrder(input) và input type gồm customer cùng danh sách item.
2. Viết controller method có @MutationMapping và @Transactional.
3. Tạo order, order item, reserve inventory và audit trong cùng transaction.
4. Kiểm tra các service con dùng cùng transaction manager và propagation REQUIRED.
5. Cố ý làm bước reserve inventory ném runtime exception; xác minh order và order item không còn trong database.
6. Thêm checked exception và cấu hình rollbackFor; xác minh rollback đúng.
7. Gửi operation có hai root mutation field và quan sát field đầu vẫn commit khi field sau lỗi.
8. Tạo một mutation tổng hợp để bảo đảm nhiều bước nghiệp vụ atomic.
9. Trả DTO thay vì JPA entity có lazy association; kiểm thử nested selection sau mutation.
10. Ghi outbox event cùng transaction và kiểm tra publisher xử lý sau commit.
11. Thêm idempotency key và kiểm thử client retry cùng request.
12. Với ứng dụng R2DBC, dùng ReactiveTransactionManager và kiểm tra rollback trong cùng Reactor pipeline.

Sau khi hoàn thành, hãy giải thích vì sao mutation root fields chạy tuần tự vẫn không có atomicity chung, vì sao nested resolver không thuộc transaction của mutation method và khi nào cần outbox thay cho gọi remote service trực tiếp.

## Ghi nhớ

GraphQL không định nghĩa database transaction. Các root field của mutation chạy tuần tự, nhưng thứ tự đó không tạo một transaction atomic cho toàn operation. Spring for GraphQL khuyến nghị đặt @Transactional trên mutation controller method để transaction bao quanh đúng một field; transaction kết thúc khi method trả về, trước khi nested field tiếp tục được phân giải. Nếu nhiều bước nghiệp vụ phải cùng commit hoặc rollback, hãy gộp chúng vào một mutation/use case duy nhất. Hiểu rõ rollback rule, propagation, AOP proxy và loại transaction manager. Transaction local không bao gồm remote side effect; dùng outbox khi cần giao nhận message tin cậy. Kiểm thử qua GraphQL handler thật và xác minh trạng thái database sau commit hoặc rollback.

## Tài liệu tham khảo

- [Spring for GraphQL – Data Integration: Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html)
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework – Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [GraphQL Specification – Mutation Execution](https://spec.graphql.org/September2026/#sec-Mutation)
