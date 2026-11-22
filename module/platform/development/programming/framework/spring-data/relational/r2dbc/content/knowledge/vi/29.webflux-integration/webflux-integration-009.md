# Phối hợp lời gọi HTTP hoặc sự kiện ngoài với thao tác lưu trữ

Trong ứng dụng Spring WebFlux kết hợp Spring Data R2DBC, một use case có thể vừa ghi dữ liệu vào database vừa gọi một dịch vụ HTTP khác hoặc phát một sự kiện ra message broker. Ví dụ: tạo đơn hàng rồi yêu cầu dịch vụ thanh toán xử lý; lưu hồ sơ rồi thông báo sang hệ thống tìm kiếm; ghi nhận thay đổi tồn kho rồi phát sự kiện cho các dịch vụ khác.

Khó khăn nằm ở chỗ reactive transaction của R2DBC chỉ quản lý tài nguyên database mà transaction manager sở hữu. Nó không thể rollback một HTTP request đã được hệ thống bên ngoài xử lý, thu hồi email đã gửi hoặc xóa một message broker đã nhận. Nếu database commit nhưng lời gọi ngoài thất bại, hoặc lời gọi ngoài thành công nhưng database rollback, hai hệ thống có thể lệch trạng thái.

Vì vậy, cần xác định rõ thứ tự thao tác, ranh giới transaction và cách phục hồi. Những lựa chọn thường dùng gồm: gọi HTTP trước hoặc sau transaction với quy tắc rõ ràng; lưu trạng thái workflow để điều phối nhiều bước; transactional outbox để ghi dữ liệu và sự kiện trong cùng transaction; inbox/idempotency để xử lý message lặp; và saga với hành động bù trừ khi quy trình trải qua nhiều hệ thống.

## 1. Hai loại tài nguyên trong một use case

Một luồng nghiệp vụ tích hợp thường đụng tới hai nhóm tài nguyên:

- **Tài nguyên cục bộ:** database được quản lý bởi R2DBC connection factory và reactive transaction manager.
- **Tài nguyên bên ngoài:** HTTP service, payment gateway, email provider, message broker, search index hoặc hệ thống khác.

Ví dụ:

~~~mermaid
flowchart LR
    S[WebFlux Service]
    TX[Reactive DB Transaction]
    DB[(R2DBC Database)]
    HTTP[WebClient / HTTP API]
    EXT[External Service]
    S --> TX --> DB
    S --> HTTP --> EXT
~~~

Transaction manager có thể commit hoặc rollback thao tác trên DB. HTTP service có vòng đời request và trạng thái riêng; nó không tự tham gia transaction R2DBC. Khi một request HTTP đã được xử lý thành công ở hệ thống ngoài, rollback database cục bộ không làm hệ thống đó hoàn tác.

## 2. Vì sao không nên giữ database transaction trong lúc chờ HTTP?

Một cách viết dễ gặp:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentClient.authorize(toPaymentRequest(order))
                            .thenReturn(order)
            );
}
~~~

Toàn bộ publisher nằm trong reactive transaction. Sau khi lưu Order, ứng dụng giữ connection và transaction trong lúc chờ network call. Nếu payment service mất 5 giây, connection database có thể bị giữ trong khoảng thời gian đó.

Điều này gây ra một số vấn đề:

- Connection pool bị chiếm lâu hơn cần thiết.
- Row lock hoặc transaction snapshot có thể được giữ trong lúc chờ dịch vụ ngoài.
- HTTP timeout kéo dài thời gian transaction.
- Payment có thể thành công nhưng câu lệnh DB tiếp theo lỗi, dẫn đến database rollback trong khi payment vẫn được xử lý.
- Retry transaction có thể gọi payment lần nữa và tạo tác động trùng.

Hãy giữ transaction database ngắn, chỉ bao quanh các thao tác cần commit/rollback nguyên tử trên cùng database. Đặt lời gọi HTTP ngoài ranh giới đó, rồi điều phối kết quả bằng trạng thái workflow hoặc cơ chế idempotency phù hợp.

## 3. Vì sao một transaction R2DBC không thể rollback HTTP?

Reactive transaction của Spring được quản lý qua `ReactiveTransactionManager`, thường là `R2dbcTransactionManager`. Manager này điều phối một R2DBC `ConnectionFactory`: bắt đầu transaction, commit hoặc rollback trên connection đó và gắn tài nguyên vào Reactor Context.

Khi Service gọi `WebClient`, WebClient gửi HTTP request qua network. HTTP server bên kia có thể:

1. Nhận request.
2. Thực hiện nghiệp vụ.
3. Commit database riêng của nó.
4. Trả HTTP 200.

Sau đó database cục bộ có thể gặp lỗi và rollback. Không có giao thức chung nào khiến R2DBC transaction manager tự động yêu cầu HTTP server kia undo thao tác vừa commit.

Đây là ranh giới giữa **local transaction** và **distributed workflow**. Nếu cần phối hợp nhiều hệ thống, phải thiết kế giao thức nghiệp vụ như idempotency, outbox, saga hoặc compensation; không thể dựa vào `@Transactional` đơn lẻ.

## 4. Nối WebClient và repository bằng publisher

WebClient là HTTP client reactive. Một phương thức có thể trả `Mono<T>` hoặc `Flux<T>`, nên có thể ghép với publisher repository bằng Reactor:

~~~java
public Mono<ShippingQuote> getQuote(Long orderId) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(orderId)
            ))
            .flatMap(order ->
                    webClient.get()
                            .uri("/quotes/{postalCode}",
                                    order.shippingPostalCode())
                            .retrieve()
                            .bodyToMono(ShippingQuote.class)
            );
}
~~~

Ở đây:

- Repository trả `Mono<Order>`.
- `flatMap` nhận Order và gọi WebClient.
- WebClient trả `Mono<ShippingQuote>`.
- Kết quả được làm phẳng thành một `Mono<ShippingQuote>`.

Không gọi `block()` để chờ HTTP và không gọi `subscribe()` bên trong Service. Hãy trả publisher để caller quản lý kết quả, lỗi và cancellation.

Ghép publisher reactive không đồng nghĩa hai thao tác nằm trong cùng transaction phân tán. Nó chỉ phối hợp thứ tự thực thi và tín hiệu trong một pipeline.

## 5. Chọn thứ tự: HTTP trước hay ghi database trước?

Không có một thứ tự phù hợp cho mọi nghiệp vụ. Cần xem xét điều gì xảy ra nếu bước thứ hai thất bại.

| Thứ tự | Rủi ro chính | Phù hợp khi |
| --- | --- | --- |
| Gọi HTTP trước, sau đó ghi DB | HTTP thành công nhưng DB ghi thất bại | HTTP là thao tác kiểm tra/đọc, hoặc remote call có thể idempotent/compensate |
| Ghi DB trước, sau đó gọi HTTP | DB đã commit nhưng HTTP thất bại | Có trạng thái pending và cơ chế retry/dispatch sau commit |
| Ghi DB và outbox trong cùng transaction, gửi sau | Message có thể được gửi lặp khi worker crash | Cần bảo đảm không mất sự kiện khi DB commit |
| Workflow nhiều bước với saga | Phải quản lý trạng thái và compensation | Nhiều dịch vụ có tác động riêng, không có distributed ACID transaction |

Trước khi chọn thứ tự, hãy trả lời:

- Nếu process chết giữa hai bước, hệ thống có biết việc đang dở ở đâu không?
- Nếu client retry cùng request, có tạo tác động lần hai không?
- Nếu HTTP timeout, remote service có thể đã xử lý request chưa?
- Nếu message được gửi lặp, consumer có idempotent không?
- Có thể bù trừ một bước đã thành công không?

## 6. Trường hợp chỉ cần gọi HTTP đọc dữ liệu

Nếu lời gọi ngoài chỉ đọc thông tin và không tạo side effect, có thể gọi HTTP rồi mới thực hiện transaction ghi cục bộ:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return shippingClient.validateAddress(command.address())
            .flatMap(validation -> {
                if (!validation.valid()) {
                    return Mono.error(
                            new InvalidShippingAddressException()
                    );
                }

                return transactionalOperator.transactional(
                        orderRepository.save(toOrder(command, validation))
                );
            });
}
~~~

Lời gọi kiểm tra địa chỉ hoàn tất trước khi transaction DB bắt đầu. Nếu HTTP thất bại, không có transaction ghi nào được mở. Nếu DB ghi thất bại, thao tác HTTP chỉ là kiểm tra/đọc nên không có side effect cần hoàn tác.

Tuy nhiên, kết quả kiểm tra từ dịch vụ ngoài có thể thay đổi trước lúc commit. Nếu quy tắc cần đảm bảo tại thời điểm xử lý, remote service phải cung cấp reservation/token hoặc xác nhận có thời hạn; một lần validate thuần túy không bảo đảm trạng thái vẫn đúng ở bước sau.

## 7. Ghi trạng thái pending trước, gọi HTTP ngoài transaction

Với thao tác có side effect như thanh toán, một cách phổ biến là tạo trạng thái workflow bền vững:

1. Transaction ngắn tạo Order ở trạng thái PENDING_PAYMENT.
2. Commit transaction.
3. Gọi payment service bằng idempotency key ổn định.
4. Khi thanh toán thành công, transaction mới cập nhật Order thành PAID.
5. Khi thất bại rõ ràng, transaction mới cập nhật thành PAYMENT_FAILED.

Ví dụ:

~~~java
public Mono<OrderResponse> placeOrder(CreateOrderCommand command) {
    return transactionalOperator.transactional(
                    orderRepository.save(toPendingOrder(command))
            )
            .flatMap(order ->
                    paymentClient.authorize(
                                    toPaymentRequest(order),
                                    order.paymentIdempotencyKey()
                            )
                            .flatMap(payment ->
                                    transactionalOperator.transactional(
                                            orderRepository.markPaid(
                                                    order.id(),
                                                    payment.reference()
                                            )
                                    )
                            )
                            .map(this::toResponse)
            );
}
~~~

Đây là khung minh họa. Trong production cần xử lý lỗi HTTP, timeout không rõ kết quả, cập nhật trạng thái thất bại, retry và khôi phục sau khi process dừng. Việc ghi trạng thái PENDING trước giúp hệ thống có một bản ghi để đối chiếu và tiếp tục workflow.

Không đặt WebClient call bên trong publisher được bao bởi `transactional(...)`. Hai transaction ở ví dụ này là hai transaction cục bộ riêng: một transaction tạo pending order, một transaction cập nhật kết quả.

## 8. Timeout HTTP có thể tạo kết quả không xác định

Giả sử payment service nhận request, xử lý và commit thanh toán nhưng response bị mất trên đường về. WebClient timeout. Ứng dụng không thể kết luận payment thất bại chỉ từ timeout.

Hai khả năng:

- Request chưa đến server hoặc server chưa xử lý.
- Server đã xử lý thành công nhưng response không tới client.

Nếu ứng dụng lập tức gửi một payment request mới với key khác, có thể tạo thanh toán trùng. Vì vậy:

- Tạo idempotency key ổn định cho một nghiệp vụ thanh toán.
- Gửi lại cùng key khi retry cùng một yêu cầu logic.
- Remote service phải lưu và nhận diện key để trả lại kết quả trước đó thay vì thực hiện lại.
- Nếu kết quả vẫn không rõ, truy vấn endpoint kiểm tra trạng thái theo key/reference trước khi quyết định retry hoặc compensation.

Không tạo idempotency key mới trong mỗi lần retry. Key phải được tạo một lần cho workflow và được lưu bền vững cùng bản ghi nghiệp vụ.

## 9. Transactional outbox giải quyết bài toán ghi DB và phát event

Một vấn đề kinh điển:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                eventPublisher.publishEvent(
                        new OrderCreated(saved.id())
                ).thenReturn(saved)
        );
~~~

Nếu database commit thành công nhưng publish message thất bại, event bị mất. Nếu publish thành công nhưng transaction database rollback, consumer có thể nhận một event về đơn hàng không tồn tại.

Transactional outbox xử lý bằng cách ghi dữ liệu nghiệp vụ và một hàng outbox trong **cùng một transaction database**:

~~~mermaid
flowchart TD
    A[Service creates order]
    B[Local R2DBC transaction]
    C[(orders table)]
    D[(outbox_event table)]
    E[Commit]
    F[Outbox relay]
    G[Message broker / HTTP endpoint]
    A --> B
    B --> C
    B --> D
    C --> E
    D --> E
    E --> F --> G
~~~

Nếu transaction commit, cả Order và outbox event đều tồn tại. Nếu rollback, cả hai đều không tồn tại. Một tiến trình riêng đọc outbox và gửi event sau commit.

Outbox không làm việc gửi message trở thành exactly-once. Nó bảo đảm event được lưu bền vững cùng dữ liệu nghiệp vụ; relay có thể gửi lại khi gặp lỗi, nên consumer vẫn cần idempotency.

## 10. Thiết kế bảng outbox

Một schema minh họa:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    locked_until TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(status, next_attempt_at, created_at);
~~~

Các trường có ý nghĩa:

- `id`: event ID ổn định, dùng làm idempotency key ở consumer.
- `aggregate_type` và `aggregate_id`: đối tượng nghiệp vụ phát sinh event.
- `aggregate_version`: hỗ trợ giữ thứ tự event theo aggregate nếu cần.
- `event_type`: tên loại sự kiện.
- `payload`: dữ liệu event đã serialize.
- `status`: NEW, PROCESSING, PUBLISHED hoặc trạng thái lỗi theo thiết kế.
- `attempts`: số lần relay thử gửi.
- `next_attempt_at`: thời điểm được phép thử tiếp.
- `locked_until`: lease để worker khác có thể lấy lại việc nếu worker chết.
- `published_at`: thời điểm gửi thành công được ghi nhận.

Schema thực tế cần chọn kiểu UUID, JSON/JSONB, index và timestamp phù hợp database. Nếu payload chứa dữ liệu nhạy cảm, áp dụng chính sách mã hóa, quyền truy cập và thời hạn lưu trữ.

## 11. Ghi Order và outbox event trong cùng transaction

Entity event:

~~~java
@Table("outbox_event")
public record OutboxEvent(
        @Id UUID id,
        @Column("aggregate_type") String aggregateType,
        @Column("aggregate_id") String aggregateId,
        @Column("event_type") String eventType,
        String payload,
        @Column("created_at") Instant createdAt,
        String status
) {}
~~~

Service:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    outboxRepository.save(
                            toOrderCreatedEvent(order)
                    ).thenReturn(order)
            );
}
~~~

Hai repository phải dùng cùng database và cùng R2DBC connection factory do reactive transaction manager quản lý. Khi cả hai thao tác nằm trong cùng pipeline, transaction có thể commit hoặc rollback đồng thời.

Không gọi broker hoặc HTTP trong method này. Nó chỉ ghi dữ liệu nghiệp vụ và ý định phát event.

Nếu dùng `DatabaseClient` để ghi outbox, nó cũng phải tham gia cùng reactive transaction context. Không tự tạo một connection độc lập rồi ghi event ngoài transaction.

## 12. Outbox relay: claim ngắn, gửi ngoài transaction, cập nhật kết quả

Một relay có thể chạy theo chu kỳ hoặc dưới dạng worker nền:

1. Mở transaction ngắn và claim một nhóm event NEW đến hạn.
2. Đánh dấu PROCESSING, tăng attempts và đặt lease.
3. Commit để giải phóng connection/lock.
4. Gửi message qua broker hoặc gọi HTTP ngoài transaction.
5. Nếu thành công, mở transaction ngắn đánh dấu PUBLISHED.
6. Nếu thất bại, đặt next_attempt_at theo backoff hoặc chuyển DEAD_LETTER sau ngưỡng.

Với PostgreSQL, một cách claim thường dùng là:

~~~sql
SELECT id, event_type, payload
FROM outbox_event
WHERE status = 'NEW'
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at, id
LIMIT 50
FOR UPDATE SKIP LOCKED;
~~~

Trong cùng transaction claim, cập nhật những hàng được chọn sang PROCESSING và gán locked_until. Sau đó commit trước khi gửi. `SKIP LOCKED` là cú pháp database-specific; với hệ quản trị khác, dùng cơ chế claim phù hợp như UPDATE có điều kiện và token sở hữu.

Không giữ transaction/row lock trong lúc chờ broker hoặc HTTP response. Nếu worker chết sau khi claim, lease hết hạn cho phép worker khác lấy lại event.

## 13. Vì sao outbox relay có thể gửi trùng?

Giả sử relay gửi event thành công, broker đã nhận, nhưng process chết trước khi cập nhật `status = 'PUBLISHED'`. Khi lease hết hạn, worker khác sẽ gửi lại event.

Đây là hành vi at-least-once delivery. Outbox bảo vệ khỏi mất event khi database commit, nhưng không loại bỏ khả năng gửi trùng ở ranh giới giữa hệ thống ngoài và cập nhật trạng thái cục bộ.

Vì thế:

- Dùng event ID ổn định.
- Consumer ghi nhận event đã xử lý.
- Đặt unique constraint trên event ID ở inbox/processed-message table.
- Cập nhật dữ liệu nghiệp vụ và ghi nhận inbox trong cùng consumer transaction.
- Nếu consumer gọi tiếp hệ thống ngoài, tiếp tục truyền idempotency key hoặc dùng outbox riêng.

Không quảng cáo outbox là exactly-once delivery nếu không có một giao thức đồng bộ và semantics cụ thể ở cả producer, broker lẫn consumer.

## 14. Inbox pattern để chống xử lý event lặp

Consumer có thể lưu ID event đã xử lý:

~~~sql
CREATE TABLE inbox_message (
    event_id UUID PRIMARY KEY,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Trong cùng transaction:

1. Insert event ID vào inbox.
2. Nếu unique constraint báo event đã tồn tại, coi đây là message lặp và không xử lý lại.
3. Nếu insert thành công, cập nhật dữ liệu nghiệp vụ.
4. Commit.

Ví dụ logic khung:

~~~java
@Transactional
public Mono<Void> handle(OrderCreated event) {
    return inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return projectionRepository.updateFrom(event);
            });
}
~~~

`insertIfAbsent` cần được triển khai bằng SQL/constraint phù hợp database; không chỉ SELECT kiểm tra trước rồi INSERT vì hai consumer đồng thời vẫn có thể cùng thấy chưa tồn tại.

Nếu consumer nhận message từ broker, chỉ ACK/commit offset sau khi transaction xử lý inbox và dữ liệu nghiệp vụ thành công. Nếu ACK trước commit, process có thể mất message khi database rollback.

## 15. Idempotency cho lời gọi HTTP

Không chỉ message broker mới cần idempotency. HTTP client cũng có thể retry do timeout, lỗi network hoặc caller gửi lại request.

Ví dụ tạo thanh toán:

~~~java
public Mono<PaymentResult> authorize(
        PaymentCommand command,
        String idempotencyKey) {

    return webClient.post()
            .uri("/payments/authorize")
            .header("Idempotency-Key", idempotencyKey)
            .bodyValue(command)
            .retrieve()
            .bodyToMono(PaymentResult.class);
}
~~~

Remote service phải cam kết semantics cho header này: cùng key và cùng nội dung logic trả lại kết quả trước đó hoặc trạng thái đang xử lý, không tạo thêm thanh toán. Chỉ gửi header mà server không lưu/kiểm tra key thì không tạo ra idempotency.

Idempotency key nên gắn với operation, ví dụ order ID + operation type hoặc UUID được tạo khi tạo workflow. Lưu key bền vững để process restart vẫn dùng lại cùng key.

## 16. Saga cho workflow nhiều hệ thống

Khi một use case gồm nhiều hệ thống có side effect riêng, có thể mô hình hóa thành saga. Saga chia quy trình thành các bước cục bộ; nếu bước sau thất bại, hệ thống chạy hành động bù trừ (compensation) cho những bước trước đã thành công.

Ví dụ đặt hàng:

~~~mermaid
flowchart TD
    A[Create order PENDING]
    B[Reserve inventory]
    C[Authorize payment]
    D[Confirm order]
    E[Release inventory]
    F[Void / refund payment]
    G[Mark order FAILED]
    A --> B --> C --> D
    B -->|Payment failed| E
    E --> G
    C -->|Confirmation failed| F
    F --> E
    E --> G
~~~

Compensation không phải rollback database theo nghĩa ACID. Ví dụ hoàn tiền là một giao dịch mới có thể thất bại hoặc bị trì hoãn; nó chỉ đưa trạng thái nghiệp vụ về một kết quả được chấp nhận.

Saga có thể được điều phối:

- **Orchestration:** một service/workflow coordinator theo dõi trạng thái và gọi từng bước.
- **Choreography:** các service phát/nhận event và phản hồi bằng event tiếp theo.

Với hệ thống cần quan sát và khôi phục dễ dàng, orchestration thường giúp thấy rõ trạng thái từng bước. Choreography giảm sự phụ thuộc vào một coordinator trung tâm nhưng có thể khó theo dõi luồng dài.

## 17. Lưu trạng thái saga trong database

Một bảng workflow có thể lưu:

~~~sql
CREATE TABLE order_workflow (
    id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    state VARCHAR(40) NOT NULL,
    payment_reference VARCHAR(150),
    inventory_reservation_id VARCHAR(150),
    last_error_code VARCHAR(100),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL
);
~~~

Các trạng thái minh họa:

- PENDING
- INVENTORY_RESERVED
- PAYMENT_AUTHORIZED
- COMPLETED
- COMPENSATING
- FAILED

Mỗi bước chỉ chuyển trạng thái hợp lệ. Có thể dùng optimistic locking với version hoặc UPDATE có điều kiện:

~~~sql
UPDATE order_workflow
SET state = 'PAYMENT_AUTHORIZED',
    payment_reference = :reference,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND state = 'INVENTORY_RESERVED';
~~~

Nếu số hàng cập nhật bằng 0, workflow có thể đã chuyển trạng thái bởi một worker khác hoặc đang ở trạng thái không hợp lệ. Không ghi đè trạng thái một cách mù quáng.

## 18. Phân biệt retry, compensation và rollback

Ba khái niệm thường bị nhầm:

| Cơ chế | Mục tiêu | Phạm vi |
| --- | --- | --- |
| Rollback | Hủy thay đổi chưa commit | Một local database transaction |
| Retry | Chạy lại thao tác sau lỗi có thể phục hồi | Một attempt hoặc toàn bộ workflow step |
| Compensation | Tạo hành động mới để bù tác động đã commit ở hệ thống khác | Nhiều hệ thống / saga |

Ví dụ:

- INSERT Order và INSERT Outbox cùng transaction rồi lỗi: rollback cả hai.
- Gửi event thất bại trước khi broker nhận: retry relay theo backoff.
- Payment đã capture nhưng bước giao hàng thất bại: gọi refund/void như compensation.

Không dùng retry để thay thế compensation. Nếu payment đã thành công, chạy lại lệnh capture có thể tạo thêm tác động; cần truy vấn trạng thái và thực hiện hành động nghiệp vụ phù hợp.

## 19. Xử lý lỗi WebClient và phân loại kết quả

WebClient có thể phát lỗi do:

- HTTP 4xx: request không hợp lệ, không được phép hoặc xung đột.
- HTTP 5xx: lỗi phía dịch vụ.
- Timeout: không rõ remote đã xử lý hay chưa.
- DNS/connect/reset: lỗi kết nối.
- Decode error: response không đúng định dạng.

Ví dụ:

~~~java
return webClient.post()
        .uri("/reservations")
        .bodyValue(request)
        .retrieve()
        .onStatus(
                status -> status.is4xxClientError(),
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new RemoteRequestRejected(body))
        )
        .onStatus(
                status -> status.is5xxServerError(),
                response -> Mono.error(new RemoteServiceUnavailable())
        )
        .bodyToMono(ReservationResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

Đây là ví dụ mapping; trong thực tế, tránh đưa toàn bộ response body nhạy cảm vào exception/log. Không retry tất cả 4xx. Một số 409 có thể là kết quả idempotent đã tồn tại; một số 429/503 có thể retry theo Retry-After và deadline.

Timeout hoặc connection reset không cho biết chắc chắn remote side effect chưa xảy ra. Với POST tạo tài nguyên, cần idempotency key hoặc endpoint tra cứu trạng thái.

## 20. Không dùng onErrorResume để che lỗi workflow

Ví dụ nguy hiểm:

~~~java
return paymentClient.authorize(request)
        .onErrorResume(error -> Mono.empty())
        .flatMap(result -> orderRepository.markPaid(orderId));
~~~

Nếu payment thất bại, publisher phục hồi thành empty; bước markPaid không chạy, nhưng caller có thể nhận complete bình thường và hiểu nhầm workflow thành công.

Hãy chuyển lỗi thành trạng thái nghiệp vụ cụ thể hoặc truyền lỗi ra ngoài:

~~~java
return paymentClient.authorize(request)
        .flatMap(result -> markPaymentAuthorized(orderId, result))
        .onErrorResume(error ->
                markPaymentFailed(orderId, classify(error))
                        .then(Mono.error(error))
        );
~~~

Trong ví dụ này, việc đánh dấu thất bại được thực hiện trong transaction riêng; sau đó lỗi gốc được truyền tiếp. Nếu kết quả remote không xác định do timeout, không nên ghi PAYMENT_FAILED ngay; có thể cần trạng thái PAYMENT_UNKNOWN và bước reconciliation.

## 21. Đặt transaction đúng phạm vi

Một mẫu tổ chức rõ ràng:

~~~java
public Mono<Order> createAndRequestPayment(
        CreateOrderCommand command) {

    return transactionalOperator.transactional(
                    orderRepository.save(toPendingOrder(command))
            )
            .flatMap(order ->
                    paymentClient.authorize(
                                    toPaymentRequest(order),
                                    order.idempotencyKey()
                            )
                            .flatMap(payment ->
                                    transactionalOperator.transactional(
                                            orderRepository.markPaymentResult(
                                                    order.id(),
                                                    payment.status(),
                                                    payment.reference()
                                            )
                                    )
                            )
            );
}
~~~

Ở đây:

- Transaction thứ nhất chỉ lưu trạng thái pending.
- HTTP call diễn ra sau commit.
- Transaction thứ hai chỉ lưu kết quả remote.

Code production cần bổ sung nhánh lỗi, timeout, reconciliation và idempotency. Nếu payment thành công nhưng transaction thứ hai thất bại, workflow phải có thể tiếp tục cập nhật kết quả mà không capture lại payment.

Không bọc toàn bộ phương thức bằng `@Transactional` nếu mục tiêu là các thao tác database được commit riêng trước và sau HTTP. Nếu dùng annotation, tách từng local transaction thành bean/method phù hợp hoặc dùng `TransactionalOperator` để thể hiện ranh giới tường minh.

## 22. Sự kiện sau commit và giới hạn của event listener

Một lựa chọn khác là phát application event sau khi transaction commit. Với transaction đồng bộ, Spring có `@TransactionalEventListener(phase = AFTER_COMMIT)` để listener chỉ chạy sau commit.

Tuy nhiên, cần chú ý:

- Event trong bộ nhớ có thể mất nếu process chết sau commit nhưng trước khi listener xử lý.
- Listener có thể chạy nhưng việc gửi message thất bại.
- Retry listener có thể gửi trùng.
- Với reactive transaction, transaction context nằm trong Reactor Context chứ không phải ThreadLocal; việc phát và nhận event phải bảo toàn reactive transaction context theo cơ chế Spring hỗ trợ.

Trong Spring hỗ trợ reactive transaction events, có thể dùng `TransactionalEventPublisher` để phát event mang reactive transaction context. Hãy đối chiếu API và cách dùng với phiên bản Spring Framework đang chạy; không giả định một event được publish bằng application event thông thường sẽ tự động có transaction synchronization như mô hình imperative.

Nếu yêu cầu là **không mất event sau khi database commit**, transactional outbox thường bền vững hơn event chỉ tồn tại trong bộ nhớ. Event listener sau commit có thể phù hợp cho tác vụ phụ, không quan trọng hoặc có thể tái tạo.

## 23. Outbox polling và Change Data Capture

Có hai cách phổ biến để chuyển outbox thành message:

**Polling relay**

- Worker truy vấn các hàng outbox chưa publish.
- Claim theo batch và lease.
- Gửi message.
- Đánh dấu trạng thái.
- Dễ triển khai với repository/DatabaseClient và scheduler.

**Change Data Capture (CDC)**

- Công cụ đọc transaction log của database.
- Khi outbox row được commit, CDC connector phát thay đổi tới broker.
- Có thể giảm polling query và độ trễ.
- Cần vận hành connector, offset, schema registry/serialization và retention log.

CDC không loại bỏ idempotency ở consumer. Event vẫn có thể được phát lại khi connector khôi phục offset hoặc xử lý lại log.

## 24. Giữ thứ tự event theo aggregate

Nếu một Order phát OrderCreated rồi OrderPaid, consumer có thể cần xử lý đúng thứ tự. Outbox có thể lưu aggregate ID và version:

~~~text
order_id = 900
aggregate_version = 1
event_type = OrderCreated

order_id = 900
aggregate_version = 2
event_type = OrderPaid
~~~

Relay nên đảm bảo không phát version 2 trước version 1 cho cùng aggregate nếu hợp đồng yêu cầu thứ tự. Nhiều worker dùng `SKIP LOCKED` có thể lấy các event của cùng aggregate ở các batch khác nhau; cần partition theo aggregate, claim theo thứ tự hoặc cơ chế tuần tự hóa phù hợp.

Consumer cũng có thể lưu version cuối đã áp dụng và từ chối/hoãn event cũ hoặc vượt version theo quy tắc. Không giả định broker đảm bảo thứ tự toàn cục nếu không cấu hình partition/key và semantics phù hợp.

## 25. Sự kiện đến từ bên ngoài: lưu trước, ACK sau

Khi ứng dụng nhận webhook hoặc message từ hệ thống ngoài, quy tắc tương tự áp dụng theo chiều ngược:

1. Xác thực nguồn và chữ ký webhook.
2. Ghi nhận event ID và payload cần thiết vào inbox hoặc bảng nhận sự kiện.
3. Commit database.
4. Trả HTTP 2xx/202 hoặc ACK broker.
5. Xử lý nghiệp vụ từ bản ghi đã lưu, có thể ở worker riêng.

Nếu trả 2xx trước khi lưu bền vững, process có thể chết và event bị mất vì sender nghĩ đã giao thành công. Nếu xử lý side effect lâu trước khi ACK, sender có thể timeout và gửi lại, nên cần idempotency.

Ví dụ endpoint tiếp nhận webhook:

~~~java
@PostMapping("/webhooks/payment")
public Mono<ResponseEntity<Void>> receivePaymentWebhook(
        @RequestBody Mono<PaymentWebhook> body) {

    return body.flatMap(webhook ->
                    webhookService.storeIfNew(webhook)
            )
            .thenReturn(ResponseEntity.accepted().build());
}
~~~

Service `storeIfNew` nên ghi inbox event và trạng thái cần xử lý trong một transaction. Chỉ trả 202 sau khi publisher lưu trữ hoàn tất. Chữ ký, timestamp, replay protection và xác thực webhook phải được xử lý trước khi tin payload.

## 26. Cấu trúc consumer idempotent

Một consumer có thể xử lý event theo mẫu:

~~~java
@Transactional
public Mono<Void> handle(PaymentWebhook event) {
    return inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return orderRepository.applyPaymentStatus(
                        event.orderId(),
                        event.paymentStatus()
                );
            });
}
~~~

Inbox insert và cập nhật Order phải cùng transaction. Nếu cập nhật Order thất bại, inbox insert cũng rollback, để event có thể được gửi lại và xử lý tiếp. Nếu transaction commit, lần gửi lặp sau sẽ gặp unique conflict/insert-if-absent false và không áp dụng nghiệp vụ lần hai.

Nếu event được ACK sau commit, hệ thống tránh mất event do ACK sớm. Nếu process chết sau commit nhưng trước ACK, broker có thể giao lại; inbox xử lý trùng an toàn.

## 27. Retry và backoff cho lời gọi ngoài

HTTP hoặc broker call có thể gặp lỗi tạm thời. Retry cần:

- Giới hạn số lần.
- Backoff và jitter.
- Chỉ retry lỗi phù hợp như 429/503 hoặc lỗi kết nối có thể phục hồi.
- Tôn trọng Retry-After khi có.
- Giữ nguyên idempotency key.
- Có deadline tổng.
- Không retry lỗi validation/authorization một cách chung chung.

Ví dụ:

~~~java
Retry retry = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(3))
        .jitter(0.5)
        .filter(this::isRetryableRemoteFailure);

return webClient.post()
        .uri("/reservations")
        .header("Idempotency-Key", reservationKey)
        .bodyValue(request)
        .retrieve()
        .bodyToMono(ReservationResponse.class)
        .retryWhen(retry)
        .timeout(Duration.ofSeconds(10));
~~~

Ví dụ này chỉ retry một publisher HTTP. Nếu publisher nằm trong database transaction, retry có thể kéo dài transaction hoặc lặp side effect trong transaction. Thông thường hãy thực hiện remote retry ngoài local DB transaction và dùng key ổn định.

## 28. Bảo đảm trạng thái workflow có thể phục hồi

Một workflow bền vững nên có:

- Trạng thái hiện tại và bước tiếp theo.
- ID tương quan tới các hệ thống ngoài.
- Idempotency key.
- Số lần thử và thời điểm retry tiếp.
- Lỗi cuối cùng được phân loại, không chỉ lưu raw message.
- Lease/owner để worker có thể tiếp quản khi process chết.
- Cơ chế reconciliation cho trạng thái không xác định.
- Hành động compensation khi cần.

Không chỉ lưu log để suy ra workflow đã đi tới đâu. Log có thể bị thiếu hoặc hết retention; trạng thái cần thiết để tiếp tục phải được lưu bền vững trong database.

## 29. Quan sát và vận hành tích hợp

Các metric hữu ích:

| Metric | Mục đích |
| --- | --- |
| HTTP dependency latency/error rate | Theo dõi hệ thống ngoài |
| Outbox pending count/oldest age | Phát hiện relay chậm hoặc ngừng |
| Outbox retry/exhausted count | Phát hiện event lỗi lặp |
| Inbox duplicate count | Đo message được giao lại |
| Workflow age by state | Tìm workflow bị kẹt |
| Compensation success/failure | Theo dõi saga phục hồi |
| Idempotency conflict count | Theo dõi request/event lặp |
| Database pool active/pending | Phát hiện transaction giữ connection lâu |

Log nên có correlation ID, order/workflow ID, event ID và idempotency key ở dạng an toàn. Không log token, thông tin thanh toán hoặc payload nhạy cảm đầy đủ.

Đặt cảnh báo cho outbox tồn đọng lâu, workflow ở trạng thái PENDING quá hạn, payment UNKNOWN chưa reconciliation và compensation thất bại. Các trạng thái này cần quy trình vận hành cụ thể chứ không chỉ retry vô hạn.

## 30. Kiểm thử tích hợp giữa database và hệ thống ngoài

Không thể kiểm chứng toàn bộ workflow chỉ bằng mock repository. Nên có nhiều lớp test:

**Service unit test**

- Xác nhận thứ tự gọi remote và local publisher.
- Xác nhận mapping lỗi và trạng thái workflow.
- Xác nhận idempotency key không thay đổi qua retry.
- Xác nhận nhánh compensation được gọi khi cần.

**Database integration test**

- Order và outbox cùng commit.
- Nếu ghi outbox lỗi, Order cũng rollback.
- Inbox và cập nhật nghiệp vụ cùng commit/rollback.
- Unique constraint ngăn xử lý event lặp.
- Claim/lease cho nhiều worker không lấy cùng event cùng lúc.

**HTTP contract/component test**

- Remote trả 2xx, 4xx, 5xx.
- Timeout trước/sau khi server xử lý.
- Response không hợp lệ.
- Idempotency key được truyền đúng.

**End-to-end/recovery test**

- Process chết sau commit trước khi gửi event.
- Process chết sau khi gửi nhưng trước khi đánh dấu published.
- Remote thành công nhưng DB update kết quả thất bại.
- Message được giao lại sau khi consumer commit nhưng trước ACK.
- Saga compensation thất bại và được tiếp tục.

Testcontainers có thể cung cấp database thật cho R2DBC integration test. HTTP service có thể được giả lập bằng WireMock hoặc mock web server; cần giữ kịch bản timeout và response loss để kiểm tra kết quả không xác định.

## 31. Các lỗi thường gặp

1. **Giữ transaction database trong lúc chờ HTTP.** Connection và lock bị giữ lâu.
2. **Cho rằng @Transactional rollback được HTTP hoặc message broker.** Transaction manager chỉ quản lý resource đã enlist.
3. **Ghi DB rồi publish event trực tiếp.** Có thể commit DB nhưng mất event.
4. **Publish event rồi mới commit DB.** Consumer có thể nhận event về dữ liệu chưa tồn tại.
5. **Retry POST bằng idempotency key mới.** Có thể tạo side effect trùng.
6. **Coi HTTP timeout là remote thất bại.** Remote có thể đã xử lý nhưng response bị mất.
7. **Đánh dấu PAYMENT_FAILED khi kết quả không xác định.** Có thể bỏ qua một khoản thanh toán đã thành công.
8. **Outbox relay giữ row lock khi gửi network.** Làm transaction và connection kéo dài.
9. **Giả định outbox cung cấp exactly-once.** Relay có thể gửi lại sau crash.
10. **Consumer ACK trước khi commit.** Có thể mất message nếu database rollback.
11. **Không có inbox/unique event ID.** Message giao lại có thể áp dụng nghiệp vụ lần hai.
12. **Dùng event listener trong bộ nhớ cho event không được phép mất.** Process có thể dừng sau commit trước khi listener hoàn tất.
13. **Dùng @TransactionalEventListener theo mô hình imperative mà không xét reactive context.** Reactive transaction cần giữ context theo cơ chế Spring hỗ trợ.
14. **Dùng retry thay cho compensation.** Retry không đảo ngược side effect đã commit.
15. **Không lưu trạng thái workflow.** Process restart không biết phải tiếp tục từ bước nào.
16. **Không giới hạn retry hoặc không có dead-letter/reconciliation.** Workflow có thể lặp vô hạn và che giấu lỗi vận hành.

## Quy tắc lựa chọn nhanh

- Chỉ bao các thao tác database cần nguyên tử trong reactive transaction.
- Không giữ connection/row lock khi chờ HTTP hoặc broker.
- Với HTTP chỉ đọc/validate, có thể gọi trước transaction rồi ghi local, nhưng đánh giá tính hợp lệ theo thời gian.
- Với side effect đồng bộ, lưu trạng thái pending, gọi remote ngoài transaction và cập nhật kết quả trong transaction mới.
- Dùng idempotency key ổn định cho HTTP command có thể được retry.
- Dùng transactional outbox khi dữ liệu local và ý định phát event phải commit cùng nhau.
- Dùng inbox/unique event ID để consumer xử lý message lặp an toàn.
- Dùng saga và compensation cho workflow nhiều hệ thống.
- Xem timeout là kết quả có thể không xác định; reconciliation trước khi tạo tác động mới.
- Đặt retry có giới hạn, backoff, jitter và deadline.
- ACK message sau khi inbox và thay đổi nghiệp vụ đã commit.
- Theo dõi outbox age, workflow state, dependency latency và compensation.
- Kiểm thử crash window, duplicate delivery và lỗi giữa các bước.

Phối hợp lời gọi HTTP hoặc sự kiện ngoài với thao tác lưu trữ đòi hỏi ranh giới nhất quán rõ ràng. Reactive transaction của Spring Data R2DBC chỉ bảo vệ các thao tác trên database mà transaction manager quản lý; nó không thể hoàn tác side effect đã xảy ra ở hệ thống khác. Hãy giữ transaction cục bộ ngắn, dùng trạng thái workflow và idempotency cho lời gọi HTTP, transactional outbox để không mất event sau commit, inbox để chống xử lý lặp và saga/compensation cho quy trình nhiều dịch vụ. Khi thiết kế cả timeout, retry, crash window và reconciliation, ứng dụng có thể phục hồi an toàn khi một hệ thống ngoài chậm hoặc thất bại.
