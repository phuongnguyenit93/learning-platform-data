# Ghép nhiều thao tác repository/client trong cùng một chuỗi

Trong ứng dụng Spring Data Neo4j (SDN) reactive, một use case thường cần nhiều thao tác graph: đọc node liên quan, lưu entity, tạo relationship hoặc ghi audit bằng Cypher. Những thao tác này cần được kết hợp thành một chuỗi Reactor duy nhất để cùng tham gia một reactive transaction.

Reactive transaction được quản lý qua Reactor Context, không dựa trên ThreadLocal như transaction imperative. Vì vậy, cách ghép publisher có ý nghĩa trực tiếp đến tính nguyên tử: các thao tác phải được trả về và nối tiếp trong cùng pipeline; gọi subscribe hoặc block thủ công có thể tách thao tác ra khỏi transaction đang quản lý.

Bài học này dùng ví dụ tạo đơn hàng: đọc Customer bằng repository, lưu Order bằng repository, ghi OrderEvent bằng ReactiveNeo4jClient và chỉ trả kết quả khi toàn bộ công việc hoàn tất.

## 1. Thành phần của một reactive transaction

Với stack reactive, SDN dùng ReactiveNeo4jTransactionManager để phối hợp transaction với reactive Neo4j Driver. Các repository reactive và ReactiveNeo4jClient phải sử dụng cùng cấu hình Driver và database để tham gia cùng transaction.

| Thành phần | Vai trò |
| --- | --- |
| ReactiveNeo4jRepository | Thực hiện CRUD và derived query dưới dạng Mono/Flux |
| ReactiveNeo4jClient | Chạy Cypher tùy chỉnh dưới dạng Mono/Flux |
| ReactiveNeo4jTransactionManager | Quản lý transaction reactive của Neo4j |
| Reactor Context | Mang transaction resource xuyên suốt subscription |
| Mono<T> | Publisher không hoặc một kết quả |
| Flux<T> | Publisher gồm không hoặc nhiều kết quả |

Khi dùng Spring Boot với cấu hình SDN reactive, transaction manager có thể được auto-configure. Nếu tự cấu hình, phải bảo đảm repository và client dùng cùng reactive Driver với ReactiveNeo4jTransactionManager.

Không dùng Neo4jClient imperative bên trong reactive transaction. Client imperative không tham gia reactive transaction context. Hãy dùng ReactiveNeo4jClient trong pipeline reactive.

## 2. Mô hình hóa use case

Giả sử hệ thống có Customer, Order và OrderEvent. Khi tạo đơn, ứng dụng cần:

1. Xác nhận Customer tồn tại.
2. Tạo và lưu Order có tham chiếu tới Customer.
3. Tạo OrderEvent bằng Cypher tùy chỉnh.
4. Trả OrderResult sau khi cả hai thao tác ghi hoàn tất.

Order có thể biểu diễn quan hệ với Customer bằng property @Relationship hoặc thông qua mô hình domain phù hợp của ứng dụng. Phần ví dụ tập trung vào cách phối hợp các thao tác repository/client; các constructor và factory method domain được rút gọn để dễ đọc.

Repository reactive:

~~~java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;

public interface CustomerRepository
        extends ReactiveNeo4jRepository<Customer, String> {
}

public interface OrderRepository
        extends ReactiveNeo4jRepository<Order, String> {
}
~~~

Các kiểu dữ liệu đầu vào và kết quả:

~~~java
public record CreateOrderCommand(
    String orderId,
    String customerId,
    String eventId,
    long totalCents
) {}

public record OrderResult(
    String orderId,
    String eventId
) {}
~~~

Ví dụ giả định Order.create(command, customer) tạo entity mới với ID do ứng dụng cấp và gắn Customer theo mô hình relationship đã khai báo.

## 3. Ghép repository và ReactiveNeo4jClient bằng flatMap

Đây là một service dùng @Transactional:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final CustomerRepository customerRepository;
    private final OrderRepository orderRepository;
    private final ReactiveNeo4jClient neo4jClient;

    public OrderService(
            CustomerRepository customerRepository,
            OrderRepository orderRepository,
            ReactiveNeo4jClient neo4jClient) {
        this.customerRepository = customerRepository;
        this.orderRepository = orderRepository;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public Mono<OrderResult> createOrder(CreateOrderCommand command) {
        return customerRepository.findById(command.customerId())
            .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(command.customerId())
            ))
            .flatMap(customer -> {
                Order order = Order.create(command, customer);

                return orderRepository.save(order)
                    .flatMap(savedOrder ->
                        neo4jClient.query("""
                                MATCH (order:Order {id: $orderId})
                                CREATE (event:OrderEvent {
                                    id: $eventId,
                                    type: "CREATED",
                                    createdAt: datetime()
                                })
                                CREATE (order)-[:HAS_EVENT]->(event)
                                RETURN event.id AS eventId
                                """)
                            .bind(savedOrder.getId()).to("orderId")
                            .bind(command.eventId()).to("eventId")
                            .fetchAs(String.class)
                            .mappedBy((typeSystem, record) ->
                                record.get("eventId").asString()
                            )
                            .one()
                            .switchIfEmpty(Mono.error(
                                new IllegalStateException("Không tạo được OrderEvent")
                            ))
                            .map(eventId -> new OrderResult(
                                savedOrder.getId(),
                                eventId
                            ))
                    );
            });
    }
}
~~~

Pipeline thực hiện theo thứ tự:

- findById phát Customer hoặc lỗi CustomerNotFoundException.
- flatMap nhận Customer rồi tạo Order.
- save phát Order đã lưu.
- flatMap tiếp theo chạy Cypher tạo event.
- one() phát event ID, map tạo OrderResult.

Vì mọi publisher đều được trả về từ cùng phương thức transactional, Spring có thể gắn các thao tác repository và client vào cùng reactive transaction. Nếu thao tác tạo event phát lỗi, lỗi truyền ngược qua pipeline và transaction có thể rollback cả việc lưu Order.

Điều kiện quan trọng là CustomerRepository, OrderRepository và ReactiveNeo4jClient phải dùng cùng reactive transaction infrastructure. Nếu một thành phần dùng Driver khác hoặc client imperative, không thể giả định nó tham gia transaction này.

## 4. Chọn operator theo quan hệ giữa các thao tác

Reactor cung cấp nhiều operator để ghép publisher. Hãy chọn theo phụ thuộc dữ liệu và thứ tự nghiệp vụ.

| Operator | Cách dùng | Ví dụ trong luồng dữ liệu |
| --- | --- | --- |
| flatMap | Chạy publisher tiếp theo dựa trên giá trị vừa phát | Tìm Customer rồi mới lưu Order |
| then | Chờ publisher trước hoàn tất, bỏ kết quả của nó rồi chạy publisher sau | Lưu Order rồi ghi audit |
| thenReturn | Chờ publisher hoàn tất rồi phát một giá trị đã có | Chạy lệnh Cypher ghi xong rồi trả Order |
| concatMap | Xử lý từng phần tử Flux theo thứ tự, tuần tự | Lần lượt xử lý danh sách lệnh ghi |
| map | Chuyển đổi đồng bộ một giá trị đã phát | Chuyển event ID thành OrderResult |
| onErrorResume | Chuyển lỗi thành một publisher khác | Chuyển lỗi kỹ thuật thành kết quả dự phòng khi phù hợp |

Ví dụ dùng thenReturn khi lệnh client chỉ cần ghi:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        neo4jClient.query("""
                MATCH (order:Order {id: $orderId})
                SET order.status = "CONFIRMED"
                """)
            .bind(saved.getId()).to("orderId")
            .run()
            .thenReturn(saved)
    );
~~~

run() trả publisher hoàn tất khi lệnh ghi kết thúc. thenReturn(saved) bỏ ResultSummary và phát entity đã lưu.

Khi thao tác sau cần dữ liệu từ thao tác trước, dùng flatMap. Khi chỉ cần chờ thao tác trước hoàn tất rồi chuyển sang publisher khác, dùng then hoặc thenReturn. map chỉ dành cho phép chuyển đổi đồng bộ, không dùng map để trả về một publisher lồng nhau.

## 5. Ghép nhiều thao tác độc lập và thao tác tuần tự

Không phải mọi thao tác đều có thể chạy song song. Nếu thao tác B cần ID hoặc kết quả từ thao tác A, phải dùng flatMap hoặc then để bảo đảm thứ tự.

~~~java
return customerRepository.findById(customerId)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(customerId)))
    .flatMap(customer ->
        orderRepository.save(Order.create(command, customer))
    )
    .flatMap(savedOrder ->
        writeAudit(savedOrder).thenReturn(savedOrder)
    );
~~~

Với Flux chứa nhiều phần tử cần ghi theo thứ tự, concatMap thường dễ kiểm soát hơn:

~~~java
import reactor.core.publisher.Flux;

return Flux.fromIterable(commands)
    .concatMap(command ->
        orderRepository.save(Order.from(command))
    )
    .collectList();
~~~

flatMap có thể cho phép nhiều inner publisher chạy đồng thời. Không dùng nó chỉ để tăng tốc các lệnh ghi phụ thuộc lẫn nhau hoặc cùng thao tác trên một trạng thái graph. Việc song song hóa có thể làm thay đổi thứ tự, tăng tranh chấp khóa hoặc khiến lỗi khó dự đoán.

Cũng không nên dùng Mono.when hoặc Mono.zip để chạy đồng thời các truy vấn trên cùng một reactive transaction chỉ vì các publisher không phụ thuộc dữ liệu trực tiếp. Hãy kiểm tra khả năng hỗ trợ của driver và transaction/session đang dùng; trong một transaction graph, ghép tuần tự thường rõ ràng và dễ kiểm soát hơn.

## 6. Dùng TransactionalOperator thay cho annotation

Ngoài @Transactional, có thể dùng TransactionalOperator để bao một publisher cụ thể. Cách này hữu ích khi ranh giới transaction cần được nhìn thấy ngay trong pipeline hoặc khi không thể dựa vào proxy annotation.

Tạo operator từ reactive transaction manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveTransactionConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveNeo4jTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Dùng operator ở service. Inject TransactionalOperator vào service bằng constructor như một dependency; ví dụ method sau tập trung vào cách bao publisher:

~~~java
public Mono<OrderResult> createOrder(CreateOrderCommand command) {
    Mono<OrderResult> work = customerRepository.findById(command.customerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(command.customerId())
        ))
        .flatMap(customer ->
            orderRepository.save(Order.create(command, customer))
        )
        .flatMap(saved ->
            writeAudit(saved, command)
                .thenReturn(new OrderResult(saved.getId(), command.eventId()))
        );

    return work.as(transactionalOperator::transactional);
}
~~~

TransactionalOperator tạo ranh giới transaction quanh toàn bộ publisher work. Chọn @Transactional hoặc TransactionalOperator cho một ranh giới cụ thể; tránh bọc lặp cả hai nếu không có chủ đích về propagation.

Với @Transactional, phương thức phải trả về reactive type như Mono hoặc Flux để Spring chọn reactive transaction management. Nếu phương thức trả void hoặc kiểu đồng bộ, annotation có thể sử dụng transaction manager imperative thay vì reactive manager.

## 7. Transaction được mở khi publisher được subscribe

Reactive publisher là lazy. Khi gọi phương thức service, phần lớn pipeline mới được mô tả; công việc truy vấn được thực thi khi publisher được subscribe.

Với @Transactional trên phương thức trả Mono hoặc Flux, transaction reactive được bắt đầu khi subscription đi qua interceptor. Transaction resource được lưu trong Reactor Context và được các operator Reactor chuẩn truyền theo subscription.

Lời gọi phải đi qua Spring proxy để interceptor áp dụng transaction. Nếu một method trong cùng class tự gọi method @Transactional khác bằng this, lời gọi nội bộ không đi qua proxy trong chế độ proxy mặc định. Hãy đặt transaction boundary ở method được gọi từ bean khác hoặc dùng TransactionalOperator trực tiếp.

Nếu ứng dụng có đồng thời transaction manager imperative và reactive, hãy xác nhận Spring đang chọn ReactiveNeo4jTransactionManager cho method reactive. Có thể chỉ định rõ bean transaction manager bằng thuộc tính transactionManager của @Transactional khi cấu hình ứng dụng có nhiều manager.

Điều này dẫn đến một số hệ quả:

- Trả publisher cho WebFlux hoặc tầng gọi để tầng đó subscribe.
- Không gọi subscribe() bên trong service để tự kích hoạt truy vấn.
- Không gọi block() để chờ kết quả trong luồng reactive.
- Không tạo một subscription độc lập cho thao tác cần tham gia transaction hiện tại.
- Nếu cùng một cold publisher được subscribe hai lần, nghiệp vụ có thể được thực thi hai lần; cần lưu ý idempotency.

Ví dụ sai:

~~~java
@Transactional
public Mono<Order> create(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
~~~

subscribe() tạo một luồng thực thi độc lập. Phương thức transactional có thể hoàn tất trước khi thao tác save được thực thi xong; thao tác save không còn được bảo đảm tham gia transaction dự kiến.

Cách đúng:

~~~java
@Transactional
public Mono<Order> create(Order order) {
    return orderRepository.save(order);
}
~~~

Publisher được trả về, nên Spring có thể quản lý vòng đời transaction theo quá trình subscribe, complete hoặc error.

## 8. Reactor Context và ranh giới transaction

Imperative transaction thường gắn với thread hiện tại. Reactive transaction gắn với Reactor Context của subscription. Do đó, chuyển luồng bằng publishOn hoặc subscribeOn không tự làm mất transaction context nếu sử dụng operator Reactor chuẩn.

Tuy nhiên, tạo subscription mới bằng subscribe(), gọi một API imperative hoặc chạy công việc ở một cơ chế thực thi không mang Reactor Context có thể tách thao tác khỏi transaction hiện tại.

Ví dụ, nếu một helper tự subscribe:

~~~java
public void writeAuditInBackground(String orderId) {
    reactiveNeo4jClient.query("""
            MATCH (order:Order {id: $id})
            CREATE (order)-[:HAS_EVENT]->(:OrderEvent {type: "CREATED"})
            """)
        .bind(orderId).to("id")
        .run()
        .subscribe();
}
~~~

Helper này không trả publisher cho caller. Caller không thể ghép công việc audit vào pipeline và transaction boundary. Hãy đổi chữ ký thành:

~~~java
import org.neo4j.driver.summary.ResultSummary;
import reactor.core.publisher.Mono;

public Mono<ResultSummary> writeAudit(String orderId) {
    return reactiveNeo4jClient.query("""
            MATCH (order:Order {id: $id})
            CREATE (order)-[:HAS_EVENT]->(:OrderEvent {type: "CREATED"})
            """)
        .bind(orderId).to("id")
        .run();
}
~~~

Khi đó caller có thể nối publisher bằng flatMap, then hoặc thenReturn và giữ công việc trong cùng transaction.

## 9. Lỗi và rollback trong reactive pipeline

Trong reactive transaction, một terminal error đi ra khỏi publisher transactional khiến Spring rollback transaction theo rollback rule. Nếu pipeline complete bình thường, transaction có thể commit.

Vị trí xử lý lỗi rất quan trọng. Nếu onErrorResume biến lỗi thành kết quả bình thường bên trong publisher được bọc transaction, transaction có thể commit. Nếu muốn rollback trước rồi mới chuyển lỗi thành response, hãy đặt xử lý fallback ở phía ngoài transaction boundary.

Ví dụ với TransactionalOperator:

~~~java
Mono<OrderResult> transactionalWork = createOrderWork(command)
    .as(transactionalOperator::transactional);

return transactionalWork
    .onErrorResume(InsufficientStockException.class, error ->
        Mono.just(OrderResult.rejected(error.getMessage()))
    );
~~~

Ở đây transactionalWork nhìn thấy lỗi và kết thúc transaction theo rollback rule. Sau đó onErrorResume bên ngoài mới chuyển lỗi thành response.

Nếu đặt onErrorResume trước as(transactionalOperator::transactional), operator có thể chỉ thấy publisher complete bình thường và commit các thay đổi đã thực hiện trước lỗi. Chỉ làm vậy nếu nghiệp vụ thực sự muốn giữ những thay đổi đó.

Đối với lỗi checked exception được bọc thành error signal, cần xác định exception type thực tế và rollback rule. Reactive transaction vẫn tuân theo rollback policy của Spring; không nên giả định mọi error signal đều có cùng chính sách nếu có cấu hình noRollbackFor.

## 10. Giới hạn của một transaction reactive

Một reactive transaction chỉ bao phủ các thao tác database tham gia cùng transaction manager và cùng reactive resource. Nó không tự bao phủ:

- Gửi email hoặc gọi HTTP service bên ngoài.
- Ghi file hoặc cập nhật hệ thống không tham gia transaction.
- Query qua Driver/client độc lập không dùng cùng transaction context.
- Công việc được tạo bằng subscription tách rời.
- Một publisher chỉ được mô tả nhưng không được nối vào publisher cuối cùng.

Nếu nghiệp vụ cần phát thông báo sau khi transaction commit, có thể ghi outbox node trong cùng transaction rồi xử lý thông báo bằng worker riêng. Cách này tránh gửi message khi transaction cuối cùng rollback.

Không dùng reactive transaction để giữ transaction mở trong lúc chờ một dịch vụ HTTP chậm nếu không cần thiết. Giữ transaction ngắn giúp giảm thời gian giữ lock và giảm tranh chấp trên graph.

## 11. Kiểm thử một chuỗi nhiều thao tác

Kiểm thử cần xác nhận cả kết quả nghiệp vụ và trạng thái graph sau commit/rollback. Với Reactor, StepVerifier giúp subscribe publisher và kiểm tra signal.

~~~java
StepVerifier.create(orderService.createOrder(command))
    .assertNext(result -> {
        assertThat(result.orderId()).isEqualTo(command.orderId());
        assertThat(result.eventId()).isEqualTo(command.eventId());
    })
    .verifyComplete();
~~~

Một số kịch bản nên kiểm tra:

1. Customer tồn tại: Order và OrderEvent đều được ghi.
2. Customer không tồn tại: publisher phát lỗi và không tạo Order.
3. Lưu Order thành công nhưng ghi event thất bại: cả hai thay đổi được rollback nếu cùng transaction.
4. Lỗi được chuyển thành fallback bên ngoài transaction: database đã rollback trước khi response fallback được phát.
5. Cùng command được subscribe nhiều lần: kiểm tra idempotency để tránh tạo Order hoặc event trùng.
6. Repository và ReactiveNeo4jClient cùng dùng reactive transaction manager và cùng Driver.
7. Publisher không bị subscribe thủ công trong service.

Unit test với mock hữu ích để kiểm tra thứ tự operator, nhưng integration test với Neo4j cần thiết để xác minh transaction thực sự rollback dữ liệu graph. Khi kiểm thử transaction, gọi service bean từ Spring context để annotation hoặc TransactionalOperator thực sự có hiệu lực.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Repository ghi xong nhưng client query không rollback cùng | Client dùng Driver hoặc transaction infrastructure khác | Dùng ReactiveNeo4jClient cùng reactive Driver và transaction manager |
| Service trả kết quả trước khi query ghi hoàn tất | Publisher bị bỏ qua hoặc không được nối vào chuỗi | Trả publisher từ flatMap/then |
| Transaction không bao phủ thao tác save | Gọi subscribe() thủ công hoặc gọi API imperative | Giữ toàn bộ thao tác trong cùng reactive pipeline |
| Phương thức @Transactional không mở reactive transaction | Method trả kiểu đồng bộ hoặc chọn nhầm transaction manager | Trả Mono/Flux và cấu hình ReactiveNeo4jTransactionManager |
| Dữ liệu vẫn commit sau khi có lỗi | onErrorResume đã biến error thành complete trước transaction boundary | Đặt fallback bên ngoài transactional publisher nếu cần rollback |
| Thao tác ghi chạy sai thứ tự | Dùng flatMap cho các thao tác phụ thuộc hoặc chạy song song | Dùng flatMap theo phụ thuộc, then hoặc concatMap |
| Một nghiệp vụ chạy nhiều lần | Publisher bị subscribe nhiều lần | Thiết kế idempotency và kiểm soát subscription |

## 13. Quy trình thiết kế một reactive transaction

1. Xác định toàn bộ thao tác graph cần nguyên tử.
2. Chọn reactive repository cho CRUD và ReactiveNeo4jClient cho Cypher tùy chỉnh.
3. Xác nhận các thành phần dùng chung reactive Driver và transaction manager.
4. Dùng flatMap khi thao tác sau phụ thuộc kết quả trước.
5. Dùng then/thenReturn khi chỉ cần chờ thao tác hoàn tất.
6. Dùng concatMap cho chuỗi xử lý tuần tự trên Flux.
7. Chọn @Transactional hoặc TransactionalOperator cho transaction boundary.
8. Trả publisher cuối cùng, không subscribe hoặc block bên trong service.
9. Đặt xử lý fallback ở vị trí phù hợp với chính sách rollback.
10. Kiểm thử cả commit, rollback và việc subscribe nhiều lần.

## 14. Bài tập tự kiểm tra

1. Vì sao reactive transaction sử dụng Reactor Context thay cho ThreadLocal?
2. Điều kiện nào để repository reactive và ReactiveNeo4jClient tham gia cùng một transaction?
3. Khi nào nên dùng flatMap, then và thenReturn?
4. Vì sao gọi subscribe() bên trong service có thể làm thao tác thoát khỏi transaction?
5. @Transactional reactive cần kiểu trả về nào để Spring dùng reactive transaction manager?
6. onErrorResume đặt trước và sau transaction boundary có thể tạo ra khác biệt gì?
7. Khi xử lý nhiều phần tử cần ghi tuần tự, vì sao concatMap thường dễ kiểm soát hơn flatMap?
8. Vì sao Mono hoặc Flux được subscribe hai lần có thể thực hiện nghiệp vụ hai lần?
9. Những side effect nào không được rollback cùng transaction Neo4j?

Khi hoàn thành bài học, bạn cần ghép được nhiều thao tác repository và client trong một Reactor chain, lựa chọn operator đúng theo thứ tự nghiệp vụ, và bảo đảm tất cả thao tác cần nguyên tử cùng tham gia reactive transaction. Đây là nền tảng để xây dựng service Spring Data Neo4j reactive có khả năng rollback nhất quán và không tạo subscription ngoài ý muốn.

## Tài liệu tham khảo

- [Spring Data Neo4j – Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html)
- [Spring Framework – Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Project Reactor – Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Data Neo4j – Reactive Repositories](https://docs.spring.io/spring-data/neo4j/reference/repositories/core-concepts.html)

