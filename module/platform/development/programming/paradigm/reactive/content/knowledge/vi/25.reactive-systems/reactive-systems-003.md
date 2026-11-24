# Ranh giới bất đồng bộ giữa các thành phần và dịch vụ

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` mô tả các luồng dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Trong một ứng dụng, các toán tử có thể truyền demand và cancellation qua nhiều bước xử lý. Nhưng khi luồng đi qua ranh giới giữa các thành phần hoặc dịch vụ, chẳng hạn từ một service sang HTTP client, message broker hay một consumer ở tiến trình khác, ngữ nghĩa không còn chỉ là một pipeline trong JVM.

Ranh giới bất đồng bộ giúp các thành phần hoạt động độc lập về thời gian và khả năng mở rộng. Đổi lại, nó đưa vào hệ thống các vấn đề về giao thức, hàng đợi, xác nhận, thứ tự, lỗi mạng, trùng lặp và quan sát phân tán. Thiết kế tốt cần xác định rõ ai sở hữu dữ liệu ở mỗi thời điểm, khi nào một thao tác được xem là hoàn tất và hệ thống phản ứng thế nào khi bên nhận chậm hoặc tạm thời không hoạt động.

## 1. Ranh giới bất đồng bộ là gì?

Một ranh giới bất đồng bộ xuất hiện khi bên gửi không cần chờ bên nhận hoàn tất toàn bộ công việc trong cùng luồng gọi. Thay vì gọi trực tiếp một hàm và nhận kết quả ngay, bên gửi gửi một thông điệp, tạo một tác vụ hoặc đăng ký một Publisher để nhận kết quả sau.

Có hai dạng ranh giới thường gặp:

- **Trong cùng tiến trình:** một Publisher được chuyển qua scheduler hoặc queue nội bộ. Các thành phần vẫn chia sẻ bộ nhớ và có thể phối hợp qua Reactive Streams.
- **Qua mạng hoặc tiến trình:** dữ liệu được mã hóa thành HTTP message, broker record hoặc giao thức RPC. Hai phía có bộ nhớ, vòng đời và cơ chế lỗi riêng.

```text
Ranh giới trong tiến trình

Publisher -> operator -> queue/scheduler -> Subscriber
              request(n) và cancel có thể truyền qua chuỗi

Ranh giới giữa dịch vụ

Service A -> HTTP / broker / RPC -> Service B
     |                                |
     +---- giao thức và trạng thái ---+
           được quản lý qua mạng
```

Một `Mono` hoặc `Flux` có thể bao bọc thao tác mạng, nhưng `request(n)` không tự trở thành một thông điệp Reactive Streams gửi đến dịch vụ từ xa. Qua mạng, hai phía phải dùng semantics của giao thức hoặc thiết kế hợp đồng ứng dụng để điều tiết dữ liệu.

## 2. Chọn request-response hay message/event

Không phải mọi tương tác giữa dịch vụ đều cần cùng một kiểu bất đồng bộ.

| Kiểu tương tác | Bên gửi chờ điều gì? | Phù hợp khi | Điểm cần chú ý |
|---|---|---|---|
| HTTP request-response | Response của đúng request | Cần kết quả để tiếp tục quyết định hiện tại | Timeout, retry, connection pool và deadline |
| RPC bất đồng bộ | Kết quả của lời gọi từ xa qua Publisher | Cần API có kiểu dữ liệu và lỗi rõ ràng | Cancellation không bảo đảm hoàn tác tác vụ đã chạy |
| Fire-and-forget | Có thể chỉ chờ xác nhận đã tiếp nhận hoặc không chờ | Tác vụ phụ không cần kết quả ngay | Cần xác định nơi lưu công việc và cách quan sát lỗi |
| Message queue | Broker xác nhận nhận/lưu thông điệp | Muốn tách thời điểm gửi và xử lý | Consumer lag, retention, ack và retry |
| Event stream | Consumer đọc các sự kiện theo offset/sequence | Cần lịch sử sự kiện và nhiều consumer độc lập | Partition, ordering, replay và schema evolution |

HTTP request-response thường phù hợp khi service A cần kết quả để trả lời caller. Message/event phù hợp khi service A chỉ cần công bố một sự kiện đã xảy ra và các consumer có thể xử lý sau. Dùng message không tự động làm hệ thống nhanh hơn; nó chuyển một phần thời gian chờ sang queue và consumer.

Ví dụ, khi tạo đơn hàng:

- `ReserveInventory` là command yêu cầu một service thực hiện hành động và thường cần kết quả chấp nhận/từ chối.
- `OrderCreated` là event thông báo đơn hàng đã được tạo thành công; các consumer như email, analytics hoặc fulfillment có thể xử lý độc lập.

Command mô tả điều bên gửi muốn bên nhận làm. Event mô tả điều đã xảy ra. Không nên phát `OrderCreated` trước khi trạng thái đơn hàng thực sự được ghi nhận thành công.

## 3. Gói một lời gọi HTTP từ xa vào Mono

Với Spring WebFlux, `WebClient` trả về `Mono` hoặc `Flux`, giúp lời gọi HTTP tham gia vào pipeline mà không cần block thread xử lý:

```java
Mono<Reservation> reservation = webClient.post()
    .uri("/reservations")
    .bodyValue(command)
    .retrieve()
    .bodyToMono(Reservation.class)
    .timeout(Duration.ofSeconds(2));
```

Đoạn code mô tả một request-response bất đồng bộ. Khi subscription diễn ra, WebClient thực hiện request và phát kết quả hoặc lỗi. `timeout` đặt deadline cho Publisher ở phía ứng dụng; khi hết hạn, pipeline phát lỗi timeout và hủy subscription upstream theo cơ chế của Reactor.

Có thể kết hợp lời gọi từ xa với các bước khác:

```java
Mono<OrderView> createOrder(CreateOrder command) {
    return orderRepository.createPending(command)
        .flatMap(order -> inventoryClient.reserve(
                new ReserveCommand(order.id(), order.items())
            )
            .timeout(Duration.ofSeconds(2))
            .flatMap(reservation ->
                orderRepository.confirm(order.id(), reservation.id())
                    .thenReturn(OrderView.confirmed(order, reservation))
            )
        );
}
```

Các phương thức repository và client trong ví dụ được giả định trả Publisher reactive. Nếu bên trong chúng gọi JDBC hoặc HTTP client blocking, việc bọc kết quả trong `Mono` không tự biến thao tác blocking thành non-blocking; cần dùng driver reactive hoặc cô lập lời gọi blocking trên scheduler phù hợp.

## 4. Timeout ở ranh giới từ xa có ý nghĩa gì?

Timeout cho biết caller không nhận được kết quả trong thời hạn đã đặt. Nó không chứng minh service từ xa chưa thực hiện thao tác.

Ví dụ, service B có thể đã ghi reservation thành công nhưng response bị mất trên mạng. Service A hết timeout và không biết thao tác đã commit hay chưa. Nếu A gửi lại command, B có thể tạo reservation thứ hai nếu API không có cơ chế idempotency.

Với request có tác dụng phụ, nên dùng một khóa idempotency ổn định:

```java
Mono<Reservation> reserve(ReserveCommand command) {
    return webClient.post()
        .uri("/reservations")
        .header("Idempotency-Key", command.commandId().toString())
        .bodyValue(command)
        .retrieve()
        .bodyToMono(Reservation.class)
        .timeout(Duration.ofSeconds(2));
}
```

Service nhận request cần lưu khóa cùng kết quả hoặc trạng thái xử lý để một lần gửi lại không tạo tác dụng phụ lần thứ hai. Khóa phải đại diện cho cùng một ý định nghiệp vụ; không tạo UUID mới mỗi lần retry vì như vậy mỗi lần gửi sẽ trở thành một command khác.

## 5. Cancellation không đồng nghĩa với rollback từ xa

Trong một pipeline nội bộ, `cancel()` yêu cầu upstream dừng phát và giải phóng công việc nếu có thể. Qua HTTP hoặc message broker, cancellation chỉ có thể được ánh xạ sang việc đóng response, hủy request hoặc dừng tiêu thụ. Nó không tự hoàn tác một giao dịch đã commit ở dịch vụ khác.

Hãy phân biệt:

- **Dừng chờ:** caller không còn chờ response.
- **Dừng truyền:** client đóng hoặc ngừng đọc kết nối/stream.
- **Dừng xử lý:** service nhận biết yêu cầu hủy và có thể dừng công việc chưa hoàn tất.
- **Hoàn tác nghiệp vụ:** service thực hiện một hành động bù hoặc rollback giao dịch theo quy tắc riêng.

Các bước này không đồng nghĩa. Một thao tác đã commit không thể được hoàn tác chỉ bằng cách cancel subscription ở caller. Với quy trình nhiều dịch vụ, cần mô hình trạng thái và hành động bù nếu nghiệp vụ yêu cầu hoàn tác.

## 6. Message broker tạo ranh giới lưu trữ và thời gian

Message broker cho phép producer gửi record mà consumer có thể đọc sau. Broker có thể lưu thông điệp bền vững, phân phối đến nhiều consumer group và giữ lại dữ liệu để replay tùy cấu hình.

```text
Service A
   |
   | publish OrderCreated
   v
Message broker / topic
   |
   +------> Consumer email
   |
   +------> Consumer analytics
   |
   +------> Consumer fulfillment
```

Producer và consumer không cần hoạt động cùng lúc. Nhưng dữ liệu phải nằm ở đâu đó trong khoảng chờ: broker log, queue, buffer của producer hoặc một kho lưu trữ khác. Nếu consumer chậm trong thời gian dài, consumer lag tăng và dữ liệu có thể tiến gần giới hạn retention hoặc dung lượng broker.

Một xác nhận publish thường chỉ cho biết broker đã nhận hoặc lưu record theo mức đảm bảo cấu hình. Nó không có nghĩa mọi consumer đã xử lý xong event. Nếu nghiệp vụ cần biết consumer hoàn thành, cần một response/acknowledgement riêng, trạng thái workflow hoặc event kết quả.

## 7. Thiết kế envelope cho thông điệp

Thông điệp qua ranh giới dịch vụ nên mang đủ metadata để định danh, sắp thứ tự, truy vết và tiến hóa schema. Một envelope có thể gồm:

```java
record EventEnvelope<T>(
    UUID eventId,
    String eventType,
    int schemaVersion,
    String aggregateId,
    long sequence,
    Instant occurredAt,
    String correlationId,
    String causationId,
    T payload
) {}
```

Các trường có ý nghĩa:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất để phát hiện thông điệp trùng |
| `eventType` | Xác định loại sự kiện |
| `schemaVersion` | Chọn schema/decoder tương thích |
| `aggregateId` | Nhóm sự kiện thuộc cùng một thực thể nghiệp vụ |
| `sequence` | Phát hiện thiếu, trùng hoặc sai thứ tự trong phạm vi aggregate |
| `occurredAt` | Thời điểm sự kiện xảy ra theo nguồn nghiệp vụ |
| `correlationId` | Liên kết nhiều thao tác thuộc cùng một quy trình |
| `causationId` | Chỉ ra command/event đã gây ra sự kiện này |
| `payload` | Dữ liệu nghiệp vụ của event |

Không nên dùng timestamp làm thứ tự tuyệt đối giữa nhiều producer vì đồng hồ có thể lệch và nhiều event có thể cùng timestamp. Sequence do nguồn sở hữu trong một aggregate hoặc partition thường đáng tin cậy hơn cho thứ tự cục bộ.

## 8. Đảm bảo giao nhận và xử lý trùng lặp

Hệ thống phân tán thường phải lựa chọn giữa các semantics giao nhận:

| Semantics | Đặc điểm | Đánh đổi |
|---|---|---|
| At-most-once | Thông điệp có thể mất nhưng không được gửi lại theo chính sách đó | Phù hợp dữ liệu có thể mất; không phù hợp sự kiện nghiệp vụ quan trọng |
| At-least-once | Thông điệp được gửi lại cho đến khi được xác nhận theo cấu hình | Có thể xử lý trùng; consumer cần idempotency |
| Exactly-once trong phạm vi hẹp | Một số broker/transaction có thể bảo đảm xử lý một lần trong phạm vi được hỗ trợ | Không tự tạo exactly-once cho mọi side effect qua nhiều dịch vụ và database |

Với at-least-once, consumer có thể nhận cùng event nhiều lần, ví dụ khi đã ghi dữ liệu nhưng chưa commit offset hoặc ack bị mất. Consumer nên dùng `eventId` để deduplicate hoặc thiết kế thao tác idempotent.

Một mẫu phổ biến là ghi inbox/deduplication record và cập nhật dữ liệu nghiệp vụ trong cùng transaction database:

```text
BEGIN TRANSACTION
  INSERT inbox(event_id) nếu chưa tồn tại
  nếu event_id mới:
      cập nhật trạng thái nghiệp vụ
COMMIT
ACK message
```

Nếu event đã được xử lý, consumer bỏ qua tác dụng phụ và vẫn xác nhận message theo chính sách. Việc ghi inbox và thay đổi nghiệp vụ phải có ranh giới transaction nhất quán; nếu hai bước nằm ở hai kho không có transaction chung, cần một thiết kế phối hợp khác.

## 9. Tránh dual-write bằng Transactional Outbox

Một lỗi thường gặp là cập nhật database rồi publish event trong hai thao tác riêng:

1. Database commit thành công.
2. Ứng dụng gặp sự cố trước khi publish event.

Khi đó trạng thái đã thay đổi nhưng consumer không nhận được event. Đảo thứ tự cũng có thể tạo event cho thay đổi database chưa commit.

Transactional Outbox giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng một transaction:

```text
BEGIN DATABASE TRANSACTION
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO outbox(event_id, event_type, payload, created_at)
COMMIT

Outbox relay đọc bản ghi chưa gửi
   -> publish lên broker
   -> đánh dấu đã gửi / lưu checkpoint
```

Relay có thể publish lại nếu bị lỗi sau khi broker nhận record nhưng trước khi đánh dấu outbox đã gửi. Vì vậy consumer vẫn cần idempotency. Outbox bảo đảm trạng thái nghiệp vụ và ý định phát event được lưu nguyên tử trong database; nó không tự bảo đảm consumer chỉ nhận đúng một lần.

## 10. Thứ tự sự kiện và partition

Broker thường chỉ bảo đảm thứ tự trong một phạm vi cụ thể, chẳng hạn một partition hoặc một queue. Nếu các event của cùng một aggregate cần xử lý theo thứ tự, hãy định tuyến chúng bằng cùng một key, thường là `aggregateId`.

```text
Topic: orders

Partition 0: order-A seq 1 -> seq 2 -> seq 3
Partition 1: order-B seq 1 -> seq 2
Partition 2: order-C seq 1 -> seq 2
```

Consumer có thể xử lý các partition song song, nhưng cần giữ thứ tự trong một partition nếu nghiệp vụ yêu cầu. Nếu consumer tự đưa từng record vào `flatMap` không giới hạn, nó có thể hoàn tất tác vụ sai thứ tự dù broker đã giao record theo thứ tự.

Ví dụ giữ thứ tự xử lý trong một partition bằng Reactor:

```java
Flux<Void> processing = records
    .concatMap(record -> handle(record));
```

Nếu muốn song song giữa các key, có thể phân nhóm theo partition hoặc aggregate và xử lý từng nhóm tuần tự. Không nên dùng `concatMap` cho toàn bộ topic nếu điều đó làm giảm throughput không cần thiết; hãy xác định đúng phạm vi cần thứ tự.

Sequence number ở payload giúp consumer phát hiện khoảng trống hoặc sự kiện đến trùng. Nếu nhận sequence 12 trong khi trạng thái hiện tại là 10, consumer có thể chờ sequence 11, yêu cầu replay hoặc đưa event vào vùng xử lý ngoại lệ thay vì áp dụng sai thứ tự.

## 11. Backpressure qua broker cần cơ chế riêng

`request(n)` của Reactive Streams không được tự động truyền qua giao thức broker đến producer từ xa. Consumer broker thường điều tiết lượng dữ liệu đọc bằng fetch size, prefetch, số record outstanding, cơ chế pause/resume partition hoặc thời điểm commit/ack.

Khi consumer chậm, có thể áp dụng:

- Giảm số record được fetch hoặc prefetch.
- Giới hạn concurrency xử lý record trong ứng dụng.
- Pause partition khi queue nội bộ đạt ngưỡng và resume khi backlog giảm.
- Giới hạn số message đang xử lý nhưng chưa ack/commit.
- Dùng queue nội bộ hữu hạn và xác định hành vi khi đầy.
- Scale consumer nếu còn partition và dependency phía sau đủ năng lực.
- Từ chối hoặc chuyển sang dead-letter khi event không thể xử lý sau chính sách retry.

Không nên đọc toàn bộ backlog từ broker vào một queue không giới hạn trong JVM. Điều đó chỉ chuyển backlog từ broker sang heap ứng dụng, làm mất lợi ích của cơ chế lưu trữ bền vững và có thể gây OutOfMemoryError.

## 12. Lỗi, retry và Dead Letter Queue

Consumer có thể gặp lỗi tạm thời như timeout database hoặc lỗi kết nối. Một số lỗi khác là không thể phục hồi bằng retry, chẳng hạn payload sai schema hoặc dữ liệu vi phạm quy tắc nghiệp vụ.

Một chính sách xử lý nên phân biệt:

1. **Retry có giới hạn:** dùng cho lỗi tạm thời, có backoff và jitter.
2. **Không retry:** với lỗi đầu vào hoặc lỗi nghiệp vụ không thể tự hết.
3. **Dead Letter Queue (DLQ):** chuyển message không xử lý được sang nơi lưu riêng để điều tra hoặc xử lý thủ công.
4. **Quarantine:** cô lập loại message hoặc producer gây lỗi hàng loạt.
5. **Alert:** cảnh báo khi số lần retry, consumer lag hoặc DLQ tăng bất thường.

Retry vô hạn một message lỗi có thể chặn partition và làm các message hợp lệ phía sau không được xử lý nếu thứ tự partition phải giữ. Retry cần giới hạn thời gian và số lần; sau đó phải có quyết định rõ ràng về DLQ, skip có kiểm soát hoặc dừng consumer.

Trong pipeline Reactor, `retryWhen` có thể xử lý lỗi của Publisher xử lý message. Nhưng quyết định ack/commit phải phối hợp với connector broker. Không ack message trước khi side effect nghiệp vụ được lưu bền vững nếu semantics yêu cầu at-least-once.

## 13. Truyền correlation và trace qua ranh giới dịch vụ

Log trong từng service không đủ để tái dựng một quy trình bất đồng bộ kéo dài qua nhiều tiến trình. Mỗi request/event nên mang correlation ID và trace context phù hợp.

- HTTP có thể truyền trace context qua header chuẩn như `traceparent` và baggage theo chính sách observability.
- Message broker có thể lưu trace context trong header của record.
- `correlationId` liên kết các bước nghiệp vụ, kể cả khi trace kỹ thuật đã kết thúc hoặc được tạo mới ở consumer.
- `eventId` định danh một message cụ thể để deduplicate và tìm kiếm.
- `causationId` giúp truy ngược command hoặc event đã tạo ra message hiện tại.

Reactor Context có thể giữ metadata theo subscription trong một pipeline, nhưng Context không tự truyền qua mạng. Khi publish HTTP hoặc broker message, ứng dụng cần trích xuất context và đưa vào header/envelope; phía nhận cần khôi phục context khi bắt đầu pipeline mới.

Không đưa dữ liệu nhạy cảm như token, thông tin xác thực hoặc payload riêng tư vào correlation header. Chỉ truyền các định danh và baggage đã được cho phép.

## 14. Schema evolution ở ranh giới dịch vụ

Producer và consumer có thể được triển khai ở các thời điểm khác nhau. Consumer cũ có thể đọc event mới, hoặc producer mới có thể gửi event cho consumer chưa được nâng cấp. Vì vậy, schema message là hợp đồng dài hạn hơn một kiểu Java nội bộ.

Một số nguyên tắc:

- Thêm field tùy chọn có default thường dễ tương thích ngược hơn đổi tên hoặc xóa field.
- Không đổi ý nghĩa của field mà giữ nguyên schema version.
- Consumer nên bỏ qua field chưa biết nếu format và serializer cho phép.
- Khi thay đổi không tương thích, tạo event type/version mới hoặc có giai đoạn chuyển đổi.
- Kiểm thử contract giữa producer và consumer bằng payload đã version hóa.
- Xác định thời gian giữ schema cũ theo retention và khả năng replay của broker.

Không nên chỉ dùng tên class Java làm hợp đồng message. Package hoặc cấu trúc nội bộ có thể thay đổi độc lập với contract được lưu lâu dài trong broker.

## 15. Kiểm thử ranh giới bất đồng bộ

Kiểm thử cần bao phủ cả Publisher nội bộ và giao thức giữa dịch vụ.

### Kiểm thử pipeline HTTP

Với WebClient, dùng server giả lập để kiểm tra request, response, timeout và lỗi. Dùng `StepVerifier` xác minh tín hiệu của `Mono`/`Flux`; không chỉ kiểm tra object trả về bằng cách block.

### Kiểm thử message contract

- Xác minh event có `eventId`, type, version, aggregate key và payload hợp lệ.
- Đảm bảo consumer có thể đọc payload được producer phát.
- Kiểm tra consumer xử lý cùng event hai lần mà không tạo side effect trùng.
- Kiểm tra sequence thiếu, sequence lặp và event đến sai thứ tự.

### Kiểm thử lỗi và tải

- Broker tạm thời không khả dụng khi publish.
- Consumer chết sau khi ghi database nhưng trước khi ack.
- Producer publish thành công nhưng relay chưa đánh dấu outbox.
- Consumer chậm làm lag tăng và queue nội bộ chạm giới hạn.
- Poison message được chuyển vào DLQ sau retry hữu hạn.
- Cancellation hoặc shutdown xảy ra khi đang xử lý message.

### Kiểm thử tính bền vững

Kiểm tra outbox record còn lại sau khi process restart, relay có thể tiếp tục publish và consumer deduplicate được event đã phát lại. Các test này thường cần database/broker test container hoặc môi trường tích hợp; mock một Publisher không thể chứng minh semantics lưu bền vững của broker.

## 16. Chọn ranh giới theo yêu cầu nghiệp vụ

| Yêu cầu | Ranh giới phù hợp | Điều phải thiết kế |
|---|---|---|
| Cần kết quả ngay để quyết định bước tiếp theo | HTTP/RPC request-response | Deadline, timeout, retry an toàn và fallback |
| Thông báo một sự kiện cho nhiều consumer | Event broker/topic | Event schema, retention, idempotency và consumer lag |
| Tác vụ dài có thể chạy sau khi caller rời đi | Queue/command processing | Trạng thái tác vụ, ack, retry và cách truy vấn kết quả |
| Cần lịch sử để replay | Event log/stream | Offset, partition, schema evolution và retention |
| Nhiều bước qua nhiều dịch vụ cần bù trừ | Saga hoặc workflow | State machine, correlation, timeout và compensating action |
| Consumer có tốc độ thấp hơn producer | Broker với pull/pause và queue hữu hạn | Prefetch, concurrency, retention và overload policy |

Không nên chuyển mọi lời gọi nội bộ thành message chỉ vì muốn “asynchronous”. Nếu caller cần response ngay, request-response reactive có thể đơn giản và dễ quan sát hơn. Ngược lại, không nên giữ một HTTP request mở cho công việc kéo dài mà caller không cần chờ; một command được lưu bền vững cùng trạng thái tác vụ có thể phù hợp hơn.

## 17. Checklist thiết kế ranh giới bất đồng bộ

Trước khi triển khai, hãy xác định:

1. Đây là command, query hay event? Bên gửi cần kết quả nghiệp vụ hay chỉ cần xác nhận đã tiếp nhận?
2. Ranh giới nằm trong JVM hay qua mạng/tiến trình?
3. Dữ liệu được lưu ở đâu trong lúc consumer chậm hoặc offline?
4. Delivery semantics là gì; duplicate có thể xảy ra ở những điểm nào?
5. Event/command có ID ổn định, correlation, causation và version không?
6. Thứ tự cần giữ ở phạm vi nào: toàn hệ thống, aggregate hay partition?
7. Backpressure hoặc flow control được thực hiện bằng demand, fetch/prefetch, pause/resume hay rate limit?
8. Queue và retention có giới hạn; khi đầy hoặc quá tuổi thì làm gì?
9. Timeout, retry, DLQ và idempotency có phối hợp với nhau không?
10. Cancellation chỉ dừng chờ hay cần hành động bù cho side effect đã commit?
11. Trace context có được truyền qua HTTP/message header và khôi phục ở consumer không?
12. Có contract test, duplicate test, replay test và overload test không?

Ranh giới bất đồng bộ giúp các thành phần và dịch vụ độc lập về thời gian, nhưng cũng tạo ra một hợp đồng phân tán gồm dữ liệu, giao nhận, thứ tự, lỗi và trạng thái. Reactive Streams quản lý demand trong một pipeline; HTTP và broker có flow control, acknowledgement và buffering riêng. Khi chọn đúng kiểu tương tác, giới hạn queue, thiết kế idempotency, quản lý schema và truyền trace context, hệ thống có thể tiếp tục hoạt động khi một thành phần chậm hoặc tạm thời mất kết nối mà vẫn giữ được tính đúng đắn của nghiệp vụ.
