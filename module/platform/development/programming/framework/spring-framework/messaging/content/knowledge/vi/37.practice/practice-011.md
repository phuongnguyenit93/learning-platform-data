# Đo tải, ngắt kết nối và giải thích giới hạn bảo đảm của từng mô hình

## 1. Mục tiêu của bài thực hành

Một hệ thống messaging có thể xử lý hàng chục nghìn message mỗi giây trong bài benchmark ngắn nhưng vẫn mất message khi broker restart, client disconnect hoặc consumer xử lý chậm. Ngược lại, một hệ thống có bảo đảm lưu trữ tốt có thể có latency cao hơn vì phải ghi đĩa, xác nhận publisher hoặc commit transaction.

Vì vậy, kiểm thử messaging phải trả lời đồng thời bốn câu hỏi:

1. **Tốc độ:** hệ thống nhận được bao nhiêu message mỗi giây và hoàn thành xử lý bao nhiêu message mỗi giây?
2. **Độ trễ:** message đi từ lúc được tạo đến lúc được xử lý mất bao lâu ở p50, p95 và p99?
3. **Khả năng chịu lỗi:** điều gì xảy ra khi client, application instance, network hoặc broker bị ngắt giữa chừng?
4. **Bảo đảm delivery:** sau mỗi điểm lỗi, message có thể mất, được gửi lại, bị trùng hay được khôi phục?

Không có một con số throughput hoặc một kiểu kết nối nào tự chứng minh được message đã được xử lý đúng nghiệp vụ. Phải xác định rõ hệ thống đang đo đến mốc nào: API chấp nhận lệnh, transport gửi xong, broker xác nhận, consumer nhận, hay transaction nghiệp vụ đã commit.

Bài này so sánh các mô hình thường gặp trong Spring messaging:

- Spring in-process channels: `DirectChannel`, `ExecutorChannel`, `QueueChannel`.
- WebSocket/STOMP với simple broker và external broker relay.
- RSocket: Request-Response, Fire-and-Forget, Request-Stream và Channel.
- Messaging dựa trên broker như JMS và AMQP/RabbitMQ.

## 2. Chuẩn hóa thuật ngữ về delivery guarantee

Trước khi đo, cần thống nhất ý nghĩa của các trạng thái:

| Thuật ngữ | Ý nghĩa thực tế |
|---|---|
| Accepted | API hoặc queue cục bộ đã nhận lệnh gửi; chưa chắc receiver đã thấy message |
| Written | Byte/frame đã được ghi vào transport hoặc socket buffer; chưa chứng minh peer đã xử lý |
| Broker-confirmed | Broker đã xác nhận theo cơ chế và cấu hình của broker |
| Delivered | Consumer/client đã nhận message |
| Processed | Handler đã chạy xong |
| Committed | Thay đổi nghiệp vụ và trạng thái xử lý đã được commit bền vững |
| Acknowledged | Consumer đã gửi ACK hoặc commit transaction để broker/provider được phép xóa message |

Ba khái niệm delivery thường được nhắc tới:

- **At-most-once:** một message không được giao lại; có thể mất nếu lỗi xảy ra ở thời điểm không thuận lợi.
- **At-least-once:** hệ thống tiếp tục thử giao cho tới khi có xác nhận theo cơ chế đã chọn; có thể giao trùng.
- **Effectively-once:** hệ thống cho phép retry và duplicate nhưng dùng idempotency/inbox/unique key để kết quả nghiệp vụ chỉ được áp dụng một lần.
- **Exactly-once:** chỉ nên dùng khi mô tả một phạm vi giao thức hoặc transaction cụ thể. Không suy rộng thành bảo đảm end-to-end qua client, network, broker, database và side effect bên ngoài.

Ví dụ: producer gửi lệnh chuyển tiền, broker nhận lệnh, consumer cập nhật database rồi process chết trước khi ACK. Broker có thể gửi lại message. Nếu consumer không có idempotency key, tài khoản có thể bị trừ tiền hai lần. ACK bảo vệ trạng thái delivery của broker; nó không tự tạo transaction nguyên tử giữa broker và database nghiệp vụ.

### 2.1. Đo tới mốc nào?

Một message có thể đi qua chuỗi:

```text
Producer tạo message
      |
      v
API send() / request()
      |
      v
Local channel hoặc network transport
      |
      v
Broker nhận và định tuyến
      |
      v
Consumer nhận
      |
      v
Handler xử lý
      |
      v
Database commit
      |
      v
ACK / reply / client nhận kết quả
```

Mỗi mốc có một ý nghĩa khác nhau. Ví dụ:

- `QueueChannel.send()` trả về `true` chỉ cho biết message đã được đưa vào queue trong bộ nhớ.
- `ExecutorChannel.send()` có thể trả về trước khi handler chạy xong.
- STOMP `SEND` được broker nhận không có nghĩa subscriber đã xử lý message.
- RSocket Fire-and-Forget không có response payload để xác nhận nghiệp vụ.
- RabbitMQ publisher confirm không có nghĩa consumer đã commit database.
- Consumer ACK không có nghĩa một side effect bên ngoài transaction đã hoàn thành, trừ khi ứng dụng phối hợp đúng transaction hoặc outbox/inbox.

Trong báo cáo test, hãy ghi rõ tên mốc đo, không đặt chung một tên là “message delivered”.

## 3. Thiết kế bài load test có thể lặp lại

### 3.1. Xác định workload trước khi chạy

Một workload cần ít nhất các thông số sau:

| Tham số | Ví dụ |
|---|---|
| Số client/connection đồng thời | 100, 500, 2.000 |
| Tốc độ gửi mỗi client | 1, 5 hoặc 20 message/giây |
| Tổng offered rate | Số client × tốc độ gửi |
| Kích thước payload | 256 B, 4 KB, 32 KB |
| Fan-out | 1, 10 hoặc 100 subscriber cho mỗi publish |
| Thời gian chạy | 5 phút, 30 phút, 2 giờ |
| Tỷ lệ request có reply | 0%, 50%, 100% |
| Tỷ lệ client chậm | 0%, 1%, 10% |
| Tỷ lệ lỗi giả lập | disconnect, timeout, broker restart |
| Kiểu xác nhận | không ACK, ACK sau handler, ACK sau commit |

Đừng chỉ tăng số connection. Một WebSocket có thể rất nhàn rỗi hoặc có thể gửi liên tục hàng trăm message/giây. Hai workload đó tạo tải CPU, memory, broker và outbound channel rất khác nhau.

### 3.2. Các giai đoạn chạy

Một lượt benchmark nên có các giai đoạn tách biệt:

1. **Warm-up:** mở connection, tạo subscription, làm nóng JIT, connection pool và cache.
2. **Ramp-up:** tăng số client từ từ để tìm điểm hệ thống bắt đầu tăng latency hoặc queue.
3. **Steady state:** giữ offered rate ổn định đủ lâu để thấy backlog và GC.
4. **Burst:** tăng tốc độ gửi trong thời gian ngắn để kiểm tra khả năng hấp thụ đỉnh tải.
5. **Soak:** chạy dài để tìm memory leak, queue tăng dần, connection không được giải phóng hoặc scheduler bị nghẽn.
6. **Failure injection:** chủ động ngắt client, node hoặc broker trong khi tải đang chạy.
7. **Recovery:** đo thời gian reconnect, resubscribe, backlog drain và thời điểm hệ thống trở lại trạng thái bình thường.

Không gộp tất cả vào một bài test duy nhất. Khi thay một tham số, giữ các yếu tố khác cố định để biết nguyên nhân của thay đổi.

### 3.3. Open-loop và closed-loop

**Closed-loop test** gửi request tiếp theo sau khi request trước hoàn tất. Cách này dễ triển khai, nhưng khi server chậm, chính tốc độ phát sinh request của client cũng giảm. Nó có thể che giấu việc hệ thống không theo kịp offered load.

**Open-loop test** duy trì tốc độ phát sinh message độc lập với tốc độ phản hồi. Cách này cho thấy rõ queue có tăng liên tục khi arrival rate cao hơn service rate hay không. Phải có giới hạn bộ đệm ở load generator để tránh nhầm queue của công cụ test với queue của server.

Nên chạy cả hai:

- Closed-loop để mô phỏng người dùng chờ phản hồi rồi thao tác tiếp.
- Open-loop để đo khả năng chịu tải theo tốc độ sự kiện đầu vào cố định.

Nếu tốc độ đến là \(\lambda\) message/giây và tốc độ xử lý là \(\mu\) message/giây, khi \(\lambda > \mu\) trong thời gian dài, backlog sẽ tăng. Tăng thread pool có thể cải thiện throughput trong một số trường hợp nhưng không giải quyết được bottleneck database, broker hoặc network.

### 3.4. Không chỉ báo cáo average latency

Báo cáo tối thiểu nên có:

- Offered messages/sec.
- Accepted messages/sec.
- Completed/committed messages/sec.
- p50, p95, p99 latency.
- Error rate và timeout rate.
- Duplicate count và missing sequence count.
- Active connections và connection churn.
- Queue depth và tuổi message cũ nhất.
- CPU, heap, GC pause, direct memory và network throughput.

Average có thể đẹp trong khi một nhóm nhỏ client bị treo hàng chục giây. p95/p99 giúp nhìn thấy phần đuôi latency. Khi dùng histogram, bảo đảm bucket đủ chi tiết quanh SLO cần đo và các instance dùng cùng cấu hình bucket.

### 3.5. Dùng ID và sequence để phát hiện mất/trùng

Mỗi message test nên có:

- `runId`: định danh một lần chạy.
- `messageId`: UUID hoặc ID duy nhất.
- `producerId`: định danh producer.
- `sequence`: số tăng dần trong phạm vi producer.
- `createdAt`: thời điểm tạo message.
- `payloadSize`: kích thước dữ liệu.

Receiver lưu hoặc tổng hợp các ID đã thấy. Sau test, so sánh tập ID đã gửi với tập ID đã xử lý:

- Missing: đã gửi nhưng không thấy xử lý.
- Duplicate: một `messageId` được xử lý nhiều lần.
- Out-of-order: sequence đến sai thứ tự so với yêu cầu nghiệp vụ.
- Late: message xử lý sau deadline.

Không chỉ đếm số message gửi và nhận. Nếu một message bị mất và một message khác bị duplicate, tổng số có thể bằng nhau nhưng kết quả vẫn sai.

Khi đo latency giữa hai máy, cần đồng bộ clock (ví dụ NTP) và tính tới sai số clock. `System.nanoTime()` phù hợp để đo khoảng thời gian bên trong cùng process; không so sánh trực tiếp giá trị nanoTime giữa hai máy khác nhau. Nếu không kiểm soát clock tốt, đo thời gian xử lý nội bộ ở từng node và trace từng chặng thay vì trừ hai wall-clock timestamp chưa đồng bộ.

## 4. Đo và giải thích giới hạn của Spring in-process channels

Spring Integration cung cấp các channel với hành vi đồng bộ, bất đồng bộ hoặc lưu đệm khác nhau. Việc `send()` trả về thành công có ý nghĩa khác nhau theo loại channel.

### 4.1. DirectChannel

`DirectChannel` chuyển message trực tiếp tới một subscriber trong thread gọi `send()`. Handler được gọi trước khi `send()` trả về.

Đặc điểm:

- Không tạo queue trung gian.
- Độ trễ thấp, ít overhead.
- Exception từ handler có thể quay lại phía gửi.
- Transaction context của thread có thể đi xuyên qua lời gọi đồng bộ.
- Không lưu message bền vững nếu process dừng.
- Nếu handler làm việc chậm hoặc block, producer cũng bị chậm theo.

Ví dụ:

```java
@Bean
MessageChannel directOrders() {
    return new DirectChannel();
}
```

Khi benchmark, đo cả thời gian `send()` và thời gian handler. Với DirectChannel, hai khoảng thời gian thường chồng lên nhau vì handler chạy trong thread của sender. Đừng tạo hàng nghìn thread chỉ để ép DirectChannel tăng throughput; hãy xác định handler đang CPU-bound hay I/O-bound.

### 4.2. ExecutorChannel

`ExecutorChannel` dispatch handler qua `TaskExecutor`. Sender có thể nhận kết quả send trước khi handler hoàn tất.

```java
@Bean
MessageChannel asyncOrders(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
```

Đặc điểm:

- Sender và handler chạy ở các thread khác nhau.
- `send()` thành công không có nghĩa handler đã hoàn tất.
- Exception của handler xảy ra sau đó không thể quay lại lời gọi `send()` đã kết thúc.
- Transaction context của thread gửi không tự động được chia sẻ với handler.
- Khi executor bão hòa hoặc từ chối task, cần có chính sách xử lý rejection.
- Task queue của executor có thể trở thành backlog và tiêu thụ memory.

Trong load test, đo riêng số task được submit, số handler bắt đầu, số handler hoàn tất và số task bị reject. Nếu chỉ đo `send()` duration, ExecutorChannel có thể trông rất nhanh dù queue executor đang tăng không giới hạn.

### 4.3. QueueChannel

`QueueChannel` lưu message trong queue để consumer nhận sau. Mặc định queue nằm trong bộ nhớ và có thể không giới hạn capacity nếu không cấu hình.

```java
@Bean
PollableChannel orderQueue() {
    return new QueueChannel(1_000);
}
```

Với queue có capacity:

- Nếu còn chỗ, `send()` đưa message vào queue và trả về.
- Khi queue đầy, sender có thể block chờ chỗ trống hoặc hết timeout.
- Consumer gọi `receive()` để lấy message.
- Nhiều consumer nhận từ cùng queue theo point-to-point semantics: mỗi message được một consumer lấy ra.
- Queue mặc định không bền vững qua process crash.

Có thể cấu hình `QueueChannel` dùng persistent `MessageGroupStore`, nhưng phải kiểm tra implementation, transaction và cách message được xóa khỏi store. Chỉ thêm persistent store không tự bảo đảm end-to-end exactly-once.

Khi test, đo:

- Queue depth theo thời gian.
- Thời gian chờ trong queue.
- Số lần send bị block/timeout.
- Số message còn tồn khi process shutdown.
- Tỷ lệ consumer xử lý xong so với producer gửi vào.

### 4.4. PublishSubscribeChannel

`PublishSubscribeChannel` gửi một message tới nhiều subscriber. Nếu dispatch qua executor, sender có thể không chờ từng subscriber xử lý xong.

Khi benchmark fan-out, chi phí phụ thuộc số subscriber, tốc độ từng subscriber và cách xử lý subscriber chậm. Một subscriber chậm có thể làm queue hoặc executor của nó tăng, trong khi các subscriber khác vẫn xử lý bình thường.

### 4.5. Bảo đảm của in-process channel

| Channel | `send()` thành công chứng minh điều gì? | Giới hạn khi crash |
|---|---|---|
| DirectChannel | Handler đồng bộ đã được gọi và hoàn tất theo đường gọi hiện tại nếu không ném lỗi | Không có message store bền vững |
| ExecutorChannel | Task đã được dispatch/accept theo executor | Task đang chờ hoặc đang chạy có thể mất khi process dừng |
| QueueChannel mặc định | Message đã vào queue memory | Queue mất khi process dừng |
| QueueChannel có persistent store | Message được ghi theo semantics của store đã cấu hình | Cần xác minh transaction, recovery và duplicate behavior |
| PublishSubscribeChannel | Các subscriber được dispatch theo cấu hình | Không có persistence mặc định; từng subscriber có thể hoàn tất ở thời điểm khác nhau |

Dùng in-process channel khi các thành phần cùng một process và chấp nhận phạm vi lỗi của process đó. Khi cần lưu bền vững, phân phối qua nhiều instance hoặc phục hồi sau process crash, phải chọn cơ chế persistence/broker phù hợp.

## 5. Đo WebSocket/STOMP: simple broker và external broker relay

### 5.1. Simple broker

Spring simple broker lưu subscription trong memory và broadcast message tới các client đang subscribe destination khớp. Đây là lựa chọn đơn giản cho phát triển, demo hoặc ứng dụng nhỏ.

Giới hạn quan trọng:

- Không có persistence queue như message broker chuyên dụng.
- Không hỗ trợ STOMP ACK, receipt và một số command nâng cao.
- Subscription chỉ tồn tại trong bộ nhớ của application instance.
- Không phù hợp cho clustering nhiều Spring instance.
- Client disconnect làm mất subscription của session đó.
- Message phát lúc client offline không tự được lưu để gửi lại sau reconnect.

Khi test simple broker, hãy đo active session, inbound/outbound channel queue, fan-out, send buffer và số client chậm. Đừng kết luận nó có delivery guarantee bền vững chỉ vì mọi client nhận được message trong một bài test không có lỗi.

### 5.2. External STOMP broker relay

Với broker relay, Spring chuyển STOMP frame qua TCP tới external broker như RabbitMQ hoặc ActiveMQ. Broker quản lý destination/subscription theo khả năng và cấu hình của chính broker.

Ưu điểm:

- Có thể scale nhiều Spring instance cùng kết nối tới broker.
- Có thể dùng queue bền vững, ACK, receipt hoặc durable subscription nếu broker hỗ trợ.
- Broker có thể giữ message khi consumer tạm thời offline, tùy loại destination.
- Spring vẫn quản lý WebSocket session và application handler.

Giới hạn:

- Broker relay không tự biến mọi `/topic` thành durable queue.
- Semantics ACK, queue durability, persistence, expiry, redelivery và dead-letter phụ thuộc broker.
- Mỗi WebSocket client được relay có thể tạo một TCP connection riêng tới broker, ngoài system connection của mỗi Spring instance.
- Broker restart có thể làm mất client-side broker connections; client cần reconnect/resubscribe.
- Message được broker xác nhận chưa chứng minh client cuối đã xử lý xong.

Spring broker relay tự reconnect system connection khi broker hồi phục, nhưng client connection không tự được reconnect thay cho client. Ứng dụng cần lắng nghe `BrokerAvailabilityEvent`, xử lý `MessageDeliveryException` và xây dựng logic reconnect ở client.

### 5.3. STOMP receipt và ACK không phải một thứ

- **Receipt** xác nhận broker đã xử lý frame tương ứng theo semantics STOMP/broker. Nó không chứng minh subscriber đã xử lý message.
- **ACK** là xác nhận của subscriber đối với message được giao theo subscription ACK mode. Nó có thể ảnh hưởng việc broker giữ hay xóa message, nhưng không tự tạo transaction nguyên tử với database nghiệp vụ.
- **Publisher confirm** của broker-specific protocol (ví dụ RabbitMQ AMQP) là một cơ chế khác; không đồng nhất với STOMP receipt.

Simple broker không hỗ trợ ACK/receipt. Với external broker, kiểm tra tài liệu broker cụ thể và test thực tế trên queue/destination được cấu hình.

### 5.4. Theo dõi disconnect trong STOMP

Spring có thể phát các event như:

- `SessionConnectEvent`: nhận STOMP CONNECT.
- `SessionConnectedEvent`: broker phản hồi CONNECTED.
- `SessionSubscribeEvent` và `SessionUnsubscribeEvent`: subscription thay đổi.
- `SessionDisconnectEvent`: STOMP session kết thúc.
- `BrokerAvailabilityEvent`: system connection tới external broker thay đổi trạng thái.

`SessionDisconnectEvent` có thể xuất hiện nhiều hơn một lần cho một session. Listener phải idempotent. Không dùng số event disconnect thô làm số session đã đóng duy nhất nếu chưa deduplicate theo session ID.

Ngoài graceful `DISCONNECT`, cần thử abrupt socket close, process kill, network blackhole và proxy reset. Trong các trường hợp đó, server có thể phát hiện disconnect sau heartbeat timeout thay vì ngay lập tức.

### 5.5. Đo WebSocket/STOMP

Các số liệu nên thu thập:

- Current/total/abnormally closed WebSocket sessions.
- Connect failures, transport errors, send limit exceeded.
- STOMP CONNECT/CONNECTED/DISCONNECT counts.
- Inbound/outbound channel active threads và queue.
- Broker relay TCP connections và heartbeat errors.
- Message fan-out per publish.
- Client send buffer và message send duration.
- Số session reconnect và thời gian resubscribe.

Spring cung cấp bean `WebSocketMessageBrokerStats` để tổng hợp thống kê session, STOMP frame, broker relay và channel executor. Có thể quan sát qua log/JMX và đưa vào hệ thống monitoring. Nếu outbound channel queue tăng, có thể do client chậm hoặc application gửi nhanh hơn tốc độ client nhận.

## 6. Đo RSocket theo từng interaction model

RSocket có bốn interaction model. Chúng có ý nghĩa khác nhau khi request hoàn tất hoặc connection bị ngắt.

### 6.1. Request-Response

Một request nhận một response.

```java
Mono<OrderResult> result = requester
        .route("orders.create")
        .data(command)
        .retrieveMono(OrderResult.class);
```

Nên đo:

- Request rate và response rate.
- p50/p95/p99 response latency.
- Timeout và error rate.
- Số request đang pending.
- Số request retry và duplicate business operation.

Response là bằng chứng responder đã trả kết quả theo protocol. Nhưng nếu responder đã commit database rồi connection bị đứt trước khi requester nhận response, requester không biết operation đã thành công hay chưa. Retry có thể tạo side effect trùng. Dùng idempotency key hoặc query trạng thái operation trước khi retry.

### 6.2. Fire-and-Forget

Một message một chiều, không có response payload.

```java
Mono<Void> sent = requester
        .route("audit.append")
        .data(event)
        .send();
```

`send()` hoàn tất không tương đương với business ACK từ responder. Fire-and-Forget phù hợp khi requester không cần kết quả đồng bộ và ứng dụng có thể chấp nhận mức xác nhận thấp hơn hoặc có cơ chế đối soát riêng.

Khi disconnect:

- Frame có thể chưa tới responder.
- Responder có thể đã nhận và xử lý nhưng requester không có response để xác nhận.
- Retry phía client có thể gây duplicate.
- Không có response không cho biết operation đã thất bại hay đã hoàn tất.

Nếu sự kiện quan trọng cần bảo đảm, dùng Request-Response với application ACK, hoặc broker có persistence/ACK phù hợp, và idempotency cho consumer.

### 6.3. Request-Stream

Một request mở ra một stream response.

```java
Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .data(symbol)
        .retrieveFlux(PriceUpdate.class);
```

RSocket sử dụng Reactive Streams demand. Consumer có thể yêu cầu số phần tử tiếp theo bằng `request(n)`; responder cần tôn trọng demand. Backpressure giúp kiểm soát tốc độ phát và giảm buffer khi producer/consumer có thể phối hợp.

Cần đo:

- Số stream đang hoạt động.
- Messages/sec trên mỗi stream và tổng thể.
- Demand được yêu cầu và tốc độ phát.
- Cancel count, stream error và keepalive timeout.
- Buffer size và thời gian consumer xử lý từng item.

Backpressure không phải persistence. Nó điều tiết số message đang được phép phát; khi connection bị mất, stream có thể kết thúc hoặc cần resumption theo cấu hình. Nếu ứng dụng cần tiếp tục từ một vị trí nghiệp vụ, hãy dùng sequence/cursor và cho phép client resume từ offset đã xử lý.

### 6.4. Channel

Hai bên trao đổi stream message theo hai chiều.

```java
Flux<ServerEvent> events = requester
        .route("session.exchange")
        .data(clientEvents)
        .retrieveFlux(ServerEvent.class);
```

Channel thích hợp cho tương tác hai chiều liên tục. Mỗi chiều có demand/backpressure riêng. Cần đo riêng inbound và outbound rate, cancellation, demand, queue, latency và số stream active.

Khi client chậm, backpressure có thể làm producer giảm tốc độ nếu toàn bộ pipeline giữ được reactive semantics. Nếu một handler block hoặc tự buffer vô hạn, lợi ích backpressure có thể bị mất.

### 6.5. Lease, keepalive và resumption

- **Keepalive:** giúp phát hiện peer hoặc connection không còn phản hồi; không lưu message nghiệp vụ.
- **Leasing:** giới hạn số request được phép khởi tạo trong một khoảng thời gian; đây là throttling, không phải delivery ACK.
- **Session resumption:** cho phép khôi phục session sau một số lỗi kết nối nếu hai bên hỗ trợ và còn đủ state/buffer. Nó không tương đương durable message store và không bảo đảm side effect nghiệp vụ exactly-once.
- **Backpressure:** điều tiết demand của stream; không tự lưu message khi process hoặc connection mất.

Khi test resume, ngắt transport trong lúc có stream đang chạy, reconnect trong cửa sổ resume, rồi kiểm tra sequence đã nhận, sequence bị lặp và sequence bị thiếu. Thực hiện thêm test process restart và buffer exhaustion. Đừng chỉ test network flap ngắn rồi kết luận mọi loại crash đều có thể resume.

### 6.6. Ma trận giới hạn của RSocket

| Model | Có response? | Flow control | Sau disconnect |
|---|---|---|---|
| Request-Response | Một response | Một request/response, timeout | Retry có thể lặp side effect nếu response bị mất |
| Fire-and-Forget | Không | Không có response để xác nhận xử lý | Outcome có thể không xác định; retry có thể duplicate |
| Request-Stream | Nhiều response | Reactive Streams demand | Stream có thể lỗi/cancel; resume hoặc cursor là trách nhiệm bổ sung |
| Channel | Hai chiều | Demand cho các stream | Cần kiểm tra resumption và khôi phục offset/operation |

Không nên dùng Fire-and-Forget cho lệnh thanh toán, cập nhật quan trọng hoặc event cần chứng minh đã commit nếu không có một cơ chế xác nhận khác.

## 7. Đo JMS và AMQP/RabbitMQ: xác nhận, ACK và redelivery

Broker message queue thường cung cấp khả năng lưu trữ và redelivery tốt hơn in-memory channel hoặc simple WebSocket broker. Tuy nhiên, guarantee phụ thuộc cấu hình producer, queue, message, consumer, transaction và broker.

### 7.1. JMS

Các điểm cần phân biệt:

- `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` và transacted session có semantics khác nhau.
- Với Spring listener container, `sessionTransacted=true` cho phép rollback receive khi listener xử lý thất bại; message có thể được redeliver.
- Durable topic subscription khác queue subscription thông thường.
- Persistent message và durable destination có thể giúp giữ message qua restart, tùy provider và cấu hình.
- Redelivery có thể tạo duplicate; consumer cần idempotency.

Khi benchmark JMS, đo send latency, receive latency, transaction commit time, redelivery count, queue depth, consumer count và số message tồn sau khi consumer bị kill.

Đừng chỉ kiểm tra listener method đã được gọi. Hãy kiểm tra database commit và trạng thái broker sau khi listener throw exception hoặc process chết.

### 7.2. AMQP/RabbitMQ

Các cơ chế chính:

- **Publisher confirms:** producer nhận xác nhận broker đã chấp nhận hoặc từ chối publish theo semantics của broker/queue.
- **Publisher returns:** phát hiện message không được route tới queue nào khi dùng `mandatory` và cấu hình phù hợp.
- **Consumer ACK:** xác nhận consumer đã xử lý message và broker có thể loại bỏ message khỏi queue.
- **NACK/requeue:** có thể yêu cầu broker giao lại message.
- **Durable queue + persistent message:** hỗ trợ lưu message qua restart theo loại queue và chính sách replication/persistence.
- **Prefetch:** giới hạn số message broker gửi trước cho consumer chưa ACK; ảnh hưởng throughput và số message unacked.

Publisher confirm không chứng minh consumer đã nhận. Consumer ACK không chứng minh database và broker cùng commit nguyên tử. Nếu consumer commit database rồi crash trước ACK, broker có thể redeliver; nếu ACK trước khi commit database, có thể mất message khi database transaction rollback hoặc process chết.

### 7.3. Failure window của consumer

```text
Broker giao message
      |
      v
Consumer nhận message
      |
      v
Ghi database
      |
      +---- process crash trước DB commit
      |       -> broker redeliver nếu chưa ACK
      |
      +---- DB commit thành công
              |
              +---- crash trước ACK
              |       -> broker redeliver
              |       -> cần idempotency
              |
              +---- ACK
                      -> broker có thể xóa message
```

Với ACK sau commit, hệ thống thường chọn at-least-once và chấp nhận duplicate. Dùng inbox table có unique constraint theo `messageId` để đảm bảo một event chỉ áp dụng một lần trong transaction database.

### 7.4. Publisher failure window

```text
Producer gửi publish
      |
      v
Broker nhận message
      |
      +---- producer mất connection trước khi nhận confirm
      |       -> producer không biết broker đã nhận hay chưa
      |       -> retry có thể tạo duplicate
      |
      +---- broker NACK/return
      |       -> xử lý lỗi hoặc route sai
      |
      +---- publisher confirm ACK
              -> broker xác nhận theo cấu hình queue
              -> consumer vẫn có thể chưa xử lý
```

Khi publish quan trọng, kết hợp publisher confirms, mandatory returns, retry có kiểm soát, message ID ổn định và outbox pattern. Không retry vô hạn mà không có idempotency.

## 8. Đo metrics bằng Micrometer

Không nên gắn `messageId`, `sessionId` hoặc username vào metric tag vì số lượng giá trị có thể tăng rất lớn. Dùng trace/log cho ID chi tiết; metric chỉ dùng tag có cardinality thấp như `transport`, `model`, `destinationGroup`, `outcome` hoặc `consumer`.

Ví dụ instrumentation cho thời gian xử lý handler trong một process:

```java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class MessageMetrics {

    private final Counter received;
    private final Counter completed;
    private final Counter failed;
    private final Timer processing;

    public MessageMetrics(MeterRegistry registry) {
        this.received = Counter.builder("messaging.messages.received")
                .tag("transport", "stomp")
                .register(registry);

        this.completed = Counter.builder("messaging.messages.completed")
                .tag("transport", "stomp")
                .register(registry);

        this.failed = Counter.builder("messaging.messages.failed")
                .tag("transport", "stomp")
                .register(registry);

        this.processing = Timer.builder("messaging.handler.duration")
                .tag("transport", "stomp")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void process(Runnable handler) {
        received.increment();
        long started = System.nanoTime();

        try {
            handler.run();
            completed.increment();
        }
        catch (RuntimeException ex) {
            failed.increment();
            throw ex;
        }
        finally {
            processing.record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
        }
    }
}
```

Đây là ví dụ đo thời gian handler trong cùng process, không phải end-to-end latency từ producer ở máy khác. Để đo end-to-end, đưa timestamp và message ID vào payload hoặc trace context, đồng bộ clock giữa các máy và kiểm tra kết quả theo từng message. `System.nanoTime()` chỉ dùng để đo duration bên trong một JVM.

Với Prometheus, theo dõi các chuỗi:

- `rate(messaging_messages_received_total[1m])`
- `rate(messaging_messages_completed_total[1m])`
- `rate(messaging_messages_failed_total[5m])`
- Histogram bucket của `messaging_handler_duration_seconds_bucket`
- Queue depth và oldest message age do broker/exporter cung cấp.

Nếu received rate liên tục cao hơn completed rate, backlog sẽ tăng. Nếu p99 tăng cùng queue depth, consumer hoặc downstream dependency có thể đang là bottleneck.

## 9. Thiết kế test ngắt kết nối theo từng failure point

Một bài test disconnect phải ghi rõ ngắt ở đâu và quan sát điều gì. Dùng cùng một test case cho tất cả mô hình là chưa đủ vì mỗi mô hình có điểm xác nhận khác nhau.

### 9.1. Producer disconnect

Thử các trường hợp:

1. Ngắt kết nối trước khi gọi send.
2. Ngắt trong lúc frame/message đang được ghi.
3. Broker nhận message nhưng producer chưa nhận confirm/receipt.
4. Producer nhận confirm rồi process chết trước khi ghi trạng thái “đã gửi” vào database.
5. Retry sau reconnect.

Kết quả cần đo: missing, duplicate, unknown outcome, retry count và thời gian phục hồi.

### 9.2. Consumer disconnect

Thử:

1. Consumer chết trước khi nhận message.
2. Consumer nhận message nhưng chưa bắt đầu handler.
3. Consumer đang xử lý và chết trước commit.
4. Database commit xong nhưng ACK chưa được gửi.
5. ACK đã gửi nhưng consumer mất connection trước khi nhận phản hồi.
6. Consumer reconnect và nhận lại message.

Với at-least-once broker, trường hợp 4 thường tạo redelivery. Consumer phải xử lý duplicate an toàn.

### 9.3. Broker hoặc application node restart

Thử riêng:

- Restart một Spring instance nhưng giữ broker.
- Restart external broker trong khi Spring relay đang hoạt động.
- Restart broker và Spring cùng lúc.
- Kill node đang giữ WebSocket connection.
- Tạm chặn network giữa producer và broker.
- Tạm chặn network giữa consumer và broker.
- Chạy load liên tục trong lúc node được drain để deploy.

Ghi thời gian từ lúc lỗi bắt đầu đến khi:
- Producer có thể gửi lại.
- Consumer bắt đầu nhận message.
- Client reconnect và resubscribe.
- Backlog quay về baseline.
- Error rate và p99 latency trở lại SLO.

### 9.4. Slow consumer

Tạo consumer đọc chậm hơn producer trong một khoảng thời gian. Quan sát:

- Queue depth có tăng không?
- Backpressure có giảm tốc producer không?
- Outbound buffer có tăng không?
- Send timeout có đóng client không?
- Có message bị drop, requeue hoặc redeliver không?
- Sau khi consumer nhanh trở lại, backlog mất bao lâu để drain?

Không dùng một test chỉ có consumer nhanh. Slow consumer là tình huống thường làm lộ rõ giới hạn buffer và memory.

## 10. Ví dụ test disconnect idempotent cho STOMP

Spring có thể phát `SessionDisconnectEvent` khi client gửi DISCONNECT hoặc khi WebSocket transport bị đóng. Event có thể được phát hơn một lần cho cùng session, vì vậy xử lý cleanup cần idempotent.

Ví dụ listener chỉ ghi nhận event và ủy quyền cleanup cho một service idempotent:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompDisconnectListener {

    private final SessionCleanupService cleanupService;

    public StompDisconnectListener(SessionCleanupService cleanupService) {
        this.cleanupService = cleanupService;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(event.getMessage());

        String sessionId = accessor.getSessionId();
        if (sessionId != null) {
            cleanupService.closeSessionOnce(sessionId);
        }
    }
}
```

`closeSessionOnce` cần bảo đảm thao tác cleanup có thể gọi nhiều lần mà không gây side effect lặp. Trong hệ thống nhiều node, có thể dùng state có TTL hoặc unique key trong shared store. Không giữ một `Set` vô hạn trong memory chỉ để deduplicate disconnect vì số session tích lũy sẽ tăng theo thời gian.

Test phải kiểm tra cả graceful disconnect và abrupt disconnect. Đừng giả định server luôn nhận STOMP DISCONNECT frame; khi TCP bị reset hoặc client process bị kill, server có thể chỉ phát hiện qua transport/heartbeat timeout.

## 11. Ma trận bảo đảm và giới hạn theo mô hình

| Mô hình | Xác nhận mạnh nhất mặc định | Khi disconnect | Có persistence mặc định? |
|---|---|---|---|
| DirectChannel | Handler đồng bộ hoàn tất trong đường gọi nếu không lỗi | Không có retry tự động | Không |
| ExecutorChannel | Task được dispatch/accept | Task chưa chạy có thể mất khi process dừng | Không |
| QueueChannel | Message vào queue memory | Queue mất khi process dừng | Không |
| STOMP simple broker | Broker memory nhận và broadcast cho subscriber đang hoạt động | Session/subscription mất; không lưu offline | Không |
| STOMP external broker | Theo receipt/ACK/destination semantics của broker | Broker có thể giữ/requeue nếu cấu hình phù hợp; client phải reconnect | Tùy queue/broker |
| RSocket Request-Response | Responder trả một response | Response có thể mất sau khi side effect đã commit | Không |
| RSocket Fire-and-Forget | Không có response payload | Outcome có thể không xác định; retry có thể duplicate | Không |
| RSocket Request-Stream/Channel | Stream frame theo demand/backpressure | Stream có thể lỗi/cancel; resume/cursor cần cấu hình và logic bổ sung | Không |
| JMS transacted | Transaction receive/commit theo provider/container | Rollback có thể redeliver | Tùy destination/provider |
| AMQP manual ACK | Consumer ACK sau xử lý | Message chưa ACK thường được redeliver | Tùy durable queue/message/replication |

Bảng này mô tả hành vi mặc định hoặc phổ biến, không thay thế cấu hình cụ thể. Broker, protocol version, queue type, ACK mode, transaction manager và failure policy có thể thay đổi kết quả.

## 12. Cách đọc kết quả benchmark

### Throughput tăng nhưng p99 tăng mạnh

Có thể hệ thống đang tiến gần saturation. Kiểm tra queue depth, executor active count, GC pause, DB connection pool và broker flow control. Nếu completed rate không tăng dù offered rate tăng, thêm client chỉ làm latency và backlog tăng.

### `send()` nhanh nhưng message không được xử lý kịp

Có thể đang đo ở tầng dispatch thay vì tầng handler. Đặc biệt với ExecutorChannel, QueueChannel, broker publish hoặc RSocket Fire-and-Forget, thời gian API trả về không phải thời gian xử lý nghiệp vụ.

### Reconnect thành công nhưng message bị thiếu

Kiểm tra model có persistence hay không, broker ACK/receipt, subscription có được khôi phục không, consumer offset/cursor có được lưu không và khoảng mất kết nối có cơ chế replay không.

### Message bị trùng sau restart

Kiểm tra ACK xảy ra trước hay sau DB commit. Với at-least-once, duplicate là hành vi có thể dự đoán. Thêm idempotency key, inbox table hoặc unique constraint thay vì cố loại bỏ mọi retry.

### Chỉ node có client mới nhận được broadcast

Nếu dùng simple broker, mỗi node có state riêng và không cluster. Chuyển sang external broker relay và cấu hình user registry/unresolved destination broadcast khi cần gửi user destination cross-node.

### Queue tăng dù CPU còn thấp

Bottleneck có thể là I/O, broker throughput, DB connection pool, downstream HTTP, lock contention hoặc consumer concurrency. Tăng CPU/thread không nhất thiết giải quyết được.

### Disconnect event bị đếm nhiều lần

Deduplicate theo session ID và thiết kế cleanup idempotent. Phân biệt số transport close, STOMP DISCONNECT frame và số logical user session kết thúc.

## 13. Kịch bản thực hành đề xuất

Có thể dùng một bài test chung với `messageId`, `sequence`, timestamp và một business handler đơn giản. Chạy lần lượt các cấu hình:

| Lượt | Mô hình | Tải | Failure injection | Điều cần chứng minh |
|---|---|---|---|---|
| 1 | DirectChannel | Tăng producer rate | Handler throw exception | Sender thấy lỗi đồng bộ; không có persistence |
| 2 | ExecutorChannel | Tăng producer rate | Executor bão hòa | Send có thể xong trước handler; queue/rejection được quan sát |
| 3 | QueueChannel | Producer nhanh hơn consumer | Kill process khi queue còn message | Message memory có thể mất |
| 4 | STOMP simple broker | Nhiều WebSocket subscriber | Disconnect/restart node | Session/subscription và offline delivery không bền vững |
| 5 | STOMP broker relay | Nhiều node, fan-out | Restart broker | System relay reconnect; client reconnect/resubscribe |
| 6 | RSocket Request-Response | Concurrent request | Drop connection sau khi handler commit | Retry có thể duplicate nếu response bị mất |
| 7 | RSocket Fire-and-Forget | Burst event | Drop connection trong lúc send | Không có application response để biết outcome |
| 8 | RSocket Stream/Channel | Producer nhanh, consumer chậm | Cancel và network interruption | Backpressure, cancellation và resume/cursor |
| 9 | JMS transacted | Nhiều consumer | Throw exception trước commit | Rollback/redelivery theo provider |
| 10 | AMQP manual ACK | Prefetch thay đổi | Kill consumer sau DB commit trước ACK | Redelivery và idempotency |

Cho mỗi lượt, lưu cấu hình, phiên bản Spring/broker, số client, payload size, offered rate, completed rate, p95/p99, duplicate/missing count, queue depth và thời gian recovery. Không so sánh hai lượt nếu khác topology, hardware hoặc cấu hình persistence mà không ghi rõ.

## 14. Nguyên tắc thiết kế để đạt kết quả nghiệp vụ đúng

1. **Dùng message ID ổn định:** retry phải giữ nguyên ID của operation ban đầu để consumer nhận ra duplicate.
2. **Idempotent consumer:** cùng một message có thể đến nhiều lần nhưng side effect nghiệp vụ chỉ áp dụng một lần.
3. **ACK sau commit:** nếu dùng broker ACK, chỉ ACK sau khi phần xử lý cần bảo vệ đã commit.
4. **Transactional outbox:** ghi business change và event cần publish trong cùng database transaction; relay outbox có thể retry publish.
5. **Inbox/deduplication:** ghi message ID đã xử lý trong cùng transaction với business update.
6. **Bounded queue:** đặt giới hạn buffer/queue và định nghĩa backpressure, reject hoặc dead-letter rõ ràng.
7. **Retry có giới hạn:** dùng exponential backoff và jitter; tránh retry vô hạn gây retry storm.
8. **Dead-letter và poison message:** message lỗi lặp lại phải có đường xử lý, quan sát và replay có kiểm soát.
9. **Trace context:** nối trace từ producer qua broker tới consumer để thấy thời gian từng chặng.
10. **Không đánh đồng transport ACK với business ACK:** nếu caller cần biết nghiệp vụ đã commit, thiết kế response/receipt ở tầng nghiệp vụ.

## 15. Checklist nghiệm thu

- [ ] Workload có số connection, offered rate, payload size, fan-out và thời gian chạy rõ ràng.
- [ ] Có warm-up, ramp-up, steady state, burst và soak test.
- [ ] Có cả open-loop và closed-loop test nếu phù hợp.
- [ ] Báo cáo offered rate và completed/committed rate riêng.
- [ ] Báo cáo p50/p95/p99, error, timeout, missing và duplicate.
- [ ] Mỗi message có run ID, message ID và sequence.
- [ ] Đo queue depth, oldest message age, executor queue và broker unacked.
- [ ] Đã test slow consumer và buffer saturation.
- [ ] Đã test graceful disconnect và abrupt disconnect.
- [ ] Đã test producer crash, consumer crash, broker restart và node drain.
- [ ] STOMP simple broker được đánh giá như in-memory broker, không gán durability.
- [ ] STOMP relay được kiểm tra theo ACK/receipt/destination semantics của broker thật.
- [ ] RSocket FNF không bị coi là application ACK.
- [ ] RSocket backpressure được phân biệt với persistence.
- [ ] JMS/AMQP transaction và ACK được kiểm tra tại failure window trước/sau commit.
- [ ] Consumer có idempotency hoặc deduplication nếu retry có thể tạo duplicate.
- [ ] Reconnect có resubscribe/replay/cursor khi yêu cầu nghiệp vụ cần.
- [ ] Có số liệu thời gian recovery và thời gian drain backlog.
- [ ] Kết quả có cấu hình, phiên bản, topology và lệnh chạy để tái lập.

## Tài liệu tham khảo

- [Spring Framework — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)
- [Spring Framework — STOMP Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
- [Spring Framework — STOMP Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — STOMP External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — STOMP Application Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration — Channel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Framework — JMS Receiving and Transactions](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/connections.html)
- [Spring AMQP — Resilience and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring Framework — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
