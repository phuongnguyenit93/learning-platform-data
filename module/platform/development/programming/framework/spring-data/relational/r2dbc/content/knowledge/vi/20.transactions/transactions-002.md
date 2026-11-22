# Cấu hình TransactionalOperator

Trong Spring Data R2DBC, giao dịch reactive có thể được quản lý theo hai cách: khai báo bằng annotation `@Transactional` hoặc điều khiển tường minh bằng `TransactionalOperator`. Operator phù hợp khi muốn xác định rõ publisher nào nằm trong một transaction, phối hợp nhiều thao tác repository/DatabaseClient hoặc chọn transaction definition theo từng use case.

`TransactionalOperator` không tự kết nối đến database và cũng không thay thế driver. Nó điều phối transaction thông qua một `ReactiveTransactionManager`. Với R2DBC, transaction manager thường là `R2dbcTransactionManager`, được cấu hình từ cùng `ConnectionFactory` mà Spring Data repositories và `DatabaseClient` đang sử dụng.

## 1. Các thành phần của reactive transaction

Một transaction reactive thường có các thành phần:

- **ConnectionFactory:** tạo hoặc cấp kết nối R2DBC.
- **R2dbcTransactionManager:** bắt đầu, commit và rollback transaction trên kết nối.
- **ReactiveTransactionManager:** interface mà Spring dùng để quản lý transaction reactive.
- **TransactionalOperator:** bao một publisher trong ranh giới transaction.
- **Repository / DatabaseClient / R2dbcEntityTemplate:** thực hiện câu lệnh database trong transaction context.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A[Service method]
    B[TransactionalOperator]
    C[ReactiveTransactionManager]
    D[R2dbcTransactionManager]
    E[ConnectionFactory]
    F[Spring Data Repository / DatabaseClient]
    G[Database]
    A --> B
    B --> C
    C --> D
    D --> E
    A --> F
    F --> E
    E --> G
~~~

Operator mở ranh giới transaction quanh publisher. Transaction manager quản lý kết nối và trạng thái giao dịch. Repository hoặc DatabaseClient tham gia transaction khi chúng sử dụng cùng hạ tầng kết nối mà transaction manager quản lý.

## 2. Cấu hình ReactiveTransactionManager cho R2DBC

Với một `ConnectionFactory`, transaction manager tiêu chuẩn của Spring Data R2DBC là `R2dbcTransactionManager`.

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    public ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

`R2dbcTransactionManager` quản lý một R2DBC `ConnectionFactory`. Khi transaction bắt đầu, nó lấy kết nối và gắn tài nguyên transaction vào Reactor Context để các thao tác Spring tham gia có thể sử dụng đúng kết nối.

Trong ứng dụng Spring Boot, auto-configuration có thể đã tạo transaction manager khi có R2DBC `ConnectionFactory`. Trước khi tự khai báo bean, hãy kiểm tra cấu hình hiện có của dự án và tránh tạo hai transaction manager cạnh tranh cho cùng một database. Nếu Spring Boot đã cung cấp manager phù hợp, có thể dùng trực tiếp bean đó.

Nếu dùng connection pool, hãy bảo đảm transaction manager và repositories dùng cùng một `ConnectionFactory` đã được cấu hình cho pool. Việc dùng hai factory khác nhau có thể khiến thao tác repository không tham gia transaction mà operator đang quản lý.

## 3. Khai báo TransactionalOperator thành bean

Sau khi có `ReactiveTransactionManager`, có thể tạo operator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TransactionOperatorConfiguration {

    @Bean
    public TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring sẽ inject operator vào service qua constructor:

~~~java
@Service
public class OrderService {

    private final TransactionalOperator transactionalOperator;

    public OrderService(TransactionalOperator transactionalOperator) {
        this.transactionalOperator = transactionalOperator;
    }
}
~~~

Tạo operator một lần thành bean thường phù hợp khi ứng dụng dùng một transaction manager và một bộ transaction definition mặc định. Nếu có nhiều database hoặc cần các chính sách transaction khác nhau, có thể tạo các operator tương ứng với manager/definition phù hợp và đặt tên bean rõ ràng.

## 4. Cấu hình TransactionalOperator trực tiếp

Nếu chỉ cần dùng operator trong một cấu hình hoặc thành phần cụ thể, có thể tạo trực tiếp:

~~~java
TransactionalOperator operator =
        TransactionalOperator.create(transactionManager);
~~~

Hoặc tạo operator với một `TransactionDefinition`:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setName("order-write");
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(10);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Các thiết lập trong ví dụ:

- `name`: tên giao dịch hỗ trợ chẩn đoán hoặc logging tùy hạ tầng.
- `isolationLevel`: mức cô lập mong muốn.
- `timeout`: giới hạn thời gian transaction theo đơn vị giây trong `DefaultTransactionDefinition`.

Giá trị isolation phải được database hỗ trợ. Timeout transaction không nhất thiết giống statement timeout hoặc HTTP request timeout; mỗi lớp có cơ chế và phạm vi riêng. Hãy kiểm tra khả năng hỗ trợ của database, driver và transaction manager đang dùng.

## 5. Các thuộc tính trong TransactionDefinition

`TransactionDefinition` mô tả chính sách của một transaction:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Propagation | Cách transaction mới tham gia hoặc tạo transaction so với transaction hiện có |
| Isolation | Mức cô lập giữa các transaction đồng thời |
| Timeout | Thời gian tối đa được cấu hình cho transaction |
| Read-only | Gợi ý transaction chỉ đọc |
| Name | Tên transaction phục vụ nhận diện/chẩn đoán |

Ví dụ cấu hình read-only:

~~~java
DefaultTransactionDefinition readDefinition =
        new DefaultTransactionDefinition();
readDefinition.setReadOnly(true);
readDefinition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);
readDefinition.setTimeout(5);

TransactionalOperator readOnlyOperator =
        TransactionalOperator.create(
                transactionManager,
                readDefinition
        );
~~~

`readOnly = true` là một chỉ dẫn cho transaction manager và hạ tầng database. Mức độ database thực thi hoặc từ chối lệnh ghi trong transaction read-only phụ thuộc driver và hệ quản trị; không dùng thuộc tính này thay cho kiểm tra quyền truy cập.

Propagation mặc định của `DefaultTransactionDefinition` thường là `PROPAGATION_REQUIRED`: tham gia transaction hiện có nếu phù hợp, hoặc tạo transaction mới nếu chưa có. Các chế độ khác như `REQUIRES_NEW` hoặc `SUPPORTS` cần được chọn theo nghiệp vụ và khả năng của transaction manager. Không nên chọn propagation chỉ để “sửa” một lỗi transaction mà chưa hiểu ranh giới gọi.

## 6. Dùng transactional(Mono) để bao một thao tác reactive

Cách dùng trực tiếp nhất là truyền một publisher vào `transactional(...)`:

~~~java
public Mono<Customer> updateCustomerName(
        Long customerId,
        String newName) {

    Mono<Customer> work = customerRepository.findById(customerId)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)
            ))
            .map(customer -> new Customer(
                    customer.id(),
                    newName,
                    customer.email()
            ))
            .flatMap(customerRepository::save);

    return transactionalOperator.transactional(work);
}
~~~

Operator bắt đầu transaction khi publisher được subscribe, cho phép các thao tác trong pipeline tham gia cùng transaction và commit khi publisher hoàn tất bình thường. Nếu publisher phát lỗi, transaction được rollback theo chính sách rollback của operator/transaction manager.

Đoạn code không cần gọi `beginTransaction()`, `commitTransaction()` hoặc `rollbackTransaction()` bằng tay. Những bước đó thuộc trách nhiệm của transaction manager.

## 7. Dùng một transaction cho nhiều thao tác repository

Một use case thường cần nhiều lệnh ghi phải thành công cùng nhau. Ví dụ tạo đơn hàng, lưu các dòng hàng và tạo bản ghi audit:

~~~java
public Mono<PurchaseOrder> createOrder(
        PurchaseOrder order,
        List<OrderLine> lines) {

    Mono<PurchaseOrder> work = orderRepository.save(order)
            .flatMap(savedOrder ->
                    orderLineRepository.saveAll(
                            lines.stream()
                                    .map(line -> new OrderLine(
                                            null,
                                            savedOrder.id(),
                                            line.productId(),
                                            line.quantity()
                                    ))
                                    .toList()
                    )
                    .thenReturn(savedOrder)
            )
            .flatMap(savedOrder ->
                    auditRepository.save(new OrderAudit(
                            null,
                            savedOrder.id(),
                            "ORDER_CREATED"
                    ))
                    .thenReturn(savedOrder)
            );

    return transactionalOperator.transactional(work);
}
~~~

Các thao tác lưu đơn hàng, dòng hàng và audit nằm trong một pipeline được bao bởi cùng operator. Nếu một bước phát lỗi trước khi transaction hoàn tất, các thay đổi trong transaction có thể được rollback cùng nhau.

Ví dụ dùng `List.stream()` để minh họa tạo các dòng hàng. Nếu đầu vào rất lớn, không nên materialize toàn bộ dữ liệu trong bộ nhớ; hãy dùng publisher và chiến lược batch phù hợp.

Điều kiện quan trọng là các repository phải tham gia cùng transaction manager và cùng database connection factory. Nếu một repository được cấu hình với factory khác, thao tác đó có thể nằm ngoài transaction.

## 8. Dùng execute khi cần truy cập trạng thái transaction

`TransactionalOperator.execute(...)` cho phép callback nhận `ReactiveTransaction`. Cách này hữu ích khi cần đánh dấu rollback-only hoặc thao tác với trạng thái transaction:

~~~java
public Mono<Customer> createCustomer(Customer customer) {
    return transactionalOperator.execute(status ->
            customerRepository.save(customer)
                    .onErrorResume(error -> {
                        status.setRollbackOnly();
                        return Mono.error(error);
                    })
    ).singleOrEmpty();
}
~~~

`execute` trả về `Flux<T>`, vì vậy nếu callback phát tối đa một phần tử và service cần `Mono<T>`, có thể chuyển thành `singleOrEmpty()`. Nếu callback phát nhiều phần tử, giữ kết quả dạng `Flux<T>`.

Thông thường không cần gọi `setRollbackOnly()` khi lỗi được truyền ra khỏi callback: operator sẽ thấy tín hiệu lỗi và rollback. Phương thức này hữu ích khi logic cần đánh dấu rollback-only một cách tường minh hoặc khi ứng dụng xử lý lỗi bên trong callback nhưng vẫn muốn transaction rollback.

Ví dụ dưới đây cố ý phục hồi lỗi thành kết quả rỗng nhưng vẫn đánh dấu transaction rollback:

~~~java
return transactionalOperator.execute(status ->
        customerRepository.save(customer)
                .onErrorResume(error -> {
                    status.setRollbackOnly();
                    log.warn("Customer write failed", error);
                    return Mono.empty();
                })
).then();
~~~

Nếu không gọi `setRollbackOnly()` trong trường hợp đã nuốt lỗi bên trong callback, operator có thể chỉ nhìn thấy publisher hoàn tất bình thường và commit transaction. Vì vậy, chỉ phục hồi lỗi bên trong transaction khi đã xác định rõ trạng thái commit/rollback mong muốn.

## 9. Transaction bắt đầu khi publisher được subscribe

Reactive publisher thường lazy. Tạo một publisher chưa có nghĩa câu lệnh SQL đã chạy hoặc transaction đã bắt đầu:

~~~java
Mono<Customer> result = transactionalOperator.transactional(
        customerRepository.save(customer)
);
~~~

Transaction bắt đầu khi có subscriber tiêu thụ `result`. Trong WebFlux, framework subscribe khi xử lý request; trong test, `StepVerifier` subscribe khi xác minh publisher.

Không gọi `subscribe()` bên trong service để “khởi động” transaction:

~~~java
// Không dùng cách này trong service reactive.
transactionalOperator.transactional(
        customerRepository.save(customer)
).subscribe();
~~~

Việc tự subscribe tạo một luồng thực thi tách rời khỏi publisher mà caller đang theo dõi. Caller không còn phối hợp đúng thời điểm hoàn tất, lỗi hoặc cancellation; transaction cũng có thể kết thúc độc lập với luồng xử lý chính.

Hãy trả publisher từ service và để framework ở ranh giới ứng dụng quyết định thời điểm subscribe.

## 10. Reactor Context và kết nối của transaction

Reactive transaction của Spring gắn tài nguyên vào Reactor Context thay vì dựa vào ThreadLocal như mô hình đồng bộ truyền thống. Vì vậy:

- Các thao tác trong cùng pipeline có thể tham gia transaction dù chúng chạy trên các thread khác nhau.
- `publishOn` hoặc `subscribeOn` không tự làm mất transaction context khi pipeline Reactor được nối đúng cách.
- Tạo subscription độc lập bằng `subscribe()` có thể tách thao tác khỏi context transaction ban đầu.
- Chuyển sang API imperative hoặc một callback ngoài Reactor có thể làm mất ngữ cảnh nếu không truyền tiếp context phù hợp.

Sơ đồ luồng:

~~~mermaid
sequenceDiagram
    participant Caller
    participant Operator as TransactionalOperator
    participant TM as R2dbcTransactionManager
    participant Repo as Repository / DatabaseClient
    participant DB as Database
    Caller->>Operator: Subscribe publisher
    Operator->>TM: Begin transaction
    TM->>DB: Acquire connection and begin
    TM-->>Operator: Bind connection in Reactor Context
    Operator->>Repo: Execute first query
    Repo->>DB: SQL on transaction connection
    DB-->>Repo: Result
    Operator->>Repo: Execute next query
    Repo->>DB: SQL on same transaction connection
    DB-->>Repo: Result
    Operator->>TM: Commit on successful completion
    TM->>DB: COMMIT
    Operator-->>Caller: Complete
~~~

Các repository và `DatabaseClient` được cấu hình theo cơ chế Spring có thể tìm và dùng connection đã gắn trong context. Nếu tự lấy kết nối trực tiếp bằng driver API mà bỏ qua cơ chế quản lý kết nối của Spring, thao tác đó có thể không tham gia transaction hiện tại.

## 11. Dùng cùng ConnectionFactory cho transaction manager và repository

Transaction manager R2DBC quản lý một `ConnectionFactory`. Để các lệnh trong transaction dùng cùng kết nối:

- `R2dbcTransactionManager` phải được tạo từ factory của database cần giao dịch.
- Repository và `DatabaseClient` phải sử dụng factory tương ứng.
- Nếu dùng pool, các thành phần cần dùng cùng factory đã được bọc bởi pool.
- Không tạo một factory mới độc lập trong service cho từng truy vấn.

Ví dụ cấu hình sai về mặt kiến trúc là transaction manager dùng factory A nhưng một `DatabaseClient` được tạo thủ công với factory B. Hai thao tác có thể dùng hai kết nối và không cùng commit/rollback.

Với nhiều database, mỗi database thường cần factory và transaction manager riêng. Một `TransactionalOperator` chỉ điều phối transaction của manager được truyền vào. Nó không tự tạo transaction phân tán nguyên tử giữa hai database độc lập.

## 12. Rollback khi publisher phát lỗi

Khi publisher trong transaction phát lỗi và lỗi truyền ra khỏi operator, transaction được rollback:

~~~java
public Mono<Void> createThenFail(Customer customer) {
    Mono<Void> work = customerRepository.save(customer)
            .then(Mono.error(
                    new IllegalStateException("Simulated failure")
            ));

    return transactionalOperator.transactional(work);
}
~~~

Trong ví dụ, câu lệnh save có thể đã chạy trên database, nhưng transaction chưa commit. Lỗi tiếp theo làm operator rollback transaction, nên hàng mới không được lưu lại sau khi rollback thành công.

Không nên chuyển lỗi thành một giá trị thành công trước khi transaction manager nhận được tín hiệu lỗi nếu mục tiêu là rollback. Nếu cần xử lý lỗi và vẫn rollback, dùng `setRollbackOnly()` trong callback `execute` hoặc để lỗi truyền ra ngoài operator rồi phục hồi ở phía ngoài:

~~~java
return transactionalOperator.transactional(work)
        .onErrorResume(error -> {
            log.error("Transaction rolled back", error);
            return Mono.empty();
        });
~~~

Ở cách thứ hai, `onErrorResume` nằm ngoài operator. Operator đã quan sát lỗi và thực hiện rollback trước khi tầng ngoài phục hồi publisher.

## 13. Rollback-only và xử lý lỗi nghiệp vụ

Không phải mọi lỗi đều cần làm transaction rollback. Có những luồng cần ghi nhận một trạng thái nghiệp vụ rồi hoàn tất bình thường; cũng có trường hợp lỗi được xử lý bên trong transaction nhưng các thao tác trước đó không còn được phép commit.

Khi dùng `execute`, có thể gọi:

~~~java
status.setRollbackOnly();
~~~

Điều này đánh dấu transaction hiện tại phải rollback khi callback kết thúc. Nếu callback hoàn tất bình thường nhưng trạng thái đã được đánh dấu rollback-only, transaction manager sẽ không commit các thay đổi như bình thường.

Hãy phân biệt:

- **Phát lỗi ra ngoài operator:** operator nhận lỗi và rollback theo quy tắc.
- **Phục hồi lỗi bên trong callback:** publisher có thể hoàn tất bình thường; nếu muốn rollback vẫn phải đánh dấu rollback-only.
- **Đánh dấu rollback-only:** yêu cầu transaction không commit dù callback có thể hoàn tất.

Chỉ dùng rollback-only khi nghiệp vụ thực sự cần giữ transaction mở để hoàn thành logic xử lý lỗi. Nếu không, truyền lỗi ra ngoài thường đơn giản và dễ hiểu hơn.

## 14. Cancellation và transaction trên Flux

Transaction reactive được giữ trong suốt thời gian publisher được tiêu thụ. Với `Mono`, thời gian thường ngắn. Với `Flux` phát nhiều phần tử, transaction có thể mở cho đến khi luồng hoàn tất.

Nếu subscriber hủy subscription, chẳng hạn client HTTP ngắt kết nối hoặc pipeline dùng `take(1)`, transaction operator nhận tín hiệu cancellation và thực hiện rollback theo hành vi của nó.

Ví dụ:

~~~java
Flux<Customer> stream = transactionalOperator.transactional(
        customerRepository.findAll()
);
~~~

Nếu consumer đọc hết Flux, transaction có thể hoàn tất và commit. Nếu consumer hủy trước khi Flux hoàn tất, transaction có thể bị rollback. Vì vậy, không nên bọc một luồng đọc rất dài hoặc vô hạn trong transaction chỉ để giữ transaction context trong toàn bộ thời gian client tiêu thụ dữ liệu.

Với truy vấn streaming lớn, hãy cân nhắc:

- Phân trang thành các đơn vị đọc ngắn.
- Không giữ transaction lâu hơn yêu cầu nhất quán.
- Tránh để tốc độ client quyết định thời gian giữ connection.
- Xác định rõ cancellation có nên làm rollback toàn bộ công việc hay không.

## 15. Cấu hình isolation level

Isolation level quy định mức độ một transaction nhìn thấy thay đổi của transaction khác. Các mức phổ biến:

| Isolation level | Ý nghĩa tổng quát |
| --- | --- |
| READ_UNCOMMITTED | Có thể cho phép đọc dữ liệu chưa commit nếu database hỗ trợ |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit |
| REPEATABLE_READ | Bảo đảm các lần đọc lại cùng hàng ổn định theo semantics của database |
| SERIALIZABLE | Mức cô lập cao, hạn chế các hiện tượng cạnh tranh hơn nhưng có thể giảm concurrency |
| DEFAULT | Dùng mức mặc định của database/transaction manager |

Ví dụ:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ
);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Không phải database nào cũng triển khai các mức cô lập giống nhau. Một số hệ quản trị ánh xạ hoặc nâng mức isolation theo cách riêng. Hãy kiểm tra tài liệu database và đo ảnh hưởng đến khóa, contention và hiệu năng trước khi áp dụng.

Isolation level không thay thế constraint. Ví dụ, unique constraint vẫn là cách bảo đảm không có hai hàng cùng một khóa duy nhất trong mọi transaction cạnh tranh.

## 16. Timeout, read-only và propagation

Có thể tạo operator chuyên biệt cho một nhóm use case:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setName("report-query");
definition.setReadOnly(true);
definition.setTimeout(5);
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);

TransactionalOperator reportOperator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Một số lưu ý:

- Timeout transaction là giới hạn của transaction manager; nó không nhất thiết tự hủy mọi truy vấn SQL ở cùng thời điểm.
- Read-only có thể là hint và mức enforce phụ thuộc database/driver.
- Propagation xác định transaction tham gia hay tạo mới. Chọn `REQUIRES_NEW` có thể tạo ranh giới độc lập khi manager hỗ trợ, nhưng làm thay đổi semantics commit/rollback.
- Transaction definition cần nhất quán với yêu cầu nghiệp vụ và khả năng database.

Không tạo quá nhiều operator chỉ khác một thuộc tính nhỏ nếu không cần. Đặt tên bean và cấu hình rõ ràng để tránh service vô tình dùng nhầm chính sách.

## 17. TransactionalOperator so với @Transactional

Hai cách tiếp cận có thể dùng cùng `ReactiveTransactionManager`, nhưng cách biểu đạt khác nhau:

| Tiêu chí | TransactionalOperator | @Transactional |
| --- | --- | --- |
| Cách dùng | Bao publisher bằng code | Đánh dấu phương thức/class |
| Phạm vi | Publisher được truyền vào operator | Phương thức được quản lý bởi proxy/AOP |
| Điều khiển rollback-only | Có thể dùng callback `execute` và transaction status | Thường dùng exception hoặc TransactionAspectSupport theo ngữ cảnh phù hợp |
| Transaction definition động | Có thể tạo operator với definition cụ thể | Có thể cấu hình annotation attributes |
| Phù hợp | Ranh giới transaction cần thể hiện trong pipeline | Quy tắc transaction ổn định theo phương thức |

Ví dụ annotation:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Ví dụ operator:

~~~java
public Mono<Order> createOrder(Order order) {
    return transactionalOperator.transactional(
            orderRepository.save(order)
    );
}
~~~

Không cần bọc cùng một publisher bằng cả `@Transactional` và `TransactionalOperator` nếu không có chủ đích rõ ràng. Transaction lồng nhau có thể tham gia transaction hiện có theo propagation mặc định hoặc tạo ranh giới mới nếu cấu hình yêu cầu; việc kết hợp không rõ ràng làm khó hiểu commit/rollback.

Programmatic operator không yêu cầu bật proxy annotation transaction. Nếu dùng `@Transactional`, cần bảo đảm declarative transaction management được kích hoạt và lời gọi đi qua proxy Spring.

## 18. Transaction không bao trùm lời gọi HTTP hoặc message broker

R2DBC transaction manager quản lý transaction của một resource database. Nó không tự động làm cho lời gọi HTTP, gửi email hoặc publish message vào broker trở thành một phần nguyên tử của transaction database.

Ví dụ không nên giữ transaction mở trong lúc gọi dịch vụ từ xa:

~~~java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .flatMap(savedOrder ->
                        paymentClient.charge(savedOrder)
                                .thenReturn(savedOrder)
                )
);
~~~

Đoạn code trên giữ transaction database trong khi chờ network call. Nếu dịch vụ thanh toán chậm, kết nối database và transaction có thể bị giữ lâu. Nếu payment thành công nhưng transaction database rollback, hai hệ thống có thể lệch trạng thái.

Với nghiệp vụ cần phối hợp database và message, có thể dùng transactional outbox: lưu dữ liệu nghiệp vụ và outbox event trong cùng database transaction; một tiến trình riêng đọc outbox rồi gửi message. Với quy trình nhiều dịch vụ, cân nhắc saga và thao tác bù trừ theo yêu cầu.

## 19. Kiểm thử commit và rollback bằng StepVerifier

Integration test cần xác nhận cả kết quả publisher và trạng thái dữ liệu sau transaction.

Ví dụ kiểm tra rollback khi pipeline phát lỗi:

~~~java
@SpringBootTest
class CustomerTransactionTest {

    @Autowired
    CustomerService customerService;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void shouldRollbackWhenWorkFails() {
        Customer customer =
                new Customer(null, "Test", "test@example.com");

        StepVerifier.create(customerService.createThenFail(customer))
                .expectError(IllegalStateException.class)
                .verify();

        StepVerifier.create(
                customerRepository.findByEmail("test@example.com")
        )
                .verifyComplete();
    }
}
~~~

Test giả định service `createThenFail` lưu customer rồi phát lỗi trong cùng operator. Sau rollback, truy vấn bên ngoài transaction xác nhận không còn hàng.

Khi viết integration test:

- Dùng database và driver phù hợp với môi trường triển khai.
- Không chỉ kiểm tra exception; hãy truy vấn lại dữ liệu để xác nhận rollback.
- Đảm bảo truy vấn xác minh chạy sau khi transaction test đã kết thúc.
- Kiểm tra trường hợp commit thành công và nhiều thao tác cùng transaction.
- Kiểm tra cancellation nếu use case có publisher dài và hành vi hủy là quan trọng.

Mock repository không thể xác nhận transaction manager thực sự rollback kết nối database.

## 20. Các lỗi cấu hình thường gặp

1. **Không có ReactiveTransactionManager.** Operator không thể bắt đầu transaction nếu không có manager phù hợp.
2. **Transaction manager dùng ConnectionFactory khác repository.** Các thao tác có thể không tham gia cùng transaction.
3. **Tạo operator nhưng không dùng nó để bao publisher.** Chỉ inject hoặc khởi tạo operator không tự tạo transaction.
4. **Tự gọi subscribe() trong service.** Subscription tách khỏi luồng mà caller quản lý.
5. **Gọi block() giữa pipeline.** Làm mất lợi ích reactive và có thể phá vỡ cách phối hợp context.
6. **Nuốt lỗi bên trong callback execute.** Operator có thể thấy hoàn tất bình thường; cần đánh dấu rollback-only nếu vẫn muốn rollback.
7. **Cho rằng mọi lỗi đều tự rollback sau khi đã phục hồi.** Vị trí của onErrorResume so với operator quyết định operator có quan sát lỗi hay không.
8. **Giữ transaction mở trong Flux dài.** Cancellation có thể rollback và kết nối bị giữ trong suốt thời gian tiêu thụ.
9. **Dùng readOnly như cơ chế bảo mật.** Đây không thay thế quyền database hoặc authorization.
10. **Cấu hình timeout không phối hợp với HTTP/SQL timeout.** Một tầng có thể hết hạn trước tầng còn lại.
11. **Kỳ vọng transaction bao trùm hai database độc lập.** Một R2DBC transaction manager chỉ quản lý resource mà nó được cấu hình.
12. **Kết hợp annotation và operator không có chủ đích.** Có thể tạo transaction lồng nhau khó dự đoán.

## Quy trình cấu hình và sử dụng

1. Xác định `ConnectionFactory` mà Spring Data repositories và `DatabaseClient` sử dụng.
2. Bảo đảm có một `ReactiveTransactionManager` phù hợp, thường là `R2dbcTransactionManager`.
3. Tạo bean `TransactionalOperator` bằng `TransactionalOperator.create(transactionManager)`.
4. Inject operator vào service cần quản lý transaction tường minh.
5. Nối toàn bộ thao tác database trong một publisher.
6. Bao publisher bằng `transactional(...)` hoặc dùng `execute(...) ` khi cần truy cập transaction status.
7. Trả publisher cho caller; không tự subscribe hoặc block.
8. Kiểm tra commit, rollback, lỗi và cancellation bằng integration test.

`TransactionalOperator` cung cấp cách quản lý transaction reactive theo ranh giới publisher. Nó sử dụng `ReactiveTransactionManager` để quản lý kết nối, commit và rollback; với R2DBC, transaction manager phải dùng cùng `ConnectionFactory` với repository và DatabaseClient. Khi cấu hình đúng và toàn bộ thao tác nằm trong cùng pipeline, ứng dụng có thể phối hợp nhiều câu lệnh database thành một đơn vị giao dịch, đồng thời giữ nguyên mô hình reactive và xử lý lỗi/cancellation theo quy tắc transaction.
