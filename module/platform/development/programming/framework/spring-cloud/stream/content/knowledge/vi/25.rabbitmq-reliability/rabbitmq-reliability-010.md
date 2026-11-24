# Phát lại qua TTL, hàng đợi thử lại và hàng đợi cách ly

Khi consumer RabbitMQ nhận được message nhưng xử lý thất bại, hệ thống cần quyết định có thử lại ngay, chờ một khoảng thời gian rồi thử lại, hay đưa message sang nơi cách ly để điều tra. Nếu mọi lỗi đều được requeue ngay lập tức, message có thể quay lại consumer liên tục, tạo vòng lặp nóng và chiếm tài nguyên. Nếu chỉ dùng retry trong listener container, thread consumer phải chờ trong thời gian backoff và không thể xử lý message khác trên thread đó.

RabbitMQ hỗ trợ dead-letter exchange (DLX) để chuyển message bị reject, hết TTL hoặc vượt giới hạn queue sang exchange khác. Kết hợp DLX với queue có message TTL tạo thành mô hình retry queue: message lỗi được chuyển sang queue chờ, hết thời gian TTL thì được định tuyến trở lại queue chính. Spring Cloud Stream RabbitMQ binder hỗ trợ mẫu này thông qua các thuộc tính như autoBindDlq, dlqTtl và dlqDeadLetterExchange.

Hàng đợi thử lại và hàng đợi cách ly có mục đích khác nhau. Retry queue giữ message tạm thời để thử lại sau một khoảng chờ. Quarantine queue (parking-lot queue) giữ message không thể xử lý để người vận hành hoặc quy trình sửa dữ liệu kiểm tra và phát lại có chủ đích. Bài học này trình bày cách thiết kế hai loại queue, theo dõi số lần thử, bảo toàn metadata, tránh vòng lặp vô hạn và kiểm thử hành vi giao nhận.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích dead-letter exchange, dead-letter queue và message TTL.
- Thiết kế vòng lặp retry queue bằng TTL và DLX.
- Cấu hình retry queue do RabbitMQ binder provision bằng autoBindDlq và dlqTtl.
- Định tuyến message hết TTL trở lại queue chính bằng default exchange.
- Phân biệt retry trong binder, requeue tức thì và retry qua TTL.
- Dùng header x-death để đếm chu kỳ dead-letter và giới hạn số lần thử.
- Thiết kế quarantine/parking-lot queue để giữ message cần điều tra.
- Phân biệt binder republishToDlq với broker dead-lettering.
- Bảo vệ message khỏi mất hoặc trùng khi publish, dead-letter và replay.
- Kiểm thử retry, TTL, DLT, quarantine và vận hành với Spring Cloud Stream RabbitMQ binder.

## 1. Retry là một quyết định về lỗi

Không phải mọi lỗi xử lý message đều có cùng nguyên nhân hoặc cần cùng chính sách:

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Tạm thời | Dịch vụ thanh toán timeout, database tạm mất kết nối | Thử lại sau một khoảng chờ |
| Quá tải | HTTP 429, connection pool cạn | Backoff dài hơn và giới hạn tốc độ |
| Dữ liệu không hợp lệ | Thiếu orderId, JSON sai schema | Cách ly để sửa hoặc điều tra |
| Lỗi cấu hình | Credentials sai, exchange không tồn tại | Dừng retry vô ích và cảnh báo |
| Lỗi lập trình | Null pointer, bug mapping | Giới hạn retry, giữ message và điều tra |

Một chiến lược tin cậy cần trả lời ba câu hỏi:

1. Khi nào message được thử lại?
2. Thử lại tối đa bao nhiêu lần?
3. Sau khi không thể xử lý, message được giữ ở đâu và ai chịu trách nhiệm khôi phục?

Nếu không có giới hạn, một poison message có thể quay vòng mãi mãi. Nếu không có nơi cách ly, message lỗi có thể bị mất hoặc chỉ còn trong log mà không có cách phát lại đáng tin cậy.

## 2. Dead-letter exchange và dead-letter queue

Dead-lettering là cơ chế RabbitMQ chuyển message từ queue nguồn sang một exchange khác khi một trong các sự kiện sau xảy ra:

- Consumer reject hoặc nack message với requeue=false.
- Message hết thời gian sống (TTL).
- Queue vượt giới hạn độ dài hoặc dung lượng và áp dụng overflow phù hợp.
- Message trong quorum queue vượt delivery limit.

DLX là một exchange bình thường. Queue nguồn khai báo dead-letter-exchange và có thể khai báo dead-letter-routing-key. Khi message bị dead-letter, broker publish nó tới DLX; exchange dùng routing key và binding để chọn queue đích.

~~~text
Producer
   |
   v
Exchange chính
   |
   v
Queue chính (destination.group)
   |
   | reject / TTL / queue limit
   v
Dead-letter exchange (DLX)
   |
   v
Dead-letter queue (DLQ)
~~~

DLQ thường được dùng để giữ message lỗi. Tuy nhiên, nếu DLQ có TTL và được cấu hình dead-letter trở lại queue chính, nó cũng có thể đóng vai trò retry queue.

### 2.1. Routing key và default exchange

RabbitMQ có default exchange với tên rỗng. Mỗi queue tự động được bind tới default exchange bằng routing key bằng chính tên queue. Vì vậy, publish vào default exchange với routing key là tên queue sẽ định tuyến message tới queue đó.

Trong RabbitMQ binder, queue consumer group thường có tên theo dạng destination.group. Ví dụ destination là orders và group là fulfillment, queue chính thường là orders.fulfillment. Khi muốn message hết TTL ở DLQ quay lại queue chính, có thể đặt dlqDeadLetterExchange thành chuỗi rỗng để dùng default exchange và dùng routing key bằng tên queue chính.

Không nhầm tên exchange rỗng với giá trị không được cấu hình. Trong YAML, để biểu diễn default exchange, thuộc tính cần được khai báo nhưng để giá trị trống:

~~~yaml
dlq-dead-letter-exchange: ""
~~~

Nếu bỏ thuộc tính hoàn toàn, binder có thể không khai báo dead-letter exchange cho DLQ; message hết TTL khi đó không có tuyến quay về queue chính.

### 2.2. Header x-death

RabbitMQ thêm header x-death khi message bị dead-letter. Header chứa các bản ghi về queue, exchange, routing keys, reason, thời điểm và số lần dead-letter. Một số lần dead-letter có cùng cặp queue/reason có thể được nén thành một mục có trường count.

Trong AMQP 0-9-1, count thường được biểu diễn dưới dạng Long. Ứng dụng nên đọc theo kiểu Number và chuyển đổi an toàn thay vì ép kiểu Integer.

Ví dụ ý nghĩa một mục x-death:

| Trường | Ý nghĩa |
|---|---|
| queue | Queue nơi message bị dead-letter |
| reason | Nguyên nhân như rejected hoặc expired |
| count | Số lần xảy ra chu kỳ dead-letter tương ứng |
| exchange | Exchange nguồn của lần dead-letter |
| routing-keys | Routing key được dùng |
| time | Thời điểm broker ghi nhận sự kiện |

x-death là metadata hữu ích để giới hạn retry và điều tra. Không nên dựa vào một index cố định trong danh sách; hãy tìm mục theo queue và reason phù hợp với topology.

## 3. Retry trong listener container và retry qua TTL

Spring Cloud Stream RabbitMQ binder có retry trong container theo các thuộc tính maxAttempts, backOffInitialInterval, backOffMaxInterval và backOffMultiplier. Khi retry này hoạt động, listener container thread bị tạm dừng trong thời gian backoff.

Retry trong container phù hợp khi:

- Cần thử lại một số lần ngắn.
- Muốn giữ message trên cùng consumer flow.
- Cần giữ thứ tự với một consumer và có thể chấp nhận thread chờ.

Nhược điểm là thread đang xử lý không thể nhận message khác trong thời gian chờ. Với một consumer và backoff dài, throughput có thể giảm đáng kể.

Retry qua TTL/DLX đưa message sang queue khác và để broker giữ trong thời gian chờ. Consumer chính có thể tiếp tục xử lý message khác. Khi TTL hết, broker định tuyến message trở lại queue chính.

| Tiêu chí | Binder retry | TTL/DLX retry |
|---|---|---|
| Nơi chờ | Thread listener/container | Retry queue trong broker |
| Thread consumer | Bị giữ trong thời gian backoff | Có thể xử lý message khác |
| Cấu hình chính | maxAttempts và backoff | DLQ, TTL và DLX trên DLQ |
| Theo dõi số lần thử | Retry context/headers tùy cấu hình | x-death và metadata ứng dụng |
| Phù hợp | Retry ngắn, cần giữ thứ tự trên thread | Backoff dài hơn, tránh chặn consumer |
| Độ phức tạp | Ít topology hơn | Cần queue, exchange và routing đúng |

Hai cơ chế có thể kết hợp nhưng phải tính tổng số lần thử. Nếu binder retry ba lần rồi mới dead-letter sang TTL queue, một chu kỳ TTL có thể bao gồm ba lần gọi listener. Hãy xác định rõ đơn vị đếm retry và đặt giới hạn tổng thể.

## 4. Cấu hình retry queue bằng RabbitMQ binder

Rabbit binder có thể tự khai báo DLQ cho consumer group. Để tạo retry cycle:

1. Bật autoBindDlq để binder tạo DLQ.
2. Đặt dlqTtl thành khoảng chờ mong muốn.
3. Đặt dlqDeadLetterExchange thành default exchange bằng chuỗi rỗng.
4. Để routing key của DLQ trỏ về queue chính, hoặc cấu hình dlqDeadLetterRoutingKey rõ ràng.
5. Đưa message lỗi vào DLQ thay vì requeue ngay lập tức.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
          consumer:
            max-attempts: 1
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dlq-ttl: 5000
              dlq-dead-letter-exchange: ""
~~~

Trong ví dụ:

- Queue chính thường là orders.fulfillment.
- Binder tạo DLQ cho group.
- Message bị dead-letter vào DLQ.
- Message nằm trong DLQ tối đa 5.000 ms.
- Khi hết TTL, DLQ dead-letter message tới default exchange.
- Default exchange định tuyến message theo queue name trở lại orders.fulfillment.

max-attempts: 1 tắt retry nội bộ của binder, để một lần listener thất bại được đưa vào dead-letter flow. Nếu muốn có một số lần retry ngắn tại container trước khi đưa vào TTL queue, có thể tăng max-attempts và backoff, nhưng phải tính số lần thử tổng thể.

### 4.1. Đưa message vào DLQ

Để buộc một message bị dead-letter, listener có thể ném AmqpRejectAndDontRequeueException. Binder cũng có thuộc tính requeueRejected; khi false, exception từ listener không được requeue về queue chính và có thể đi qua DLX nếu queue đã khai báo dead-letter exchange.

~~~java
@Bean
Consumer<Message<OrderCreated>> processOrder(OrderService service) {
    return message -> {
        try {
            service.process(message.getPayload());
        } catch (TemporaryDependencyException ex) {
            throw new AmqpRejectAndDontRequeueException(
                    "Route to delayed retry queue", ex);
        }
    };
}
~~~

Đây là ví dụ định tuyến lỗi sang dead-letter flow. Khi dùng binder retry, cần bảo đảm exception được đánh dấu retryable hoặc non-retryable đúng theo chính sách. Nếu retry nội bộ đã hết, binder mới thực hiện hành vi DLQ được cấu hình.

### 4.2. republishToDlq

Rabbit binder có thuộc tính republishToDlq:

- Khi true, binder publish lại message lỗi sang DLQ và bổ sung metadata như exception message và stack trace của lỗi cuối cùng.
- Khi false, binder reject message; RabbitMQ dùng DLX đã cấu hình để định tuyến message gốc.

Giá trị mặc định có thể thay đổi theo phiên bản binder. Hãy khai báo tường minh nếu logic retry phụ thuộc vào header hoặc việc message được republish.

Với republishToDlq=true, message có thêm header chẩn đoán hữu ích. Với republishToDlq=false, broker dead-letter message theo topology. Cần kiểm thử xem x-death, delivery metadata và payload được giữ như thế nào trong phiên bản cụ thể.

## 5. Vòng lặp TTL retry hoạt động thế nào?

Một chu kỳ retry qua TTL:

~~~mermaid
flowchart TD
    A[Producer] --> B[Exchange orders]
    B --> C[Queue orders.fulfillment]
    C --> D[Consumer xử lý]
    D --> E{Thành công?}
    E -->|Có| F[Ack và hoàn tất]
    E -->|Không| G[Reject không requeue]
    G --> H[DLX]
    H --> I[Retry queue / DLQ có TTL]
    I --> J{TTL hết?}
    J -->|Chưa| I
    J -->|Rồi| K[Default exchange]
    K --> C
~~~

Message lỗi được chuyển sang DLQ/retry queue. Broker giữ message trong khoảng TTL; sau khi hết hạn, nó dead-letter tới default exchange. Vì default exchange có binding tự động tới queue chính bằng queue name, message quay lại queue để consumer thử lại.

### 5.1. Ví dụ chu kỳ

Giả sử queue chính là orders.fulfillment và dlqTtl bằng 5 giây:

1. Consumer nhận OrderCreated.
2. Dịch vụ phụ thuộc timeout; listener reject message.
3. RabbitMQ đưa message vào DLQ.
4. Message chờ 5 giây.
5. TTL hết; DLQ dead-letter tới default exchange.
6. Message được định tuyến về orders.fulfillment.
7. Consumer nhận lại cùng message.

Đây là vòng lặp retry vô hạn nếu không có điều kiện dừng. Cần kiểm tra x-death hoặc một retry counter ứng dụng để chuyển message sang quarantine sau số lần thử cho phép.

### 5.2. Nhiều mức backoff

Một DLQ với một dlqTtl chỉ cung cấp một khoảng chờ cố định. Nếu cần backoff tăng dần, có thể tạo nhiều retry queue:

| Queue | TTL | Hành động khi hết TTL |
|---|---:|---|
| orders.retry.5s | 5.000 ms | Route về queue chính |
| orders.retry.30s | 30.000 ms | Route về queue chính |
| orders.retry.5m | 300.000 ms | Route về queue chính |
| orders.quarantine | Không đặt TTL tự động | Giữ để điều tra |

Ứng dụng hoặc topology có thể chọn retry tier dựa trên số lần thử. Mỗi retry queue cần dead-letter exchange/routing key trỏ về queue chính. Nếu dùng exchange riêng, hãy khai báo binding rõ ràng và test routing key.

Rabbit binder autoBindDlq chủ yếu provision một DLQ cho consumer group. Nhiều retry tier thường cần topology tùy chỉnh hoặc các destination/binding riêng. Không giả định một thuộc tính dlqTtl tự tạo ra nhiều queue theo backoff schedule.

### 5.3. Delay exchange và delayed message plugin

RabbitMQ delayed message exchange plugin có thể trì hoãn định tuyến message bằng header x-delay. Đây là cách khác để thực hiện delay mà không cần một queue TTL riêng cho mỗi khoảng chờ.

Plugin là thành phần bổ sung của broker và cần được cài đặt/bật. Binder có thuộc tính delayedExchange và delayExpression cho delayed exchange. Hãy kiểm tra khả năng tương thích plugin và broker trước khi chọn. Với hệ thống cần queue retry dễ quan sát và không muốn phụ thuộc plugin, TTL/DLX vẫn là một lựa chọn phổ biến.

## 6. Giới hạn số lần thử bằng x-death

Vì TTL/DLX có thể tạo vòng lặp vô hạn, consumer cần biết message đã đi qua bao nhiêu chu kỳ. RabbitMQ thêm x-death header mỗi lần dead-letter.

Ví dụ đọc header:

~~~java
long deathCount(Message<?> message, String queueName, String reason) {
    Object header = message.getHeaders().get("x-death");
    if (!(header instanceof List<?> deaths)) {
        return 0L;
    }

    return deaths.stream()
            .filter(Map.class::isInstance)
            .map(Map.class::cast)
            .filter(death -> queueName.equals(death.get("queue")))
            .filter(death -> reason.equals(death.get("reason")))
            .map(death -> death.get("count"))
            .filter(Number.class::isInstance)
            .mapToLong(value -> ((Number) value).longValue())
            .max()
            .orElse(0L);
}
~~~

Ví dụ dùng Java pattern matching để dễ đọc; nếu dự án dùng Java thấp hơn, thay bằng các phép kiểm tra instanceof và ép kiểu truyền thống. Trong header AMQP, count thường là Long; dùng Number giúp tránh phụ thuộc kiểu số cụ thể. Truyền đúng queue và reason, ví dụ retry queue cùng reason expired, để không cộng nhầm lần reject ở queue chính với lần hết TTL ở retry queue.

Không nên đếm toàn bộ x-death một cách mù quáng. Header có thể chứa các mục cho nhiều queue và nhiều reason khác nhau. Hãy chọn mục của queue retry tương ứng và lý do rejected/expired theo topology.

### 6.1. Dừng retry sau ngưỡng

Khi số chu kỳ đạt ngưỡng, message không nên quay lại queue chính. Có thể:

- Chuyển sang quarantine queue.
- Publish tới parking-lot exchange với event ID và metadata.
- Ghi nhận trạng thái lỗi trong database rồi ack message chỉ sau khi lưu an toàn.
- Yêu cầu thao tác replay thủ công sau khi khắc phục nguyên nhân.

Nếu chỉ ném ImmediateAcknowledgeAmqpException, message được acknowledge và không tiếp tục retry; hành động này phù hợp khi chính sách cho phép bỏ message sau khi đã lưu hoặc ghi nhận ở nơi khác. Không dùng nó nếu chưa có bản sao an toàn của message cần điều tra.

### 6.2. Metadata ứng dụng

Ngoài x-death, có thể thêm header như:

- eventId: ID ổn định của sự kiện.
- retryAttempt: số lần retry logic của ứng dụng.
- originalQueue: queue ban đầu.
- firstFailedAt: thời điểm thất bại đầu tiên.
- lastFailureCode: mã lỗi cuối cùng.
- correlationId: mã truy vết xuyên dịch vụ.

Không dùng header retryAttempt thay cho x-death nếu broker topology có thể dead-letter từ nhiều queue. Nếu ứng dụng tự cập nhật retryAttempt, phải giữ nguyên eventId và cập nhật theo một quy tắc nhất quán.

## 7. Hàng đợi cách ly (quarantine/parking-lot queue)

Retry queue dành cho lỗi có khả năng tự phục hồi sau một khoảng chờ. Quarantine queue dành cho message cần con người hoặc một quy trình riêng kiểm tra trước khi phát lại.

Một message nên được cách ly khi:

- Payload sai schema hoặc thiếu trường bắt buộc.
- Vượt số lần retry đã định.
- Lỗi nghiệp vụ không thể tự phục hồi.
- Message gây poison loop và cần điều tra.
- Cần giữ message để tuân thủ kiểm toán hoặc xử lý thủ công.

### 7.1. Quarantine không tự động quay lại queue chính

Khác với retry queue, quarantine queue không nên có TTL/DLX tự động route lại queue chính. Nếu không, message lỗi vĩnh viễn sẽ tiếp tục quay vòng.

~~~text
Queue chính
   |
   | lỗi tạm thời
   v
Retry queue (TTL)
   |
   | hết TTL
   v
Queue chính

Queue chính
   |
   | hết retry / lỗi dữ liệu
   v
Quarantine / parking-lot queue
   |
   +--> Điều tra
   +--> Sửa dữ liệu hoặc dependency
   +--> Replay có kiểm soát
~~~

Quarantine queue nên durable, có quyền truy cập giới hạn, retention rõ ràng và dashboard để tìm kiếm theo eventId/correlationId. Nếu message có dữ liệu nhạy cảm, cần bảo vệ quyền truy cập và log.

### 7.2. Cấu hình DLQ như quarantine

Với Rabbit binder, có thể bật autoBindDlq nhưng không cấu hình dlqTtl và dlqDeadLetterExchange quay lại queue chính. Khi đó DLQ giữ message cho đến khi được xử lý hoặc dọn theo policy.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
~~~

republish-to-dlq=true yêu cầu binder publish message lỗi tới DLQ cùng metadata exception. Cấu hình này hữu ích để điều tra, nhưng cần xác minh hành vi theo version binder và publisher confirmation. Nếu muốn dùng broker dead-lettering nguyên bản, cấu hình republishToDlq=false và requeueRejected phù hợp.

### 7.3. Replay từ quarantine

Không nên replay toàn bộ quarantine queue một cách tự động ngay khi dependency phục hồi. Một quy trình replay an toàn:

1. Tìm message theo event ID, thời gian, loại lỗi hoặc aggregate.
2. Xác minh nguyên nhân đã được khắc phục.
3. Kiểm tra message có bị xử lý thành công ở nơi khác hay chưa.
4. Chọn một message hoặc một batch nhỏ để replay.
5. Publish lại với event ID gốc và correlation metadata.
6. Ghi lại người thực hiện, thời điểm và lý do replay.
7. Theo dõi consumer và kiểm tra kết quả nghiệp vụ.

Giữ event ID gốc giúp consumer idempotent nhận diện duplicate. Nếu replay tạo event ID mới, hệ thống có thể coi đó là một sự kiện nghiệp vụ hoàn toàn mới và áp dụng side effect lần nữa.

## 8. Binder republish và broker dead-letter khác nhau

Rabbit binder hỗ trợ hai cách đưa message lỗi vào DLQ:

| Cách | Cơ chế | Metadata |
|---|---|---|
| republishToDlq=true | Binder publish message sang DLQ sau khi retry hết | Có thể bổ sung exception message và stack trace |
| republishToDlq=false | Binder reject; broker dùng DLX để chuyển message | RabbitMQ quản lý x-death và dead-letter metadata |

Hai cách khác nhau về nơi thực hiện publish, header và semantics khi broker lỗi. Hãy chọn rõ ràng:

- Cần stack trace trong DLQ: cân nhắc republishToDlq=true.
- Muốn broker thực hiện dead-letter và dùng x-death cho TTL cycle: dùng cấu hình broker DLX phù hợp, thường là republishToDlq=false hoặc kiểm thử rõ đường đi khi binder republish.
- Cần đảm bảo chuyển message không mất: đánh giá dead-letter safety của queue nguồn, loại queue và broker version.

Không giả định binder republish và broker dead-letter có cùng semantics hoặc cùng xác nhận.

## 9. Độ tin cậy của TTL/DLX retry

TTL/DLX retry rất tiện, nhưng dead-lettering mặc định của RabbitMQ có thể là at-most-once trong một số cấu hình. Điều đó có nghĩa message được chuyển khỏi queue nguồn và có thể không tới queue đích nếu publish nội bộ thất bại trong điều kiện broker không bảo đảm retry chuyển tiếp.

### 9.1. Quorum queue và at-least-once dead-lettering

Quorum queue hỗ trợ at-least-once dead-lettering với điều kiện cấu hình cụ thể, bao gồm:

- dead-letter-strategy đặt thành at-least-once.
- overflow đặt thành reject-publish.
- Queue có dead-letter-exchange.
- Các feature flag và yêu cầu phiên bản broker được đáp ứng.

Ở chế độ này, quorum queue giữ message dead-letter cho tới khi queue đích xác nhận. Điều này tăng độ tin cậy nhưng có thể tạo duplicate ở đích nếu confirm bị mất và broker gửi lại.

### 9.2. Retry trên quorum queue

Các phiên bản RabbitMQ mới có hỗ trợ delayed retry native cho quorum queue. Cơ chế này có thể tránh một số chi phí và rủi ro của vòng lặp dead-letter qua TTL queue. Khi dùng quorum queue và broker version hỗ trợ, hãy đánh giá delayed retry native theo tài liệu RabbitMQ hiện hành.

TTL/DLX queue vẫn hữu ích cho topology classic queue, retry tiers tùy chỉnh hoặc môi trường cần cơ chế tương thích rộng. Cần xác định rõ guarantee mong muốn thay vì mặc định mọi DLX đều at-least-once.

### 9.3. Duplicate vẫn có thể xảy ra

Ngay cả khi broker giữ message an toàn, consumer vẫn có thể nhận lại message sau timeout, connection reset hoặc confirm không rõ kết quả. Consumer nên idempotent:

- Dùng eventId ổn định.
- Lưu processed event ID với unique constraint.
- Cập nhật dấu xử lý và dữ liệu nghiệp vụ trong cùng database transaction.
- Chỉ ack sau khi tác động nghiệp vụ được commit.

TTL/DLX không tạo exactly-once cho nghiệp vụ.

## 10. Thứ tự message và retry

Đưa message lỗi sang retry queue giúp queue chính tiếp tục xử lý message khác. Điều này tăng throughput nhưng có thể làm thay đổi thứ tự:

~~~text
Queue chính:
  OrderCreated        -> thành công
  PaymentAuthorized  -> lỗi, chuyển retry queue
  OrderShipped        -> thành công trước

Retry queue:
  PaymentAuthorized  -> chờ TTL -> quay lại queue chính
~~~

OrderShipped có thể được xử lý trước PaymentAuthorized. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo orderId, cần cân nhắc:

- Dùng binder retry blocking trên cùng consumer để giữ thứ tự, chấp nhận thread chờ.
- Pause partition/queue theo aggregate hoặc dùng cơ chế tuần tự hóa.
- Kiểm tra aggregate version ở consumer và từ chối xử lý sự kiện đến sai thứ tự.
- Dùng retry topic/queue riêng nhưng thiết kế consumer có thể xử lý out-of-order.

Không thể vừa tách message lỗi khỏi queue chính để xử lý các message sau ngay, vừa đảm bảo thứ tự tuyệt đối mà không có thêm cơ chế điều phối.

## 11. Kiểm thử retry queue và quarantine

Kiểm thử cần xác minh routing thực tế của broker, không chỉ kiểm tra cấu hình Spring đã được bind.

### 11.1. Kiểm thử TTL/DLX cycle

Với RabbitMQ test broker:

1. Khai báo exchange và queue chính.
2. Khởi động consumer binder với autoBindDlq=true và dlqTtl ngắn.
3. Gửi một message làm listener reject không requeue.
4. Xác minh message xuất hiện trong DLQ.
5. Xác minh message được giữ trong thời gian TTL.
6. Xác minh sau TTL message quay lại queue chính.
7. Xác minh x-death được cập nhật.

Dùng TTL ngắn trong test để giảm thời gian chạy; không dùng giá trị test làm cấu hình production mặc định.

### 11.2. Kiểm thử giới hạn retry

Gửi một poison message khiến listener luôn thất bại. Xác minh:

- Số chu kỳ retry được đếm đúng theo x-death hoặc metadata ứng dụng.
- Khi đạt ngưỡng, message chuyển sang quarantine.
- Message không tiếp tục quay về queue chính.
- Message hợp lệ khác vẫn được xử lý.

Kiểm tra x-death theo queue và reason cụ thể, vì danh sách có thể chứa nhiều mục và count có kiểu Long.

### 11.3. Kiểm thử quarantine và replay

- Xác minh quarantine queue không có TTL/DLX tự động quay lại queue chính.
- Tìm message theo event ID và kiểm tra metadata.
- Replay một message sau khi sửa lỗi.
- Gửi lại cùng event ID và xác minh consumer idempotent không áp dụng nghiệp vụ hai lần.
- Ghi lại kết quả replay và đảm bảo message gốc vẫn có thể được audit theo policy.

### 11.4. Kiểm thử lỗi broker

Giả lập queue đích hoặc exchange không tồn tại, broker restart hoặc publisher connection bị ngắt. Xác minh message không bị đánh dấu thành công chỉ vì listener đã ném exception. Với quorum queue, kiểm tra cấu hình at-least-once dead-lettering nếu yêu cầu không mất message trong quá trình chuyển.

## 12. Quan sát và vận hành

Theo dõi các chỉ số:

| Chỉ số | Mục đích |
|---|---|
| Main queue ready/unacked | Backlog và message đang xử lý |
| Retry queue depth | Số message đang chờ retry |
| Quarantine queue depth | Số message cần điều tra |
| Oldest retry age | Message chờ lâu nhất |
| x-death count distribution | Số chu kỳ retry |
| Retry success rate | Tỷ lệ xử lý thành công sau retry |
| DLQ publish failure | Lỗi khi chuyển message |
| Consumer exception rate | Lỗi listener |
| Redelivery rate | Dấu hiệu consumer crash hoặc reject |
| Publisher confirm/nack | Kết quả publish |

### 12.1. Cảnh báo

Cân nhắc cảnh báo khi:

- Retry queue tăng liên tục.
- Tuổi message chờ retry vượt SLA.
- Quarantine queue nhận message mới bất thường.
- Một event vượt ngưỡng retry.
- DLX/DLQ không có consumer hoặc binding.
- Publisher nack/return tăng.
- Main queue backlog tăng trong khi retry queue cũng tăng.

Không cảnh báo cho từng retry đơn lẻ nếu message cuối cùng xử lý thành công trong SLA. Hãy cảnh báo theo tỷ lệ, tuổi backlog và số lượng message bị cách ly.

### 12.2. Dọn dẹp và retention

Retry queue nên có TTL và giới hạn độ dài phù hợp. Quarantine queue nên có retention dài hơn để điều tra, nhưng không giữ dữ liệu vô hạn nếu có yêu cầu bảo vệ dữ liệu.

Không xóa quarantine queue khi còn message cần điều tra. Trước khi purge, export hoặc replay, cần xác nhận event ID, số lượng và phạm vi dữ liệu.

## 13. Những lỗi thường gặp

1. **Requeue ngay mọi exception**: tạo vòng lặp nóng và tăng CPU. Hãy chuyển lỗi tạm thời sang retry có backoff.
2. **Dùng TTL retry nhưng không có giới hạn lần thử**: poison message quay vòng vô hạn. Hãy đọc x-death và chuyển sang quarantine sau ngưỡng.
3. **Để dlqDeadLetterExchange trống do quên cấu hình**: message hết TTL không quay lại queue chính như dự kiến. Hãy khai báo default exchange bằng chuỗi rỗng và kiểm tra routing key.
4. **Nhầm DLQ với quarantine**: DLQ có TTL và DLX quay về queue chính thực chất là retry queue. Quarantine cần giữ message để điều tra.
5. **Bỏ qua binder retry đang bật**: mỗi lần vào DLQ có thể đã trải qua nhiều lần gọi listener. Hãy tính tổng retry.
6. **Không kiểm tra republishToDlq**: binder republish và broker dead-letter có header/semantics khác nhau. Hãy cấu hình tường minh.
7. **Đếm x-death bằng Integer**: count thường là Long. Hãy dùng Number và chọn đúng queue/reason.
8. **Cho retry queue và queue chính dùng routing key sai**: message có thể bị route tới queue khác hoặc không có queue nhận. Hãy kiểm thử topology.
9. **Tạo vòng dead-letter không có điều kiện dừng**: message có thể lặp mãi. Hãy dùng attempt limit và parking-lot queue.
10. **Coi DLX mặc định là at-least-once**: một số đường dead-letter có thể at-most-once. Hãy đánh giá queue type và cấu hình reliability.
11. **Replay với event ID mới**: consumer coi đó là event mới và tạo side effect trùng. Hãy giữ event ID gốc.
12. **Không xem xét thứ tự**: message sau có thể được xử lý trước message đang chờ retry. Hãy xác định phạm vi thứ tự nghiệp vụ.
13. **Không giám sát quarantine**: message lỗi bị bỏ quên. Hãy theo dõi oldest message và quy trình xử lý.

## 14. Quy trình thiết kế retry và quarantine

Khi xây dựng độ tin cậy cho RabbitMQ binder:

1. Phân loại lỗi tạm thời, lỗi dữ liệu và lỗi cấu hình.
2. Chọn retry trong binder hay retry qua TTL/DLX theo yêu cầu thứ tự và độ trễ.
3. Nếu dùng TTL/DLX, bật autoBindDlq và cấu hình dlqTtl.
4. Cấu hình dlqDeadLetterExchange là default exchange nếu muốn quay lại queue chính.
5. Xác minh deadLetterRoutingKey trỏ tới tên queue chính.
6. Đặt max-attempts phù hợp và tính tổng số lần thử qua các tầng.
7. Đọc x-death hoặc retry metadata để giới hạn vòng lặp.
8. Tạo quarantine/parking-lot queue không tự động route lại.
9. Giữ event ID, correlation ID và exception metadata.
10. Xác định republishToDlq và dead-letter guarantee theo broker version.
11. Thiết kế idempotent consumer và quy trình replay có kiểm soát.
12. Kiểm thử TTL expiry, DLX routing, retry limit, quarantine, broker outage và thứ tự.
13. Thiết lập dashboard, cảnh báo, retention và runbook vận hành.

## Kết luận

TTL retry queue kết hợp DLX cho phép RabbitMQ giữ message lỗi trong một khoảng thời gian rồi định tuyến trở lại queue chính. Với Spring Cloud Stream RabbitMQ binder, có thể dùng autoBindDlq, dlqTtl và dlqDeadLetterExchange để triển khai một vòng retry cơ bản. Cần hiểu queue chính có tên destination.group, default exchange dùng routing key là tên queue, và x-death cung cấp metadata để giới hạn số chu kỳ.

Retry queue không phải quarantine queue. Retry queue tự động phát lại sau thời gian chờ; quarantine giữ message lỗi để điều tra và replay có chủ đích. Một thiết kế tin cậy cần giới hạn số lần thử, phân biệt binder republish với broker dead-lettering, đánh giá at-least-once/at-most-once transfer, giữ event ID ổn định và làm consumer idempotent. Khi yêu cầu reliability cao, cần kiểm thử routing và failure trên broker thực tế thay vì chỉ dựa vào cấu hình ứng dụng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Retry With the RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-retry.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Quorum Queues and Delayed Retry](https://www.rabbitmq.com/docs/quorum-queues)
