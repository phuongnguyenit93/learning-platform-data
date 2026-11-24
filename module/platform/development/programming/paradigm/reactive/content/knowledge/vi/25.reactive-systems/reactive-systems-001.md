# Hệ thống phản ứng

## Bốn đặc tính: đáp ứng, chịu lỗi, co giãn và hướng thông điệp

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Các kỹ thuật đó là nền tảng hữu ích để xây dựng một thành phần xử lý bất đồng bộ. Ở cấp độ kiến trúc, một **Reactive System** còn đặt ra yêu cầu rộng hơn: toàn hệ thống cần phản hồi nhanh và ổn định, tiếp tục cung cấp dịch vụ khi có lỗi, thích nghi với tải thay đổi và giao tiếp qua thông điệp bất đồng bộ.

Bốn đặc tính này thường được gọi là **Responsive, Resilient, Elastic và Message-Driven**. Chúng liên kết với nhau: hướng thông điệp giúp tách rời các thành phần và kiểm soát luồng công việc; sự tách rời đó hỗ trợ cô lập lỗi và mở rộng; khả năng chịu lỗi và co giãn giúp hệ thống duy trì khả năng đáp ứng khi có sự cố hoặc tải tăng. Một ứng dụng dùng `Mono` và `Flux` chưa tự động trở thành Reactive System. Ta cần thiết kế cả ranh giới dịch vụ, giao tiếp, quản lý tải, phục hồi và vận hành.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích bốn đặc tính Responsive, Resilient, Elastic và Message-Driven.
- Phân biệt khả năng đáp ứng với tốc độ xử lý trung bình hoặc thông lượng cực đại.
- Thiết kế cô lập lỗi và phục hồi có kiểm soát ở cấp thành phần, dịch vụ và hệ thống.
- Giải thích vì sao co giãn cần giới hạn hàng đợi, điều tiết tải và năng lực tăng/giảm.
- Chọn kiểu giao tiếp bằng thông điệp phù hợp với ranh giới dịch vụ.
- Liên hệ backpressure của Reactive Streams với quản lý luồng dữ liệu ở cấp hệ thống.
- Nhận diện các anti-pattern như retry vô hạn, hàng đợi không giới hạn và chia sẻ trạng thái mutable.
- Đề xuất cách đo lường và kiểm thử bốn đặc tính trong một ứng dụng Java.

## 1. Reactive System là gì?

Reactive System là hệ thống được thiết kế để giữ hành vi có thể dự đoán khi tải thay đổi, thành phần gặp lỗi hoặc các dịch vụ giao tiếp qua mạng. Mục tiêu không chỉ là xử lý bất đồng bộ. Hệ thống phải duy trì trải nghiệm có ý nghĩa cho người dùng và các hệ thống phụ thuộc trong những điều kiện vận hành thực tế.

Bốn đặc tính có thể tóm tắt như sau:

| Đặc tính | Ý nghĩa | Câu hỏi thiết kế |
|---|---|---|
| **Responsive — Đáp ứng** | Phản hồi kịp thời, có thể dự đoán và phát hiện vấn đề | Người dùng nhận phản hồi trong ngân sách thời gian nào? |
| **Resilient — Chịu lỗi** | Duy trì dịch vụ khi thành phần gặp lỗi và phục hồi sau sự cố | Một dependency hỏng có làm sập toàn hệ thống không? |
| **Elastic — Co giãn** | Thích nghi năng lực xử lý khi tải tăng hoặc giảm | Hệ thống mở rộng và thu hẹp mà không mất kiểm soát ra sao? |
| **Message-Driven — Hướng thông điệp** | Các thành phần giao tiếp qua thông điệp bất đồng bộ, có ranh giới rõ | Các thành phần có thể tiến triển độc lập và kiểm soát luồng công việc không? |

~~~mermaid
flowchart TB
    M[Message-Driven\nGiao tiếp bất đồng bộ] --> R[Resilient\nCô lập và phục hồi lỗi]
    M --> E[Elastic\nĐiều tiết và phân phối tải]
    R --> P[Responsive\nPhản hồi có thể dự đoán]
    E --> P
    P --> F[Trải nghiệm và dịch vụ ổn định]
~~~

Sơ đồ mô tả mối quan hệ hỗ trợ giữa các đặc tính, không phải thứ tự triển khai bắt buộc. Một hệ thống có thể bắt đầu từ mục tiêu đáp ứng, rồi xác định ranh giới thông điệp, chiến lược phục hồi và cách mở rộng phù hợp.

### Reactive System khác với Reactive Programming

Hai khái niệm liên quan nhưng có phạm vi khác nhau:

- **Reactive Programming** là cách lập trình mô tả các giá trị hoặc sự kiện thay đổi theo thời gian, thường qua Publisher, Subscriber và toán tử kết hợp.
- **Reactive Systems** là cách thiết kế kiến trúc toàn hệ thống để đạt được khả năng đáp ứng, chịu lỗi, co giãn và hướng thông điệp.

Project Reactor cung cấp `Mono`, `Flux`, backpressure và các toán tử để xây dựng thành phần reactive. Spring WebFlux cung cấp mô hình web bất đồng bộ. Nhưng các công cụ đó không tự tạo ra chiến lược triển khai nhiều instance, cô lập lỗi giữa dịch vụ, lưu thông điệp bền vững hoặc tự động mở rộng năng lực. Những quyết định đó thuộc về thiết kế hệ thống và vận hành.

## 2. Responsive — Đáp ứng

Một hệ thống đáp ứng đưa ra phản hồi trong khoảng thời gian phù hợp với nhu cầu người dùng và hợp đồng của dịch vụ. Phản hồi cần có thể dự đoán: khi tải tăng hoặc một thành phần chậm, hệ thống phải phát hiện tình trạng đó và có hành vi được thiết kế trước.

Đáp ứng không đồng nghĩa với thông lượng cao. Một hệ thống có thể xử lý hàng triệu tác vụ mỗi phút nhưng vẫn khiến một request cụ thể chờ quá lâu. Ngược lại, một hệ thống có thông lượng vừa phải nhưng giữ được độ trễ ổn định trong giới hạn đã cam kết có thể đem lại trải nghiệm tốt hơn.

### Đặt ngân sách thời gian cho request

Giả sử endpoint tạo trang chi tiết đơn hàng cần gọi ba dịch vụ:

- Đọc thông tin đơn hàng: tối đa 150 ms.
- Đọc khách hàng: tối đa 200 ms.
- Đọc trạng thái giao hàng: tối đa 250 ms.
- Ghép dữ liệu và ghi response: phần ngân sách còn lại.

Nếu tổng deadline của request là 700 ms, các bước phải chia sẻ cùng một ngân sách. Không nên để mỗi dependency retry hoặc timeout độc lập đến mức tổng thời gian vượt deadline của request.

Ví dụ với Reactor:

~~~java
Mono<OrderDetail> loadDetail(String orderId) {
    return orderClient.find(orderId)
        .flatMap(order ->
            Mono.zip(
                customerClient.find(order.customerId()),
                deliveryClient.status(orderId)
            )
            .map(tuple ->
                new OrderDetail(order, tuple.getT1(), tuple.getT2())
            )
        )
        .timeout(Duration.ofMillis(700));
}
~~~

Các lời gọi reactive độc lập có thể tiến hành đồng thời trong `zip`. Timeout ngoài cùng giới hạn thời gian của chuỗi Mono. Trong hệ thống thực tế, từng dependency có thể có timeout riêng ngắn hơn để xác định nguồn chậm và chọn fallback phù hợp; deadline tổng vẫn phải được giữ.

### Đo độ trễ theo phân vị

Thời gian phản hồi trung bình có thể che giấu những request rất chậm. Nên theo dõi các phân vị như p50, p95 và p99 cùng với tỷ lệ lỗi và thông lượng.

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa request hoàn tất trong khoảng thời gian này hoặc nhanh hơn |
| p95 | 95% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn |
| p99 | Phát hiện phần đuôi độ trễ, nơi một nhóm request chịu ảnh hưởng lớn |
| Error rate | Tỷ lệ request thất bại theo hợp đồng |
| Throughput | Số request hoặc sự kiện hoàn tất trong một đơn vị thời gian |
| Saturation | Mức bão hòa của CPU, thread, connection pool, queue hoặc tài nguyên khác |

Một hệ thống có p50 thấp nhưng p99 tăng mạnh có thể đang gặp hàng đợi dài, lock contention, retry storm hoặc một dependency không ổn định.

### Trả phản hồi có ý nghĩa khi không thể hoàn tất ngay

Không phải mọi yêu cầu đều phải xử lý xong trong một HTTP request. Với công việc dài như xuất báo cáo hoặc xử lý dữ liệu lớn, có thể trả mã job và trạng thái tiếp nhận:

~~~java
Mono<JobAccepted> submit(ExportCommand command) {
    return jobRepository.create(command)
        .flatMap(job ->
            outboxRepository.append(ExportRequested.from(job))
                .thenReturn(new JobAccepted(job.id(), "ACCEPTED"))
        );
}
~~~

Caller nhận phản hồi nhanh rằng yêu cầu đã được ghi nhận. Công việc tiếp tục trong worker độc lập, và client truy vấn trạng thái bằng job ID. Cách này đáp ứng tốt hơn so với giữ một kết nối HTTP mở vô thời hạn, miễn là hợp đồng sản phẩm chấp nhận xử lý bất đồng bộ.

## 3. Resilient — Chịu lỗi

Một hệ thống chịu lỗi có thể tiếp tục cung cấp phần dịch vụ cần thiết khi một thành phần thất bại. Nó cũng có khả năng phục hồi sau lỗi mà không buộc toàn bộ hệ thống phải dừng.

Chịu lỗi không có nghĩa là không bao giờ xảy ra lỗi. Mạng có thể mất kết nối, node có thể khởi động lại, dịch vụ phụ thuộc có thể quá tải và dữ liệu đầu vào có thể không hợp lệ. Thiết kế cần giả định những tình huống này sẽ xảy ra.

### Cô lập lỗi

Nếu một dịch vụ phụ thuộc bị treo và giữ toàn bộ thread hoặc connection, lỗi có thể lan sang các request không liên quan. Cô lập lỗi giúp giới hạn phạm vi ảnh hưởng.

Một số cơ chế thường dùng:

- **Timeout:** không chờ dependency vô hạn.
- **Circuit breaker:** tạm ngừng gọi dependency đang liên tục thất bại, cho nó thời gian phục hồi.
- **Bulkhead:** giới hạn tài nguyên dành cho từng nhóm công việc để một nhóm không chiếm hết năng lực của nhóm khác.
- **Fallback:** cung cấp kết quả thay thế khi nghiệp vụ cho phép.
- **Retry có giới hạn:** thử lại lỗi tạm thời với backoff và jitter.
- **Health check và readiness:** phân biệt instance còn sống với instance đủ khả năng nhận tải.

Ví dụ dùng timeout và fallback có điều kiện:

~~~java
Mono<ProductView> product =
    catalogClient.find(productId)
        .timeout(Duration.ofMillis(300))
        .onErrorResume(TimeoutException.class, error ->
            productCache.findRecent(productId)
        );
~~~

Fallback chỉ phù hợp nếu dữ liệu cache đủ mới cho mục đích sử dụng. Không nên dùng giá trị cũ để quyết định một thao tác nhạy cảm như thanh toán hoặc giữ mặt hàng cuối cùng trong kho.

### Retry phải có giới hạn

Retry có thể giúp vượt qua lỗi mạng thoáng qua, nhưng retry vô hạn làm tăng tải lên dịch vụ vốn đang gặp vấn đề. Khi nhiều instance cùng retry theo một chu kỳ giống nhau, chúng có thể tạo ra retry storm.

~~~java
Mono<Inventory> inventory =
    Mono.defer(() -> inventoryClient.find(productId))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(1))
                .jitter(0.5)
                .filter(this::isTransientFailure)
        )
        .timeout(Duration.ofSeconds(2));
~~~

Ví dụ cho phép tối đa hai lần retry sau lần gọi đầu, dùng backoff, jitter và deadline tổng. `isTransientFailure` phải phân loại lỗi theo hợp đồng dependency. Không retry lỗi dữ liệu hoặc lỗi nghiệp vụ không thể khắc phục bằng việc gọi lại cùng request.

Với thao tác ghi, timeout không chứng minh server chưa commit. Hãy dùng idempotency key hoặc truy vấn trạng thái trước khi gửi lại để tránh tạo giao dịch trùng.

### Phục hồi thay vì chỉ che giấu lỗi

Fallback không nên biến mọi lỗi thành thành công giả. Nếu hệ thống không thể cung cấp dữ liệu chính xác, một phản hồi lỗi rõ ràng có thể tốt hơn một giá trị mặc định gây hiểu nhầm.

Cần phân biệt:

- **Lỗi có thể phục hồi:** kết nối tạm thời bị reset, node vừa khởi động lại.
- **Lỗi nghiệp vụ:** không đủ số dư, trạng thái đơn không cho phép thao tác.
- **Lỗi dữ liệu:** payload sai schema hoặc vi phạm invariant.
- **Lỗi cấu hình:** endpoint sai, credentials hết hạn, chứng thư không hợp lệ.

Mỗi nhóm cần chính sách khác nhau. Retry phù hợp với một số lỗi hạ tầng tạm thời; lỗi nghiệp vụ thường cần trả kết quả từ chối; lỗi dữ liệu cần sửa hoặc cách ly.

## 4. Elastic — Co giãn

Một hệ thống co giãn có thể điều chỉnh năng lực xử lý theo tải. Khi lượng request hoặc sự kiện tăng, hệ thống có thể tăng worker, instance hoặc partition để xử lý. Khi tải giảm, nó có thể thu hẹp tài nguyên để tránh lãng phí.

Co giãn không chỉ là thêm CPU hoặc thêm pod. Nếu tất cả instance đều phụ thuộc vào một database có connection pool cố định, tăng số instance có thể làm database quá tải trước khi thông lượng tăng.

### Mở rộng ngang và dọc

- **Mở rộng dọc (vertical scaling):** tăng CPU, RAM hoặc năng lực của một node.
- **Mở rộng ngang (horizontal scaling):** thêm nhiều instance/worker cùng xử lý các phần công việc được phân phối.

Mở rộng ngang thường phù hợp với worker stateless và tác vụ có thể phân vùng theo khóa. Tuy nhiên, hệ thống cần giải quyết phân phối công việc, thứ tự theo aggregate, chống xử lý trùng và giới hạn tài nguyên dùng chung.

~~~mermaid
flowchart LR
    Q[Message queue / partitioned stream] --> W1[Worker 1]
    Q --> W2[Worker 2]
    Q --> W3[Worker 3]
    W1 --> DB[(Shared data store)]
    W2 --> DB
    W3 --> DB
~~~

Thêm worker giúp tăng năng lực tiêu thụ khi queue có đủ công việc độc lập. Nhưng nếu mọi message cùng một aggregate phải xử lý tuần tự, chúng cần được phân vùng hoặc điều phối để không phá thứ tự.

### Giới hạn hàng đợi và backpressure

Hàng đợi không giới hạn thường biến quá tải ngắn hạn thành sự cố kéo dài. Khi producer phát nhanh hơn consumer xử lý, số message chờ tăng, bộ nhớ bị chiếm và độ trễ ngày càng lớn.

Một hệ thống co giãn cần xác định:

- Giới hạn queue hoặc buffer.
- Chính sách khi queue đầy: backpressure, từ chối, lưu bền vững hoặc drop theo ngữ nghĩa.
- Số worker và concurrency tối đa.
- Năng lực database, broker và dịch vụ phụ thuộc.
- Thời gian tối đa một message được phép nằm trong queue.
- Cách tăng/giảm worker dựa trên tải thực tế.

Trong Reactor, backpressure của Reactive Streams cho phép Subscriber báo demand và Publisher tuân thủ lượng dữ liệu được yêu cầu khi nguồn hỗ trợ giao thức:

~~~java
Flux<Event> processed =
    eventSource.events()
        .limitRate(128)
        .flatMap(this::processAsync, 16);
~~~

Ví dụ minh họa việc điều tiết request upstream và giới hạn 16 Publisher con đang hoạt động. `limitRate` không phải giới hạn tổng dung lượng của mọi queue trong hệ thống, và nó không thể ép một nguồn ngoài giao thức Reactive Streams tuân thủ demand nếu adapter đã buffer không giới hạn.

Đối với message broker, cần cấu hình prefetch, consumer concurrency, partition assignment, acknowledgement và giới hạn bộ đệm theo khả năng của broker. Backpressure trong một process và điều tiết message qua broker có liên quan nhưng là hai lớp quản lý khác nhau.

### Co giãn cần metric phù hợp

Autoscaling chỉ dựa trên CPU có thể không phù hợp với workload I/O-bound. Một worker có thể dùng ít CPU nhưng queue lag tăng nhanh vì database hoặc API phụ thuộc chậm.

Các tín hiệu có thể dùng để đánh giá năng lực:

- Queue depth và consumer lag.
- Tuổi của message cũ nhất.
- Throughput hoàn tất theo worker.
- Thời gian xử lý mỗi message.
- Số connection đang dùng và thời gian chờ connection.
- CPU, heap, GC và thread utilization.
- Tỷ lệ retry, timeout và rejection.

Không nên tăng worker vô hạn khi dependency phía sau đã bão hòa. Khi database đạt giới hạn connection, thêm consumer chỉ làm tăng tranh chấp và độ trễ. Hệ thống cần giới hạn concurrency toàn cục hoặc phân bổ quota theo dịch vụ.

## 5. Message-Driven — Hướng thông điệp

Trong hệ thống hướng thông điệp, các thành phần giao tiếp bằng cách gửi và nhận thông điệp bất đồng bộ qua những ranh giới rõ ràng. Sender không cần gọi trực tiếp một method trên receiver và giữ thread chờ receiver hoàn thành.

Thông điệp có thể là:

- **Command:** yêu cầu một thành phần thực hiện hành động, ví dụ `ReserveInventory`.
- **Event:** thông báo một điều đã xảy ra, ví dụ `OrderCreated`.
- **Request/Reply:** gửi yêu cầu và nhận phản hồi tương ứng qua cơ chế bất đồng bộ.
- **Stream item:** một phần tử trong luồng dữ liệu liên tục, ví dụ `PriceTick`.

Message-driven giúp giảm phụ thuộc thời gian và vị trí giữa các thành phần. Sender có thể gửi message tới địa chỉ logic hoặc broker; receiver có thể chạy ở instance khác, process khác hoặc node khác.

### Ghép lỏng bằng message contract

Ví dụ một dịch vụ đơn hàng phát sự kiện:

~~~java
record OrderCreated(
    String eventId,
    String orderId,
    Instant occurredAt,
    long version
) {}

Mono<Void> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            outboxRepository.append(
                new OrderCreated(
                    UUID.randomUUID().toString(),
                    saved.id(),
                    Instant.now(),
                    saved.version()
                )
            )
        )
        .then();
}
~~~

Trong thiết kế production, lưu đơn hàng và outbox nên nằm trong cùng transaction nếu cùng transactional resource. Worker outbox phát message sau khi commit. Các consumer như inventory, notification hoặc analytics đăng ký xử lý theo hợp đồng của mình.

Message contract cần có schema và version rõ ràng. Không nên gửi trực tiếp object nội bộ của service nếu nó khiến consumer phụ thuộc vào cấu trúc triển khai hoặc thay đổi class không kiểm soát.

### Delivery semantics và idempotency

Broker có thể giao lại message khi consumer xử lý xong nhưng acknowledgement bị mất. Vì vậy, consumer thường phải chấp nhận giao ít nhất một lần và xử lý idempotent.

~~~java
Mono<Void> handle(OrderCreated event) {
    return inboxRepository.tryRegister(event.eventId())
        .flatMap(firstDelivery -> {
            if (!firstDelivery) {
                return Mono.empty();
            }

            return inventoryService.reserveFor(event.orderId());
        });
}
~~~

Đây là minh họa khái niệm inbox/deduplication. Việc đăng ký event ID và tác dụng phụ cần được bảo vệ bằng transaction hoặc cơ chế atomic phù hợp; nếu chỉ lưu ID rồi crash trước khi xử lý, consumer có thể bỏ sót công việc. Nếu tác dụng phụ ở hệ thống khác, cần idempotency key tại hệ thống đó hoặc một workflow có thể đối soát.

Không nên mặc định message broker bảo đảm exactly-once cho toàn bộ business workflow. Cần xác định rõ delivery guarantee, acknowledgement boundary, retry và cách xử lý message trùng.

## 6. Bốn đặc tính hỗ trợ lẫn nhau

Bốn đặc tính không phải bốn tính năng tách biệt. Một quyết định kiến trúc có thể hỗ trợ nhiều đặc tính cùng lúc.

Ví dụ, dùng broker và worker độc lập:

1. **Message-Driven:** API ghi command hoặc event vào broker/outbox thay vì giữ request mở để gọi tuần tự mọi dịch vụ.
2. **Elastic:** worker có thể tăng hoặc giảm theo queue lag và năng lực xử lý.
3. **Resilient:** broker lưu message bền vững; worker lỗi có thể khởi động lại và tiếp tục, nếu consumer idempotent.
4. **Responsive:** API có thể xác nhận tiếp nhận nhanh; trạng thái job được truy vấn riêng, trong khi các endpoint đọc quan trọng có deadline rõ.

Tuy nhiên, message queue không tự động tạo ra bốn đặc tính. Nếu queue không giới hạn, nó có thể làm tăng độ trễ. Nếu consumer không idempotent, giao lại có thể gây tác dụng phụ trùng. Nếu broker là điểm lỗi đơn và không có phương án phục hồi, hệ thống vẫn dễ ngừng hoạt động.

### Ví dụ luồng xử lý đơn hàng

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Order API
    participant DB as Order DB + Outbox
    participant B as Message broker
    participant I as Inventory worker
    participant P as Payment worker
    C->>API: POST /orders
    API->>DB: Lưu order + outbox trong transaction
    DB-->>API: Commit
    API-->>C: 202 Accepted + orderId
    DB->>B: Outbox publisher gửi OrderCreated
    B->>I: Giao event
    B->>P: Giao event
    I-->>B: Ack sau xử lý
    P-->>B: Ack sau xử lý
~~~

API trả lời nhanh sau khi yêu cầu đã được ghi nhận bền vững. Inventory và payment có thể xử lý độc lập, có retry và trạng thái riêng. Nếu inventory từ chối, workflow cần ghi nhận kết quả và điều phối trạng thái đơn hàng, thay vì giả định toàn bộ các dịch vụ có chung một transaction database.

## 7. Thiết kế ranh giới chịu lỗi

Khi chia hệ thống thành nhiều dịch vụ, mỗi ranh giới mạng là một nơi có thể phát sinh timeout, lỗi kết nối hoặc kết quả không xác định. Cần thiết kế chính sách cho từng dependency.

Một ranh giới gọi dịch vụ thường cần:

- Timeout ngắn hơn deadline của request gọi.
- Circuit breaker để tránh tiếp tục gọi dependency đang hỏng.
- Bulkhead hoặc concurrency limit để cô lập tài nguyên.
- Retry chỉ cho lỗi tạm thời và thao tác an toàn khi lặp.
- Fallback nếu có dữ liệu thay thế hợp lệ.
- Metric theo dependency để xác định nơi gây chậm.
- Correlation ID hoặc trace context để theo dõi qua nhiều service.

Không nên áp dụng một cấu hình retry/timeout giống nhau cho mọi dependency. Một cache đọc có thể có fallback; một dịch vụ thanh toán không thể trả dữ liệu cũ; một lệnh ghi có thể cần idempotency và đối soát thay vì retry ngay.

### Bulkhead cho nhóm công việc

Có thể giới hạn số request tới một dependency bằng concurrency hữu hạn:

~~~java
Flux<CustomerView> views =
    customerIds.flatMap(
        id -> customerClient.findById(id)
            .map(this::toView),
        24
    );
~~~

Giới hạn 24 giúp không tạo số Publisher con không giới hạn trên nhánh này. Tuy nhiên, nếu có nhiều request HTTP đồng thời, mỗi request có thể tạo tối đa 24 inner; tổng concurrency toàn ứng dụng vẫn có thể lớn. Cần thêm giới hạn ở connection pool, rate limiter hoặc bulkhead cấp dependency.

Một scheduler riêng cũng có thể cô lập tác vụ blocking, nhưng không thay thế giới hạn tài nguyên của database hoặc dịch vụ từ xa.

## 8. Hệ thống reactive không có nghĩa mọi thứ đều non-blocking

Một ứng dụng dùng Reactor có thể vẫn bị nghẽn nếu gọi JDBC blocking trên event loop, dùng `block()` trong pipeline hoặc tạo thread không kiểm soát.

Một số nguyên tắc:

- Dùng driver reactive hoặc client non-blocking khi có thể.
- Cô lập thư viện blocking trên `Schedulers.boundedElastic()`.
- Dùng `Schedulers.parallel()` cho phép tính CPU-bound không blocking.
- Không gọi `block()` trên event loop hoặc giữa các bước reactive.
- Giới hạn concurrency của `flatMap` theo năng lực dependency.
- Đặt timeout và quản lý cancellation.
- Theo dõi queue và pool thay vì chỉ theo dõi CPU.

Ví dụ bọc một API legacy blocking:

~~~java
Mono<Customer> customer =
    Mono.fromCallable(() -> legacyCustomerDao.load(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(1));
~~~

`fromCallable` trì hoãn lời gọi tới lúc subscription; `subscribeOn` chuyển công việc blocking sang bounded elastic. Timeout giới hạn thời gian chờ của pipeline, nhưng API blocking chỉ dừng thực sự nếu driver hoặc thư viện hỗ trợ interrupt/cancellation. Không nên xem timeout là bằng chứng rằng truy vấn phía database đã dừng.

## 9. Quản lý trạng thái và tính nhất quán

Một hệ thống phân tán có nhiều thành phần cập nhật dữ liệu theo thời điểm khác nhau. Không phải mọi cập nhật đều có thể nằm trong một transaction ACID duy nhất. Cần chọn mô hình nhất quán phù hợp với nghiệp vụ.

### Strong consistency trong một ranh giới transaction

Nếu đơn hàng, projection và outbox nằm trong cùng database, có thể cập nhật chúng trong một transaction. Commit thành công làm các thay đổi cùng có hiệu lực; lỗi trước commit có thể rollback theo transaction manager.

### Eventual consistency giữa các dịch vụ

Khi inventory và payment là dịch vụ riêng, chúng cập nhật trạng thái qua message và có độ trễ. Trong khoảng thời gian đó, các view có thể tạm thời chưa đồng bộ. API cần biểu diễn trạng thái trung gian như `PENDING`, `RESERVING` hoặc `PAYMENT_AUTHORIZING`, thay vì giả vờ mọi bước đã hoàn tất.

### Saga và hành động bù trừ

Một saga mô hình hóa workflow nhiều bước và các hành động bù trừ khi một bước thất bại. Ví dụ, nếu đã giữ hàng nhưng thanh toán bị từ chối, workflow có thể phát lệnh giải phóng hàng. Đây là một hành động nghiệp vụ mới, không phải rollback database ở dịch vụ kho.

Tính nhất quán cuối cùng cần:

- Event ID và aggregate version.
- Consumer idempotent.
- Trạng thái workflow bền vững.
- Retry có giới hạn và dead-letter handling.
- Hành động bù trừ được xác định trước.
- Công cụ đối soát các trạng thái không hoàn tất.

## 10. Backpressure ở cấp thành phần và cấp hệ thống

Reactive Streams định nghĩa giao thức demand giữa Publisher và Subscriber. Subscriber yêu cầu số lượng phần tử có thể nhận; Publisher cần tôn trọng demand theo hợp đồng. Đây là cách kiểm soát luồng dữ liệu trong một pipeline.

Tuy nhiên, backpressure không tự động truyền xuyên mọi ranh giới hệ thống. Khi một Publisher đọc từ broker, adapter phải ánh xạ demand sang prefetch, pull, acknowledgement hoặc buffer của broker. Nếu nguồn ngoài không hỗ trợ điều tiết, adapter cần chính sách buffer có giới hạn, drop hoặc từ chối rõ ràng.

Ví dụ, một consumer Reactor xử lý message theo concurrency giới hạn:

~~~java
Flux<InventoryCommand> commands =
    receiver.receive();

Flux<Void> processing =
    commands.flatMap(
        message -> inventoryService.apply(message.getPayload())
            .then(message.acknowledge()),
        32
    );
~~~

Ví dụ minh họa consumer chỉ chạy tối đa 32 Publisher con đồng thời và ack sau khi xử lý hoàn tất. Mã thực tế cần xử lý lỗi, nack/requeue, duplicate delivery, cancellation và giới hạn prefetch ở broker. Nếu `apply` thất bại, không được ack như thể đã xử lý thành công.

Backpressure hữu ích khi các thành phần có thể phối hợp demand. Đối với message bền vững, broker queue cũng có thể hấp thụ tải trong một khoảng thời gian, nhưng queue cần giới hạn dung lượng và chính sách khi quá tải. Không nên biến queue thành nơi giữ công việc vô hạn.

## 11. Anti-pattern làm mất bốn đặc tính

| Anti-pattern | Hậu quả | Hướng xử lý |
|---|---|---|
| Queue không giới hạn | Độ trễ và heap tăng, hệ thống cuối cùng quá tải | Giới hạn queue, điều tiết producer, lưu bền vững hoặc từ chối |
| Retry vô hạn | Retry storm, dependency càng quá tải | Backoff, jitter, deadline và giới hạn retry |
| Chia sẻ trạng thái mutable giữa thread | Race condition và trạng thái không nhất quán | State ownership, immutable data và version |
| Một dependency dùng chung mọi thread/connection | Một nhóm lỗi làm nghẽn các nhóm khác | Bulkhead, pool và concurrency riêng |
| `block()` trên event loop | Một request chặn nhiều request khác | Non-blocking client hoặc cô lập blocking |
| Tự subscribe trong service | Mất liên kết lỗi, demand và cancellation | Trả Publisher và ghép bằng toán tử |
| Scale worker không giới hạn | Database/broker bị quá tải | Quota, autoscaling có trần và đo saturation |
| Giả định exactly-once | Message giao lại gây tác dụng phụ trùng | Idempotency, inbox/outbox và đối soát |
| Chỉ đo CPU | Bỏ sót queue lag và I/O saturation | Đo latency, queue, connection và error rate |
| Fallback dữ liệu cũ cho quyết định nhạy cảm | Quyết định nghiệp vụ sai | Xác định freshness và từ chối khi không đủ tin cậy |

## 12. Đo lường và vận hành Reactive System

Một hệ thống reactive cần quan sát được từ đầu tới cuối. Các metric nên phản ánh trải nghiệm bên ngoài và trạng thái bên trong.

### Metric về đáp ứng

- p50, p95, p99 của HTTP request.
- Tỷ lệ request vượt deadline.
- Error rate theo endpoint và dependency.
- Throughput hoàn tất, không chỉ số request được nhận.

### Metric về chịu lỗi

- Circuit breaker open/half-open/closed.
- Số lần retry và kết quả retry.
- Timeout theo dependency.
- Số request đang ở fallback.
- Tỷ lệ job hoặc saga ở trạng thái chưa hoàn tất.
- Số message trong dead-letter queue.

### Metric về co giãn

- Queue depth và consumer lag.
- Tuổi message cũ nhất.
- Worker count và utilization.
- Scheduler queue, thread count và rejection.
- Database connection pool usage.
- Tốc độ scale up/down và thời gian khởi động instance.

### Metric về hướng thông điệp

- Số message được publish, consume và ack.
- Tỷ lệ redelivery và duplicate.
- Độ trễ từ publish tới consume.
- Số message bị nack, retry hoặc chuyển DLQ.
- Tỷ lệ lỗi schema hoặc không tương thích version.

Dùng correlation ID hoặc trace context để theo dõi một yêu cầu qua nhiều dịch vụ. Không đưa ID người dùng, request ID hoặc payload biến thiên vào metric label nếu điều đó tạo cardinality không kiểm soát. Dữ liệu nhạy cảm cần được lọc trước khi ghi log.

## 13. Kiểm thử bốn đặc tính

Unit test cho reducer và toán tử là cần thiết nhưng chưa đủ. Reactive System cần được kiểm thử ở cấp tích hợp và vận hành.

| Đặc tính | Kiểm thử cần có | Điều cần xác minh |
|---|---|---|
| Responsive | Load test, latency test, deadline test | p95/p99 và tỷ lệ lỗi dưới tải mục tiêu |
| Resilient | Fault injection, dependency timeout, node restart | Phạm vi lỗi được cô lập và workflow phục hồi |
| Elastic | Tăng/giảm tải, scale worker, queue backlog | Năng lực thay đổi mà không làm queue hoặc dependency mất kiểm soát |
| Message-Driven | Duplicate, redelivery, ordering, broker outage | Consumer idempotent, message không mất ngoài hợp đồng và có thể phục hồi |

### Kiểm thử lỗi dependency

Dùng một server giả lập phản hồi chậm hoặc trả 503 để xác minh timeout, retry và fallback:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(2), Mono.just("cached"))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("cached")
    .verifyComplete();
~~~

Đây là test cấp Publisher. Kiểm thử tích hợp cần xác minh client HTTP thực sự hủy request, metric timeout được ghi và fallback không được gọi khi nguồn chính thành công.

### Kiểm thử idempotency

Gửi cùng event ID hai lần và xác minh consumer chỉ áp dụng tác dụng phụ một lần. Test cần bao gồm tình huống consumer commit xử lý nhưng mất acknowledgement, sau đó broker giao lại message.

### Kiểm thử quá tải

Tăng tốc độ producer vượt khả năng consumer và quan sát:

- Queue có bị giới hạn không?
- Producer có nhận backpressure hoặc lỗi từ chối không?
- Heap có tăng không giới hạn không?
- p95/p99 có vượt SLO không?
- Hệ thống có phục hồi sau khi tải giảm không?

### Kiểm thử phục hồi

Dừng một worker hoặc broker trong lúc xử lý, khởi động lại và xác minh message chưa ack được giao lại theo cấu hình. Xác minh consumer có thể tiếp tục từ trạng thái bền vững mà không tạo tác dụng phụ trùng.

## 14. Bài tập vận dụng

Một nền tảng đặt hàng có các thành phần: Order API, Inventory Service, Payment Service, Notification Service và Dashboard. Lượng đơn có thể tăng gấp mười lần trong một đợt khuyến mãi. Dịch vụ thanh toán đôi khi phản hồi chậm; broker có thể giao lại message sau khi consumer khởi động lại.

Hãy đề xuất thiết kế:

1. **Responsive:** API nên trả response đồng bộ hay xác nhận job bất đồng bộ? Deadline và trạng thái trung gian cần có là gì?
2. **Resilient:** timeout, circuit breaker, retry và fallback nên đặt ở những ranh giới nào? Lỗi thanh toán không xác định kết quả cần được đối soát ra sao?
3. **Elastic:** worker inventory và notification nên scale theo tín hiệu nào? Vì sao CPU đơn lẻ có thể không đủ?
4. **Message-Driven:** event contract nào được phát khi đơn hàng được tạo? Làm thế nào để tách sender khỏi consumer?
5. Làm sao bảo đảm message giao lại không giữ hàng hoặc gửi thông báo hai lần?
6. Nếu dashboard cập nhật chậm, API nên biểu diễn trạng thái nào để người dùng không hiểu nhầm?
7. Backpressure và giới hạn queue được áp dụng ở Reactor consumer và broker ra sao?
8. Những metric và fault-injection test nào cần có trước khi triển khai đợt khuyến mãi?

**Gợi ý:** ghi đơn hàng và outbox trong một transaction; trả `202 Accepted` cùng order ID nếu workflow dài. Worker tiêu thụ event với concurrency hữu hạn, partition theo order ID nếu cần thứ tự, dùng inbox/idempotency key để chống trùng. Đặt deadline cho từng dependency, retry có giới hạn và circuit breaker cho lỗi tạm thời. Theo dõi queue lag, tuổi message, connection pool và p95/p99; thử dừng worker, làm chậm payment và tăng tải producer để xác minh phục hồi.

## Kết luận

Reactive System hướng tới bốn đặc tính bổ trợ nhau: **Responsive** để phản hồi kịp thời và có thể dự đoán, **Resilient** để cô lập lỗi và phục hồi, **Elastic** để thích nghi với tải, và **Message-Driven** để các thành phần giao tiếp bất đồng bộ qua ranh giới rõ ràng. Project Reactor và Reactive Streams giúp xây dựng pipeline non-blocking, phối hợp demand và cancellation trong từng thành phần; kiến trúc hệ thống còn cần timeout, bulkhead, retry có giới hạn, queue hữu hạn, idempotency, lưu trữ bền vững và quan sát xuyên dịch vụ. Hãy thiết kế bốn đặc tính như một tập hợp mục tiêu vận hành có thể đo và kiểm thử, thay vì xem chúng là hệ quả tự động của việc dùng `Mono` hoặc `Flux`.
