# Giới hạn giao dịch giữa nhiều nguồn dữ liệu và dịch vụ

Một nghiệp vụ trong ứng dụng reactive có thể đọc và ghi nhiều nguồn: cập nhật đơn hàng trong cơ sở dữ liệu, giữ chỗ tồn kho ở một dịch vụ khác, ghi nhận thanh toán qua cổng bên ngoài và phát sự kiện cho hệ thống vận chuyển. Mỗi thao tác có thể trả về Mono hoặc Flux, nhưng việc ghép các Publisher thành một pipeline không tự tạo ra một giao dịch ACID chung.

Thiết kế đúng cần xác định rõ ranh giới nào được bảo vệ bởi một transaction cục bộ, nguồn nào có thể tham gia cùng transaction, và cách xử lý khi một dịch vụ hoàn tất còn dịch vụ khác thất bại. Trong hệ sinh thái Java reactive, Spring quản lý transaction R2DBC qua Reactor Context; còn các nghiệp vụ trải qua nhiều database hoặc service thường cần Outbox, Saga, idempotency và cơ chế phục hồi.

## 1. Transaction ACID có phạm vi hữu hạn

Transaction cơ sở dữ liệu cung cấp một ranh giới để nhóm nhiều thao tác đọc/ghi thành một đơn vị. Nếu transaction commit, các thay đổi được xác nhận theo chính sách của database; nếu rollback, các thay đổi thuộc transaction đó bị hủy.

Bốn thuộc tính ACID thường được nhắc đến:

- **Atomicity:** các thay đổi trong transaction được commit hoặc rollback như một đơn vị.
- **Consistency:** transaction phải giữ các ràng buộc dữ liệu mà ứng dụng và database đặt ra.
- **Isolation:** các transaction đồng thời quan sát và ảnh hưởng lẫn nhau theo mức cô lập đã chọn.
- **Durability:** dữ liệu đã commit được lưu bền vững theo cam kết của database.

Phạm vi của transaction phụ thuộc vào transaction manager và các resource mà nó quản lý. Một transaction R2DBC thường gắn với một connection factory và một connection được bind vào Reactor Context của subscription. Nó không tự mở rộng sang một database khác, HTTP service, message broker hoặc payment gateway.

Ví dụ, đoạn pipeline sau chỉ là chuỗi xử lý bất đồng bộ:

~~~java
Mono<Void> workflow =
    orderRepository.save(order)
        .then(inventoryClient.reserve(order))
        .then(paymentClient.charge(order));
~~~

Nếu bước thanh toán lỗi, việc trả lỗi xuống subscriber không tự động xóa reservation đã được tạo ở inventory service hoặc hoàn tác bản ghi order đã commit. Các Publisher chỉ mô tả thứ tự và kết quả của các thao tác; chúng không tạo một transaction phân tán.

## 2. Transaction reactive cục bộ với R2DBC

Trong Spring, transaction reactive thường dùng ReactiveTransactionManager, ví dụ R2dbcTransactionManager, cùng TransactionalOperator hoặc @Transactional trên phương thức trả về Publisher.

Một cấu hình điển hình:

~~~java
@Configuration
class DatabaseConfiguration {
    @Bean
    R2dbcTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

R2dbcTransactionManager quản lý transaction cho connection được lấy từ ConnectionFactory. TransactionalOperator bao quanh Publisher để bắt đầu transaction khi subscribe, commit khi Publisher hoàn tất bình thường và rollback khi Publisher lỗi hoặc bị hủy theo chính sách của transaction manager.

Ví dụ cập nhật một đơn hàng và ghi audit trong cùng database:

~~~java
Mono<Order> updateOrder(Order order) {
    Mono<Order> work = orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.save(AuditRecord.forOrder(saved))
                .thenReturn(saved)
        );

    return transactionalOperator.transactional(work);
}
~~~

Nếu auditRepository.save thất bại, lỗi thoát khỏi Publisher được bao bởi operator và transaction có thể rollback cả thao tác lưu order lẫn audit, miễn là cả hai repository dùng cùng transaction manager và cùng connection factory.

Các thao tác phải nằm trong cùng subscription và sử dụng resource mà transaction manager quản lý. Nếu một repository dùng datasource khác hoặc tự tạo connection độc lập, nó không tự động tham gia transaction này.

Các kiểu Order, AuditRecord, repository và service trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa; những đoạn mã rút gọn tập trung vào ranh giới transaction và có thể cần thêm import theo dự án.

## 3. Dùng @Transactional cho phương thức reactive

Spring hỗ trợ @Transactional với phương thức trả về Mono hoặc Flux khi ứng dụng cấu hình reactive transaction manager phù hợp:

~~~java
@Service
class OrderService {
    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Order> update(Order order) {
        return orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.save(AuditRecord.forOrder(saved))
                    .thenReturn(saved)
            );
    }
}
~~~

Với reactive transaction, transaction gắn với subscription thông qua Reactor Context. Phương thức trả về Publisher; transaction được thực thi khi Publisher được subscribe. Vì vậy, không nên gọi subscribe() bên trong phương thức transactional rồi trả về ngay: subscription tách rời có thể chạy ngoài phạm vi transaction do proxy quản lý.

Cần gọi phương thức qua Spring proxy để annotation được áp dụng. Self-invocation, tức một phương thức trong cùng bean gọi trực tiếp phương thức @Transactional khác, thường không đi qua proxy và có thể khiến transaction annotation không có hiệu lực như mong muốn. Khi cần ranh giới rõ ràng, có thể tách service hoặc dùng TransactionalOperator trực tiếp.

Không dùng transaction reactive của R2DBC cho JDBC blocking. JDBC dựa trên thread-bound transaction và thao tác blocking; R2DBC dùng reactive transaction manager và Reactor Context. Nếu cần tích hợp JDBC, hãy cô lập thao tác blocking trên scheduler phù hợp và thiết kế ranh giới transaction theo công nghệ thực sự quản lý resource đó.

## 4. TransactionalOperator và vị trí của operator

Có thể áp dụng TransactionalOperator theo kiểu functional bằng as:

~~~java
Mono<Order> update =
    orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> orderRepository.save(order.confirm()))
        .as(transactionalOperator::transactional);
~~~

Toàn bộ Publisher trước as nằm trong transaction được operator quản lý. Cách viết này hữu ích khi muốn nhìn rõ ranh giới transaction ngay trong pipeline.

Cũng có thể chỉ bao một đoạn công việc cần transaction:

~~~java
Mono<InventoryRow> reserveLocally =
    Mono.defer(() -> inventoryRepository.lockAndReserve(sku, quantity))
        .as(transactionalOperator::transactional);

Mono<Receipt> workflow =
    reserveLocally.flatMap(reservation ->
        notificationClient.sendReservation(reservation)
            .thenReturn(Receipt.from(reservation))
    );
~~~

Trong ví dụ, transaction cục bộ chỉ bao thao tác giữ chỗ trong database. Việc gọi notification diễn ra sau khi Publisher transaction hoàn tất. Điều này tránh giữ connection và lock database trong suốt thời gian chờ mạng.

Nếu notification bắt buộc phải được phát cùng với thay đổi database, hãy lưu một outbox record trong transaction và phát nó sau commit. Không nên kéo dài transaction để chờ HTTP hoặc message broker phản hồi.

## 5. Giữ transaction ngắn và tránh gọi service từ bên trong

Một transaction dài có thể giữ connection, row lock hoặc snapshot lâu hơn cần thiết. Trong reactive system, lời gọi HTTP có thể chờ mạng trong thời gian không xác định; nếu nằm trong transaction database, connection có thể bị giữ trong toàn bộ khoảng chờ đó.

Ví dụ cần tránh:

~~~java
@Transactional
Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            inventoryClient.reserve(saved)
                .then(paymentClient.charge(saved))
                .thenReturn(saved)
        );
}
~~~

Transaction này bao gồm các thao tác database và các request mạng. Khi inventory hoặc payment chậm, transaction database vẫn mở; khi service ngoài lỗi, database transaction có thể rollback nhưng side effect ở service ngoài không tự được hoàn tác.

Một cách tổ chức tốt hơn là tách transaction cục bộ và quy trình điều phối:

~~~java
Mono<Order> createPendingOrder(Order order) {
    return orderRepository.save(order.withStatus(PENDING))
        .as(transactionalOperator::transactional);
}

Mono<Reservation> reserveInventory(Order order) {
    return inventoryClient.reserve(order.id(), order.lines());
}
~~~

Sau khi lưu trạng thái pending và commit, tầng orchestration gọi inventory. Nếu bước sau thất bại, workflow có thể cập nhật trạng thái hoặc thực hiện compensation bằng transaction riêng.

## 6. Nhiều repository có cùng transaction hay không?

Hai repository có thể tham gia cùng transaction nếu chúng dùng cùng một transaction manager và resource được manager đó quản lý. Việc chúng là hai interface repository khác nhau không quyết định ranh giới transaction; cấu hình connection factory và transaction manager mới là yếu tố quan trọng.

| Kết hợp resource | Có thể cùng transaction cục bộ? | Điều kiện |
|---|---|---|
| Hai repository R2DBC cùng ConnectionFactory | Có | Cùng reactive transaction manager và subscription context. |
| Repository R2DBC với repository JDBC | Không tự động | Hai công nghệ có transaction manager và mô hình context khác nhau. |
| Hai R2DBC datasource độc lập | Không tự động | Mỗi datasource thường có transaction manager/connection riêng. |
| Database và HTTP service | Không | HTTP service không tham gia transaction R2DBC thông thường. |
| Database và message broker | Không tự động | Cần cơ chế phối hợp riêng hoặc transaction hỗ trợ bởi cả hai hệ thống. |

Nếu ứng dụng có hai database độc lập, việc đặt hai thao tác trong một Mono.zip hoặc Mono.when chỉ phối hợp thời điểm hoàn tất. Nó không tạo atomic commit giữa hai transaction manager.

Ví dụ:

~~~java
Mono.zip(
    accountRepository.updateBalance(accountId, amount),
    ledgerRepository.insertEntry(entry)
);
~~~

Nếu mỗi repository dùng datasource riêng, một thao tác có thể commit thành công trong khi thao tác kia thất bại. zip không thể tự rollback resource đã commit. Hãy quyết định rõ dữ liệu nào là nguồn sự thật và dùng outbox, saga hoặc một coordinator phân tán thực sự nếu nghiệp vụ đòi hỏi.

Nếu các thao tác chỉ cần hoàn tất mà không cần ghép giá trị trả về, Mono.when diễn đạt ý định đó rõ hơn. Cả zip lẫn when đều chỉ phối hợp tín hiệu; chúng không thay thế transaction manager. Ngoài ra, Mono.zip cần mỗi nguồn phát một giá trị để tạo tuple, nên không phù hợp để ghép các thao tác Mono<Void> vốn hoàn tất rỗng.

Về lý thuyết, một hệ thống có thể dùng distributed transaction hoặc two-phase commit nếu mọi resource manager đều hỗ trợ giao thức, có coordinator và được cấu hình để tham gia cùng một giao dịch. Đây là yêu cầu hạ tầng cụ thể, có chi phí về độ trễ, khả năng sẵn sàng và vận hành. Một chuỗi HTTP call giữa các microservice không trở thành distributed transaction chỉ vì caller dùng Reactor; không nên giả định R2DBC, HTTP client và broker đều tham gia XA hoặc 2PC.

## 7. Giới hạn transaction giữa nhiều service

Một service thường sở hữu database riêng và công bố API để các service khác tương tác. Việc một request gọi tuần tự nhiều service không làm các database đó trở thành một transaction chung.

Ví dụ đặt hàng:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant DB as Order DB
    participant I as Inventory Service
    participant P as Payment Service

    O->>DB: Tạo order PENDING
    DB-->>O: Commit
    O->>I: Reserve stock
    I-->>O: Reservation OK
    O->>P: Charge payment
    P-->>O: Payment declined
    O->>DB: Đánh dấu order FAILED
    O->>I: Release reservation
~~~

Trong kịch bản này, transaction của Order Service chỉ bảo vệ thay đổi trong Order DB. Reservation và payment là side effect ở service khác. Nếu payment thất bại, Order Service phải gọi hành động bù để giải phóng reservation và cập nhật trạng thái.

Không nên mô tả chuỗi này như một ACID transaction duy nhất. Mỗi service commit transaction cục bộ riêng; tính nhất quán toàn quy trình được đạt qua các bước tiến, retry, sự kiện và compensation.

## 8. Saga: phối hợp các transaction cục bộ

Saga chia một quy trình dài thành các bước, mỗi bước thực hiện một transaction cục bộ. Khi một bước thất bại, hệ thống chạy các hành động bù cho những bước trước đó đã thành công.

Một Saga có thể được điều phối tập trung (orchestration) hoặc thông qua sự kiện giữa các service (choreography).

| Đặc điểm | Orchestration | Choreography |
|---|---|---|
| Điều phối | Một orchestrator quyết định bước tiếp theo. | Mỗi service phản ứng với sự kiện của service khác. |
| Quan sát quy trình | Dễ thấy trạng thái toàn Saga tại một nơi. | Trạng thái phân tán qua sự kiện và service. |
| Phụ thuộc | Orchestrator biết các bước và hợp đồng service. | Các service phụ thuộc vào event contract. |
| Phù hợp | Quy trình nhiều bước, cần theo dõi và quyết định rõ. | Quy trình đơn giản, các bước phản ứng độc lập. |

Ví dụ các bước và compensation:

| Bước tiến | Transaction cục bộ | Hành động bù |
|---|---|---|
| Tạo đơn hàng | Lưu order ở trạng thái PENDING | Đánh dấu order CANCELLED |
| Giữ tồn kho | Tạo reservation | Hủy reservation |
| Thu tiền | Tạo payment capture | Refund hoặc void payment theo khả năng cổng thanh toán |
| Xác nhận đơn | Cập nhật order CONFIRMED | Chuyển sang trạng thái cần xử lý bù nếu không thể hoàn tác |

Compensation không phải rollback tức thời của transaction đã commit. Nó là một thao tác nghiệp vụ mới, có thể thất bại và cần retry hoặc xử lý thủ công. Ví dụ, hoàn tiền có thể không thành công ngay; Saga cần trạng thái REFUND_PENDING và cơ chế tiếp tục xử lý.

Không phải side effect nào cũng có thể đảo ngược hoàn toàn. Gửi email, phát thông báo hoặc giao hàng đã bắt đầu có thể chỉ được bù bằng một hành động khác như gửi thông báo đính chính hoặc tạo yêu cầu thu hồi. Hãy thiết kế trạng thái và compensation theo nghiệp vụ thực tế.

## 9. Transactional Outbox: lưu thay đổi và sự kiện cùng nhau

Một vấn đề phổ biến là cập nhật database thành công nhưng gửi message thất bại, hoặc message được gửi nhưng transaction database rollback. Nếu ghi database và publish message bằng hai thao tác độc lập, hệ thống có thể rơi vào trạng thái không đồng bộ.

Transactional Outbox giải quyết phần ghi bằng cách lưu dữ liệu nghiệp vụ và một outbox record trong cùng transaction cục bộ:

~~~java
Mono<Order> createOrder(Order order) {
    Mono<Order> work = orderRepository.save(order)
        .flatMap(saved ->
            outboxRepository.save(
                OutboxEvent.orderCreated(saved)
            ).thenReturn(saved)
        );

    return transactionalOperator.transactional(work);
}
~~~

Nếu transaction commit, cả order và outbox event đều tồn tại. Nếu rollback, cả hai đều không được ghi. Một publisher riêng đọc outbox chưa gửi và chuyển message đến broker sau đó.

~~~mermaid
flowchart LR
    A["Order command"] --> T["Local DB transaction"]
    T --> D["Order row"]
    T --> O["Outbox row"]
    O --> P["Outbox publisher / CDC"]
    P --> B["Message broker"]
    B --> C["Consumer service"]
~~~

Outbox publisher có thể gửi lại một event nếu đã publish nhưng chưa kịp đánh dấu trạng thái đã gửi. Vì vậy, mô hình thường cung cấp giao nhận at-least-once, không tự đảm bảo exactly-once end-to-end.

Mỗi event nên có ID ổn định. Consumer cần lưu dấu event đã xử lý hoặc dùng một thao tác idempotent để nếu nhận trùng thì kết quả nghiệp vụ vẫn đúng. Nếu consumer cập nhật database, việc ghi deduplication marker và thay đổi nghiệp vụ nên nằm trong cùng transaction cục bộ.

Outbox giải quyết tính nhất quán giữa thay đổi database và ý định phát sự kiện. Nó không tự giải quyết toàn bộ Saga hoặc đảm bảo mọi consumer đã xử lý thành công; cần retry, dead-letter handling, monitoring và quy trình khôi phục.

## 10. Idempotency và chống xử lý trùng

Trong hệ thống phân tán, retry có thể gửi lại cùng một lệnh hoặc event. Consumer cần nhận diện một thao tác đã được xử lý để tránh trừ tiền hai lần, tạo hai reservation hoặc tạo bản ghi trùng.

Một request có thể mang idempotency key:

~~~java
Mono<PaymentResult> charge(PaymentCommand command) {
    Mono<PaymentAttempt> claim = transactionalOperator.transactional(
        paymentRepository.insertPendingIfAbsent(
            command.idempotencyKey(),
            command.payloadHash()
        ).then(
            paymentRepository.findByIdempotencyKey(command.idempotencyKey())
        )
    );

    return claim.flatMap(attempt -> {
        if (attempt.isCompleted()) {
            return Mono.just(attempt.result());
        }

        return paymentGateway.charge(
                command,
                command.idempotencyKey()
            )
            .flatMap(result -> transactionalOperator.transactional(
                paymentRepository.markCompleted(attempt.id(), result)
                    .thenReturn(result)
            ));
    });
}
~~~

Ví dụ dùng thao tác insert-if-absent có unique constraint trên idempotency key để tạo một claim bền vững trước khi gọi cổng thanh toán. Sau đó, kết quả được lưu bằng transaction cục bộ riêng. Cổng thanh toán cũng nhận cùng key để nhận diện lần gọi lặp. Hai request đồng thời vẫn có thể cùng quan sát trạng thái PENDING và cùng gọi gateway; idempotency ở phía gateway hoặc một cơ chế lease/worker ownership mới ngăn được việc tạo hai khoản charge.

Một thiết kế chắc chắn thường:

- Sinh idempotency key ổn định ở ranh giới lệnh.
- Đặt unique constraint cho key trong database của service sở hữu.
- Lưu trạng thái xử lý và kết quả để trả lại cho request lặp.
- Gọi downstream bằng cùng key nếu downstream hỗ trợ idempotency.
- Nếu downstream không hỗ trợ idempotency, dùng lease, lock hoặc worker claim để chỉ một tiến trình thực hiện side effect tại một thời điểm.
- Phân biệt retry cùng một command với một command nghiệp vụ mới.

Idempotency không có nghĩa mọi thao tác đều được bỏ qua khi lặp. Cần xác định phạm vi key, thời gian lưu và cách xử lý khi cùng key nhưng payload khác nhau.

## 11. Retry ở ranh giới transaction phù hợp

Retry là cần thiết với lỗi tạm thời như deadlock, serialization failure hoặc service ngoài tạm thời không khả dụng. Tuy nhiên, vị trí đặt retryWhen ảnh hưởng đến phạm vi transaction được tạo lại.

Nếu muốn mỗi lần thử có một transaction mới, đặt retry bên ngoài Publisher đã được bọc bởi TransactionalOperator:

~~~java
Mono<Order> attempt = transactionalOperator.transactional(
    orderRepository.findById(orderId)
        .flatMap(orderRepository::confirm)
);

Mono<Order> result = attempt.retryWhen(
    Retry.max(2)
        .filter(this::isTransientDatabaseError)
);
~~~

Khi transaction thất bại, operator kết thúc lần thử và rollback. Retry subscribe lại Publisher đã bọc, từ đó tạo một lần transaction mới theo vòng đời của operator.

Nếu đặt retry bên trong đoạn work được bọc, các lần thử có thể diễn ra trong cùng transaction tùy vị trí operator và transaction context. Sau một lỗi database, transaction có thể đã bị đánh dấu rollback-only hoặc connection không còn phù hợp để tiếp tục. Không nên tiếp tục truy vấn trong transaction đã hỏng chỉ vì onErrorResume hoặc retry che lỗi.

Chỉ retry lỗi được xác định là tạm thời. Không retry lỗi validation, quyền truy cập hoặc vi phạm nghiệp vụ như thể chúng sẽ tự biến mất. Với thao tác đã gọi service ngoài, retry phải có idempotency key hoặc cơ chế xác nhận trạng thái để tránh lặp side effect.

## 12. Error recovery có thể làm transaction commit

Một chi tiết quan trọng: transaction operator thường commit khi Publisher bên trong hoàn tất bình thường. Nếu lỗi được chuyển thành giá trị dự phòng ngay bên trong ranh giới transaction, transaction manager có thể chỉ thấy completion và commit các thay đổi trước đó.

Ví dụ:

~~~java
Mono<Order> result = transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.save(AuditRecord.forOrder(saved))
                .thenReturn(saved)
        )
        .onErrorResume(error -> Mono.just(order))
);
~~~

Nếu lưu audit thất bại nhưng onErrorResume biến lỗi thành một giá trị bình thường trước khi Publisher đi tới TransactionalOperator, operator có thể commit thay đổi order. Điều này chỉ đúng nếu nghiệp vụ thực sự chấp nhận lưu order mà không có audit.

Nếu audit là bắt buộc và lỗi phải rollback, hãy để lỗi thoát khỏi transaction:

~~~java
Mono<Order> result = transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.save(AuditRecord.forOrder(saved))
                .thenReturn(saved)
        )
);
~~~

Sau đó, nếu cần chuyển lỗi thành response, xử lý ở phía ngoài:

~~~java
Mono<OrderResult> response = result
    .map(OrderResult::success)
    .onErrorResume(error ->
        Mono.just(OrderResult.failure(error))
    );
~~~

Khi đó, transaction operator đã quan sát lỗi và có cơ hội rollback trước khi tầng response chuyển lỗi thành dữ liệu. Nếu cần tiếp tục trong cùng transaction sau một lỗi có thể phục hồi, phải hiểu rõ trạng thái transaction và cơ chế đánh dấu rollback-only của database/driver; không nên giả định mọi lỗi đều có thể được nuốt an toàn.

## 13. Cancellation và thời gian sống của transaction

Reactive transaction gắn với subscription. Khi downstream hủy, cancellation được truyền ngược upstream và transaction manager có thể rollback thay vì commit. Điều này thường xảy ra khi HTTP client ngắt kết nối, timeout hoặc một toán tử như take kết thúc sớm.

Vì vậy:

- Không tạo subscription detached bên trong transaction.
- Không lưu Publisher transactional để subscribe nhiều lần mà không hiểu mỗi subscription có thể tạo một transaction riêng.
- Giữ transaction ngắn, tránh chờ dịch vụ ngoài.
- Cấu hình timeout phù hợp với connection pool và database.
- Đảm bảo nguồn và driver hỗ trợ cancellation; một số thao tác có thể cần thời gian để dừng thực tế.
- Không xem client disconnect là bằng chứng mọi side effect ngoài database đã được hủy.

Nếu một transaction đã gửi HTTP request đến service ngoài rồi bị hủy, database có thể rollback nhưng service ngoài vẫn tiếp tục xử lý. Đây là một lý do khác để đặt side effect liên service ngoài transaction cục bộ và quản lý bằng Saga/Outbox.

## 14. Isolation, lock và concurrency trong pipeline

Transaction manager có thể cho phép chọn isolation level và timeout, nhưng mức hỗ trợ cụ thể phụ thuộc database và R2DBC driver. Không nên giả định mọi database hỗ trợ cùng một mức cô lập hoặc mọi cấu hình đều có cùng hiệu lực.

Khi một transaction dùng một connection R2DBC, cần thận trọng với các thao tác song song trên cùng connection:

~~~java
// Tránh mặc định chạy nhiều query đồng thời trên cùng transaction connection.
Mono<Tuple2<Account, Ledger>> unsafeParallelWork =
    Mono.zip(
        accountRepository.findById(accountId),
        ledgerRepository.findLatest(accountId)
    );
~~~

Một số driver hoặc connection không hỗ trợ nhiều câu lệnh đồng thời trên cùng connection. Hành vi có thể là lỗi, xếp hàng nội bộ hoặc phụ thuộc driver. Nếu các thao tác thuộc cùng transaction và dùng chung connection, cách tuần tự thường rõ ràng hơn:

~~~java
Mono<AccountSnapshot> snapshot =
    accountRepository.findById(accountId)
        .flatMap(account ->
            ledgerRepository.findLatest(accountId)
                .map(ledger -> new AccountSnapshot(account, ledger))
        )
        .as(transactionalOperator::transactional);
~~~

Nếu hai truy vấn thật sự độc lập và cần chạy song song, hãy cân nhắc đọc bằng các transaction/connection riêng hoặc thiết kế truy vấn tổng hợp. Nhưng khi tách connection, chúng không còn tự động thuộc cùng một transaction ACID.

Giảm thời gian giữ lock, dùng index phù hợp và chọn isolation theo invariant nghiệp vụ. Không hạ isolation chỉ để tăng throughput nếu điều đó cho phép lost update, dirty read hoặc vi phạm invariant.

## 15. Kiểm thử transaction và quy trình liên service

Kiểm thử transaction cần xác minh cả kết quả phát ra và trạng thái database sau completion hoặc error. StepVerifier điều khiển subscription và tín hiệu; kiểm thử tích hợp với database thật hoặc container giúp xác nhận rollback/commit của driver và transaction manager.

Ví dụ cấu trúc kiểm thử một work unit:

~~~java
@Test
void rollbackKhiAuditThatBai() {
    Mono<Order> work = orderService.updateOrderAndAudit(order);

    StepVerifier.create(work)
        .expectError(AuditWriteException.class)
        .verify();

    StepVerifier.create(orderRepository.findById(order.id()))
        .verifyComplete();
}
~~~

Phép thử giả định database được chuẩn bị để audit insert thất bại và kiểm tra order không còn được lưu. Nếu repository dùng datasource hoặc transaction manager khác, kết quả có thể không rollback cùng nhau; đó chính là ranh giới cần kiểm chứng.

Các kịch bản nên kiểm thử:

- Tất cả thao tác trong cùng datasource commit khi thành công.
- Một thao tác trong transaction lỗi làm các thay đổi trước đó rollback.
- Lỗi được xử lý bên ngoài transaction không làm transaction commit ngoài ý muốn.
- Cancellation xảy ra trước khi transaction hoàn tất dẫn đến cleanup/rollback theo cấu hình.
- Hai datasource độc lập có thể rơi vào trạng thái một bên thành công, một bên thất bại.
- Outbox record và dữ liệu nghiệp vụ được commit hoặc rollback cùng nhau.
- Consumer xử lý event trùng mà không tạo side effect trùng.
- Saga chạy compensation khi một bước sau thất bại.
- Retry chỉ lặp lỗi tạm thời và tạo transaction mới khi cần.

Với Outbox và Saga, cần kiểm thử cả crash window: publisher gửi event xong nhưng chưa đánh dấu sent; consumer xử lý xong nhưng acknowledgement bị mất; compensation thất bại và cần retry. Các tình huống này quyết định độ tin cậy của quy trình trong production.

## 16. Checklist xác định ranh giới giao dịch

Trước khi triển khai một pipeline có nhiều nguồn dữ liệu hoặc dịch vụ, hãy trả lời:

1. Những thao tác nào phải commit hoặc rollback cùng nhau?
2. Chúng có dùng cùng database, connection factory và transaction manager không?
3. Có thao tác HTTP, message broker hoặc side effect bên ngoài nào nằm trong transaction không?
4. Transaction có bị kéo dài bởi I/O mạng hoặc Publisher không giới hạn không?
5. Khi một service thất bại sau khi service khác đã commit, hành động bù là gì?
6. Có cần Outbox để không mất event giữa database và broker không?
7. Retry có an toàn nhờ idempotency key hoặc unique constraint không?
8. Lỗi được phục hồi ở bên trong hay bên ngoài transaction boundary?
9. Cancellation có thể xảy ra ở đâu và resource nào cần cleanup?
10. Kiểm thử có xác minh trạng thái lưu trữ sau commit, rollback và crash/retry không?

Trong ứng dụng Java reactive, TransactionalOperator và reactive @Transactional bảo vệ các thao tác thuộc cùng transaction manager và resource. Khi nghiệp vụ đi qua nhiều database hoặc service, Mono.zip, Mono.when hay một chuỗi flatMap chỉ điều phối các kết quả bất đồng bộ; chúng không tạo atomic commit phân tán. Giới hạn transaction cục bộ, giữ transaction ngắn, dùng Outbox và Saga, thiết kế idempotency cùng retry có kiểm soát sẽ giúp hệ thống duy trì tính nhất quán mà không giả định mọi service cùng nằm trong một transaction.

