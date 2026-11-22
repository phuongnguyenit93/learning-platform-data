# Giới hạn giao dịch cục bộ khi liên quan nhiều tài nguyên

Spring Data R2DBC hỗ trợ transaction reactive cho các thao tác trên một `ConnectionFactory`. Transaction này có thể bảo đảm nhiều câu lệnh SQL cùng commit hoặc rollback trên tài nguyên database được quản lý. Tuy nhiên, một transaction R2DBC cục bộ không tự động mở rộng sang message broker, dịch vụ HTTP, Redis, filesystem hoặc một `ConnectionFactory` khác.

Đây là ranh giới quan trọng khi thiết kế một use case có nhiều side effect. Ví dụ, tạo đơn hàng trong database rồi gửi sự kiện sang Kafka là hai thao tác trên hai tài nguyên độc lập. Nếu database commit nhưng gửi message thất bại, trạng thái giữa hai hệ thống không đồng nhất. Nếu gửi message thành công nhưng transaction database rollback, consumer có thể nhận một sự kiện tham chiếu đến đơn hàng không tồn tại.

Muốn xử lý đúng, cần phân biệt transaction cục bộ với distributed transaction, xác định tài nguyên nào thực sự tham gia cùng transaction, rồi chọn mẫu tích hợp như transactional outbox, saga, retry idempotent hoặc cơ chế điều phối phân tán phù hợp.

## 1. Transaction cục bộ trong Spring Data R2DBC

`R2dbcTransactionManager` quản lý transaction cho một R2DBC `ConnectionFactory`. Khi transaction bắt đầu, Spring lấy và gắn một connection phù hợp vào reactive transaction context. Các thao tác truy cập dữ liệu được cấu hình để dùng cùng `ConnectionFactory` và tham gia transaction đó có thể dùng chung connection được quản lý.

Ví dụ cấu hình:

```java
@Configuration
public class DatabaseConfiguration {

    @Bean
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

Service có thể dùng `@Transactional` trên reactive method:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        Order order = Order.from(command);

        return orderRepository.save(order)
            .flatMap(saved ->
                Flux.fromIterable(command.lines())
                    .map(line -> OrderLine.from(saved.getId(), line))
                    .concatMap(lineRepository::save)
                    .thenReturn(saved)
            );
    }
}
```

Nếu hai repository dùng cùng `ConnectionFactory` và cùng reactive transaction manager, các thao tác ghi có thể tham gia một transaction cục bộ. Nếu bất kỳ thao tác nào phát lỗi trong reactive chain, transaction có thể rollback.

Transaction reactive được gắn với Reactor Context, không dựa vào việc mọi thao tác chạy trên cùng một thread. Vì vậy, phải nối các publisher vào cùng chain và trả publisher về cho Spring quản lý. Không gọi `subscribe()` hoặc `block()` bên trong phương thức transactional để tự chạy một nhánh công việc tách rời.

## 2. Phạm vi tài nguyên của R2dbcTransactionManager

`R2dbcTransactionManager` quản lý một `ConnectionFactory` cụ thể. Nó không phải transaction coordinator cho mọi tài nguyên mà ứng dụng sử dụng.

| Tài nguyên | Có tự động tham gia transaction R2DBC không? | Ghi chú |
|---|---|---|
| Repository và `R2dbcEntityTemplate` dùng cùng `ConnectionFactory` | Có thể | Cần dùng đúng transaction manager và reactive context. |
| `DatabaseClient` dùng cùng `ConnectionFactory` | Có thể | Spring tích hợp connection management để tham gia transaction. |
| Một `ConnectionFactory` khác | Không | Cần transaction manager riêng hoặc cơ chế phối hợp khác. |
| JDBC `DataSource` | Không | JDBC transaction manager và R2DBC transaction manager quản lý connection khác nhau. |
| Kafka/RabbitMQ broker | Không | Broker có transaction riêng, không tự tham gia transaction database R2DBC. |
| Redis hoặc cache | Không | Lệnh cache là side effect ngoài transaction R2DBC. |
| HTTP API của service khác | Không | Remote service không thể được rollback bởi database transaction cục bộ. |
| File system/object storage | Không | Ghi file không được rollback khi transaction database thất bại. |

Điểm cần nhớ là transaction manager quản lý tài nguyên mà nó được thiết kế để điều khiển. Đặt nhiều thao tác trong cùng một phương thức `@Transactional` không biến chúng thành một transaction ACID chung nếu các thao tác đó dùng resource manager khác nhau.

## 3. Vì sao nhiều tài nguyên không tự động cùng commit?

Giả sử use case cần ghi đơn hàng vào database và gửi `OrderCreated` sang message broker. Có hai thứ tự dễ gặp, cả hai đều có khoảng lỗi:

**Gửi message trước, rồi commit database:**

1. Ứng dụng gửi `OrderCreated` thành công.
2. Consumer nhận message và đọc đơn hàng.
3. Transaction R2DBC gặp lỗi hoặc rollback.
4. Message vẫn tồn tại dù đơn hàng không được commit.

**Commit database trước, rồi gửi message:**

1. Transaction R2DBC commit đơn hàng.
2. Ứng dụng gửi message.
3. Broker không khả dụng hoặc thao tác gửi thất bại.
4. Đơn hàng đã tồn tại nhưng sự kiện chưa được phát.

Một transaction R2DBC không thể rollback message đã được broker chấp nhận, và transaction broker cũng không tự rollback bản ghi đã commit trong database. Chỉ đổi thứ tự hai lệnh không loại bỏ được khoảng lỗi; nó chỉ chuyển lỗi từ một phía sang phía còn lại.

Ví dụ dưới đây không tạo atomicity giữa database và Kafka dù phương thức có `@Transactional`:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = Order.from(command);

    return orderRepository.save(order)
        .flatMap(saved ->
            Mono.fromFuture(kafkaTemplate.send(
                "orders",
                saved.getId().toString(),
                new OrderCreated(saved.getId())
            )).thenReturn(saved)
        );
}
```

Publisher gửi Kafka có thể được nối vào reactive chain, nhưng `R2dbcTransactionManager` vẫn chỉ quản lý database connection. Nếu gửi Kafka thành công rồi transaction database rollback, message không tự biến mất. Nếu database commit và thao tác gửi Kafka thất bại, transaction database không thể hoàn tác một commit đã hoàn tất chỉ vì publisher bên ngoài phát lỗi sau đó.

## 4. Phân biệt transaction cục bộ và distributed transaction

**Local transaction** bảo đảm tính nguyên tử trong phạm vi một resource manager, chẳng hạn một transaction trên connection do `R2dbcTransactionManager` quản lý.

**Distributed transaction** phối hợp nhiều resource manager để chúng cùng commit hoặc rollback theo một giao thức chung. Mô hình hai pha thường được gọi là two-phase commit (2PC): coordinator yêu cầu các participant chuẩn bị commit, rồi quyết định commit hoặc rollback. Cách này cần tất cả participant hỗ trợ giao thức và có coordinator phù hợp.

R2DBC SPI không cung cấp một giao thức XA/distributed transaction chuẩn để `R2dbcTransactionManager` tự phối hợp tùy ý nhiều `ConnectionFactory` và broker. Không nên suy luận rằng vì một API có tên `@Transactional` nên nó tự cung cấp 2PC.

Trong hệ thống Spring, một số công nghệ hoặc broker có transaction riêng, và một số nền tảng có thể cung cấp cơ chế điều phối phân tán ở cấp hạ tầng. Việc phối hợp đó cần tích hợp và hỗ trợ rõ ràng từ tất cả resource manager; không phải tính năng mặc định của Spring Data R2DBC. Trước khi chọn distributed transaction, phải xác minh driver, broker, coordinator, khả năng phục hồi và mô hình triển khai có hỗ trợ đầy đủ hay không.

## 5. Nhiều ConnectionFactory cũng là nhiều ranh giới transaction

Một ứng dụng có thể kết nối đến hai database bằng hai `ConnectionFactory`, ví dụ database đơn hàng và database phân tích. Mỗi factory thường có transaction manager tương ứng:

```java
@Bean
@Primary
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
ReactiveTransactionManager reportingTransactionManager(
        @Qualifier("reportingConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

Một transaction của `ordersTransactionManager` không tự quản lý connection do `reportingConnectionFactory` tạo ra. Việc hai factory trỏ đến cùng một máy chủ database hoặc cùng một database name cũng không đủ để coi chúng là cùng transaction; mỗi factory có thể cấp connection độc lập.

Với nhiều transaction manager, cần chọn rõ manager cho service:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(...) {
    // Các thao tác trên ordersConnectionFactory.
}
```

Nếu use case phải ghi cả hai database, `@Transactional` với một manager chỉ bao phủ tài nguyên của manager đó. Có thể thực hiện hai local transaction theo trình tự và thiết kế retry/compensation, hoặc dùng một distributed transaction coordinator thực sự tương thích nếu yêu cầu và nền tảng cho phép. Không nên giả định hai annotation `@Transactional` lồng nhau tạo ra một commit nguyên tử xuyên hai database.

## 6. Transactional outbox: ghi dữ liệu và sự kiện trong cùng database transaction

Transactional outbox giải quyết bài toán database commit và phát sự kiện bằng cách lưu sự kiện cần gửi thành một hàng trong cùng database transaction với dữ liệu nghiệp vụ.

Luồng xử lý:

1. Bắt đầu transaction R2DBC.
2. Ghi đơn hàng hoặc thay đổi nghiệp vụ.
3. Ghi một hàng outbox chứa event type, payload, aggregate ID và trạng thái chờ gửi.
4. Commit cả dữ liệu nghiệp vụ và hàng outbox cùng lúc.
5. Một publisher nền đọc các hàng outbox chưa gửi và gửi đến broker.
6. Sau khi broker xác nhận, publisher đánh dấu hàng outbox đã gửi hoặc lưu checkpoint tương ứng.

Nếu transaction database rollback, cả đơn hàng lẫn outbox row đều rollback. Nếu database commit, sự kiện vẫn nằm trong outbox để publisher có thể gửi lại sau khi broker phục hồi.

Ví dụ schema đơn giản:

```sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX ix_outbox_pending
    ON outbox_event (created_at)
    WHERE published_at IS NULL;
```

Cú pháp partial index trong ví dụ phù hợp với một số database như PostgreSQL; database khác có thể cần index hoặc schema khác. Kiểu JSON/JSONB cũng có thể được chọn cho `payload` nếu driver và schema hỗ trợ.

Ghi domain object và outbox row trong cùng reactive transaction:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = Order.from(command);

    return orderRepository.save(order)
        .flatMap(saved -> {
            OutboxEvent event = OutboxEvent.pending(
                UUID.randomUUID(),
                "Order",
                saved.getId().toString(),
                "OrderCreated",
                serialize(new OrderCreated(saved.getId()))
            );

            return outboxRepository.save(event)
                .thenReturn(saved);
        });
}
```

Hai repository phải dùng cùng database `ConnectionFactory` và transaction manager. Nếu outbox nằm ở database khác, hai lần ghi không còn nguyên tử trong một transaction R2DBC.

## 7. Publisher outbox và giao nhận ít nhất một lần

Một publisher nền có thể truy vấn các event đang chờ, gửi từng event đến broker, rồi cập nhật trạng thái. Việc gửi và đánh dấu đã gửi vẫn là hai thao tác ở hai tài nguyên khác nhau:

- Nếu gửi thành công nhưng process dừng trước khi cập nhật `published_at`, event sẽ được gửi lại sau khi khởi động.
- Nếu đánh dấu đã gửi trước rồi mới gửi broker, process có thể dừng sau khi đánh dấu và trước khi gửi, khiến event bị mất.

Vì vậy, cách triển khai phổ biến là gửi trước, đánh dấu sau và chấp nhận khả năng duplicate. Đây là mô hình giao nhận **at-least-once**. Consumer cần xử lý idempotent dựa trên event ID hoặc một khóa nghiệp vụ duy nhất.

Ví dụ phác thảo publisher:

```java
Mono<Void> publishOne(OutboxEvent event) {
    return Mono.fromFuture(kafkaTemplate.send(
            "domain-events",
            event.getAggregateId(),
            event.getPayload()))
        .then(outboxRepository.markPublished(
            event.getId(), Instant.now()))
        .then();
}
```

Đoạn code minh họa thứ tự gửi rồi đánh dấu; phần chọn event, lease/lock, retry, timeout và xử lý lỗi cần được triển khai theo broker cùng database thực tế. Nếu nhiều publisher chạy đồng thời, cần cơ chế claim để tránh tất cả cùng gửi một hàng. Có thể dùng lease, trạng thái `PROCESSING`, khóa hàng hoặc cú pháp như `FOR UPDATE SKIP LOCKED` nếu database hỗ trợ.

Không nên tuyên bố outbox tự cung cấp exactly-once end-to-end. Publisher có thể gửi trùng, broker có thể redeliver và consumer có thể xử lý lại. Event ID ổn định cùng consumer inbox/deduplication giúp đạt hiệu quả xử lý một lần ở cấp nghiệp vụ, nhưng phải thiết kế và lưu trạng thái chống trùng rõ ràng.

## 8. Idempotency ở consumer

Consumer nhận event nên có cách nhận diện event đã xử lý. Một bảng inbox có thể lưu event ID với unique constraint:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Khi consumer nhận event, nó mở transaction cục bộ của database đích, cố gắng ghi event ID vào `processed_event`, rồi áp dụng thay đổi nghiệp vụ trong cùng transaction. Nếu event ID đã tồn tại, consumer biết event đã được xử lý và có thể bỏ qua phần thay đổi lặp.

Minh họa luồng:

```java
@Transactional
public Mono<Void> handle(OrderCreated event) {
    return processedEventRepository.insertIfAbsent(event.eventId())
        .flatMap(inserted -> {
            if (!inserted) {
                return Mono.empty();
            }

            return projectionRepository.applyOrderCreated(event);
        });
}
```

`insertIfAbsent` là abstraction minh họa; cách triển khai có thể dùng `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL hoặc cú pháp tương đương của database. Nếu không ghi inbox và cập nhật projection trong cùng transaction, process có thể dừng giữa hai bước và gây xử lý lặp hoặc mất cập nhật.

Nếu consumer thực hiện side effect bên ngoài database, ví dụ gọi dịch vụ thanh toán, inbox transaction không thể rollback side effect đó. Khi đó cần idempotency key mà dịch vụ đích hỗ trợ hoặc đưa hành động vào một saga có trạng thái và cơ chế bù trừ.

## 9. Saga cho quy trình nghiệp vụ qua nhiều service

Khi một use case đi qua nhiều service hoặc database độc lập, saga chia quy trình thành các bước, mỗi bước dùng transaction cục bộ của chính service đó. Nếu bước sau thất bại, hệ thống thực hiện hành động bù trừ (compensating action) để đưa nghiệp vụ về trạng thái chấp nhận được.

Ví dụ đặt hàng:

1. Order Service tạo đơn ở trạng thái `PENDING`.
2. Inventory Service giữ hàng.
3. Payment Service thu tiền.
4. Order Service chuyển đơn sang `CONFIRMED`.

Nếu thanh toán thất bại sau khi giữ hàng, saga gọi Inventory Service để nhả hàng. Nếu bước xác nhận đơn thất bại sau khi đã thu tiền, quy trình có thể yêu cầu hoàn tiền. Hành động bù trừ là một thao tác nghiệp vụ mới, không phải rollback database transaction đã commit ở service trước.

Hai kiểu điều phối phổ biến:

- **Choreography:** service phát và phản ứng với event của nhau; không có một coordinator trung tâm điều khiển mọi bước. Cách này giảm phụ thuộc tập trung nhưng luồng nghiệp vụ có thể khó theo dõi khi có nhiều nhánh.
- **Orchestration:** một saga orchestrator giữ trạng thái quy trình và gửi lệnh cho từng service. Cách này làm rõ trình tự, timeout, retry và compensation nhưng thêm một thành phần điều phối.

Saga phù hợp với quy trình dài, nhiều tài nguyên và chấp nhận eventual consistency. Nó không tạo isolation toàn cục như một transaction ACID duy nhất; trong thời gian saga chạy, các service có thể nhìn thấy trạng thái trung gian như `PENDING`, `RESERVED` hoặc `PAYMENT_PENDING`.

## 10. Retry, timeout và compensation

Mỗi bước saga cần xác định rõ:

- Trạng thái trước và sau khi thực hiện.
- Khóa idempotency để lệnh gửi lại không tạo tác động trùng.
- Timeout và số lần retry.
- Lỗi nào có thể retry, lỗi nào là lỗi nghiệp vụ không thể tự phục hồi.
- Hành động bù trừ nếu bước sau không thể hoàn thành.
- Cách lưu trạng thái để process có thể tiếp tục sau restart.

Không retry vô hạn một thao tác đã biết chắc không thể thành công, ví dụ tài khoản không đủ tiền hoặc sản phẩm không còn hàng. Ngược lại, lỗi mạng tạm thời có thể được retry với backoff và jitter. Nếu không biết chắc request đã đến service đích hay chưa, idempotency key giúp tránh tạo tác động hai lần.

Compensation không phải lúc nào cũng đảo ngược hoàn toàn hành động ban đầu. Ví dụ, email đã gửi không thể thu hồi; một khoản thanh toán đã capture có thể cần refund chứ không thể xóa lịch sử thanh toán. Vì vậy, saga phải mô hình hóa trạng thái nghiệp vụ và hành động bù trừ thực tế.

## 11. Tích hợp với HTTP API và dịch vụ bên ngoài

Một transaction database không thể giữ khóa trên service HTTP từ xa hoặc rollback yêu cầu đã được service đó xử lý. Tránh mở transaction R2DBC dài trong khi chờ HTTP call.

Một cách tổ chức thường tốt hơn:

1. Đọc và kiểm tra dữ liệu cần thiết trước khi mở transaction nếu không cần khóa dữ liệu trong lúc gọi dịch vụ ngoài.
2. Gọi service ngoài với idempotency key và timeout phù hợp nếu bước đó phải xảy ra trước khi ghi.
3. Mở transaction R2DBC ngắn để ghi trạng thái kết quả và dữ liệu liên quan.
4. Nếu hai phía cần phối hợp qua nhiều bước, lưu trạng thái workflow/saga và phát command/event có thể retry.

Nếu thứ tự nghiệp vụ yêu cầu database ghi trước rồi mới gọi HTTP, hãy ghi trạng thái `PENDING` và outbox command trong cùng transaction; worker thực hiện HTTP sau commit và cập nhật kết quả bằng một transaction cục bộ khác. Cách này giúp process restart vẫn biết việc cần thực hiện.

## 12. Tích hợp với cache và filesystem

Cache thường là bản sao có thể tái tạo từ database. Thay đổi cache trong khi transaction database chưa commit có thể khiến request khác đọc trạng thái mới trước khi dữ liệu chính thức được commit. Nếu transaction rollback, cache trở nên sai.

Một số lựa chọn:

- Xóa hoặc cập nhật cache sau khi database commit.
- Phát sự kiện invalidation qua outbox để worker xử lý.
- Dùng TTL và cơ chế cache-aside để cache có thể được làm mới.
- Không coi cache write là một phần của transaction database nếu không có giao thức phối hợp thực sự.

Tương tự, ghi file hoặc object storage không được rollback cùng transaction R2DBC. Nếu cần lưu file và metadata, có thể upload file vào vùng tạm trước, ghi metadata/trạng thái trong database, rồi chuyển file sang trạng thái chính thức sau commit. Cần có job dọn file tạm nếu database rollback hoặc workflow bị bỏ dở.

## 13. Những cách làm dễ tạo trạng thái không nhất quán

| Cách làm | Rủi ro |
|---|---|
| Ghi database rồi gửi message, coi `@Transactional` bảo vệ cả hai | Message có thể thất bại sau khi database đã commit. |
| Gửi message rồi mới ghi database | Consumer có thể xử lý event trước khi dữ liệu database tồn tại; database rollback không thu hồi message. |
| Ghi hai `ConnectionFactory` dưới một `R2dbcTransactionManager` | Manager chỉ quản lý factory mà nó được cấu hình. |
| Gọi HTTP trong transaction dài | Giữ connection/lock trong lúc chờ mạng và vẫn không rollback được service ngoài. |
| Ghi cache trước commit | Cache có thể chứa dữ liệu mà transaction database sau đó rollback. |
| Dùng `onErrorResume` để bỏ qua lỗi side effect | Ứng dụng có thể báo thành công dù một tài nguyên chưa được cập nhật. |
| Retry không có idempotency key | Có thể tạo bản ghi, thanh toán hoặc message trùng. |
| Đánh dấu outbox đã gửi trước khi broker xác nhận | Process dừng giữa hai bước có thể làm mất event. |

## 14. Chọn mẫu tích hợp theo yêu cầu

| Nhu cầu | Mẫu phù hợp |
|---|---|
| Nhiều câu SQL trên cùng database cần cùng commit | Một local R2DBC transaction với cùng `ConnectionFactory`. |
| Ghi database và phát event đáng tin cậy | Transactional outbox cùng publisher có retry. |
| Consumer có thể nhận event nhiều lần | Inbox/deduplication và xử lý idempotent. |
| Quy trình qua nhiều service với nhiều bước nghiệp vụ | Saga choreography hoặc orchestration. |
| Nhiều resource manager có hỗ trợ 2PC và yêu cầu atomic commit toàn cục | Distributed transaction coordinator tương thích, sau khi xác minh đầy đủ hỗ trợ và chi phí vận hành. |
| Cập nhật cache sau khi dữ liệu chính thức commit | After-commit invalidation hoặc outbox event. |
| Ghi file/object storage cùng metadata | Workflow có trạng thái, vùng tạm và cleanup/compensation. |

Không chọn distributed transaction chỉ để tránh thiết kế trạng thái trung gian. 2PC có thể giữ tài nguyên trong thời gian coordinator chờ participant, làm tăng độ phức tạp vận hành và tạo phụ thuộc vào hạ tầng hỗ trợ. Với nhiều hệ thống web và message-driven, outbox cùng eventual consistency thường dễ mở rộng và phục hồi hơn.

## 15. Quy trình thiết kế use case có nhiều tài nguyên

Trước khi triển khai, hãy lập danh sách tài nguyên và ranh giới transaction:

1. Liệt kê mọi nơi có side effect: database, broker, cache, HTTP service, file store và các database khác.
2. Xác định `ConnectionFactory` và transaction manager sở hữu từng thao tác database.
3. Đánh dấu thao tác nào có thể cùng nằm trong một local transaction và thao tác nào nằm ngoài.
4. Viết rõ các trạng thái lỗi có thể xảy ra giữa từng bước, chẳng hạn database commit nhưng message chưa gửi.
5. Chọn outbox cho sự kiện cần phát bền vững sau commit; chọn saga cho quy trình nhiều bước có compensation.
6. Thiết kế idempotency key, unique constraint, retry/backoff, timeout và dead-letter/reject handling.
7. Lưu trạng thái workflow/checkpoint đủ để tiếp tục sau restart.
8. Đưa side effect ra khỏi transaction database dài; chỉ giữ transaction mở quanh thao tác database cần nguyên tử.
9. Kiểm thử các điểm crash giả lập: trước commit, sau commit, sau khi gửi message và trước khi đánh dấu đã gửi.
10. Theo dõi outbox backlog, tuổi event chờ gửi, số lần retry, saga đang treo và lỗi compensation.

## 16. Kiểm thử và vận hành tính nhất quán

Kiểm thử happy path chưa đủ để xác nhận một workflow nhiều tài nguyên an toàn. Cần kiểm tra cả các khoảng lỗi:

- Transaction database rollback sau khi ghi domain row và outbox row: cả hai phải không tồn tại.
- Database commit thành công nhưng publisher dừng trước khi gửi: event vẫn ở trạng thái chờ và được gửi sau khi khởi động lại.
- Broker nhận event nhưng publisher dừng trước khi đánh dấu: event có thể được gửi lại; consumer phải chống xử lý trùng.
- Consumer commit cập nhật nghiệp vụ rồi mất acknowledgement: broker có thể giao lại; inbox/deduplication phải ngăn tác động lặp.
- Một bước saga timeout nhưng service đích đã thực hiện: retry cùng idempotency key phải trả lại kết quả tương ứng thay vì lặp side effect.
- Compensation thất bại: workflow phải được đánh dấu cần can thiệp hoặc retry, không báo hoàn tất giả.

Các metric quan trọng gồm số lượng và tuổi outbox pending, tỷ lệ publish lỗi, số event trùng được bỏ qua, thời gian hoàn thành saga, số workflow ở trạng thái trung gian quá lâu, số lần retry và số compensation thất bại. Có log correlation ID xuyên service để theo dõi toàn bộ một nghiệp vụ.

Transaction cục bộ của Spring Data R2DBC là công cụ phù hợp để bảo đảm atomicity trên một `ConnectionFactory`. Khi một use case liên quan nhiều database hoặc nhiều loại tài nguyên, cần chủ động thiết kế ranh giới commit, trạng thái trung gian và cách phục hồi. Outbox giúp gắn dữ liệu với sự kiện trong cùng transaction database; saga điều phối các bước cục bộ và hành động bù trừ; idempotency giúp retry an toàn. Không có annotation `@Transactional` đơn lẻ nào tự biến các tài nguyên độc lập thành một transaction ACID chung.
