# Cấu hình maxAttempts và các khoảng chờ backoff

Khi consumer nhận một message và xử lý thất bại, thử lại có thể giúp phục hồi những lỗi tạm thời như timeout ngắn, kết nối database gián đoạn hoặc dịch vụ phụ thuộc đang khởi động lại. Spring Cloud Stream cung cấp các thuộc tính consumer để giới hạn số lần thử và điều khiển khoảng chờ giữa các lần thử. Hai nhóm cấu hình quan trọng là `maxAttempts` và các thuộc tính backoff.

`maxAttempts` xác định tổng số lần thực thi, bao gồm lần đầu tiên. `backOffInitialInterval`, `backOffMaxInterval` và `backOffMultiplier` xác định khoảng nghỉ giữa các lần retry. Cấu hình hợp lý giúp tránh gọi liên tục một dependency đang lỗi, đồng thời giới hạn thời gian một message bị giữ trong quá trình xử lý.

Bài thuộc chương **Xử lý lỗi** của module `SPRING_CLOUD_STREAM`. Nội dung đặt các thuộc tính này trong consumer binding của mô hình hàm `Supplier`/`Function`/`Consumer`, đồng thời giải thích cách retry liên quan đến binder, Kafka, RabbitMQ, Pulsar, DLQ và bảo đảm giao nhận.

## 1. Vòng đời một lần xử lý message

Khi một message đến consumer, framework gọi handler hoặc function để xử lý. Nếu xử lý hoàn tất thành công, message đi theo cơ chế xác nhận/commit của binder. Nếu handler ném lỗi, framework có thể thử lại theo chính sách consumer trước khi chuyển lỗi đến cơ chế xử lý cuối cùng.

```text
Broker giao message
       |
       v
Consumer handler / function
       |
       +---- thành công ----> hoàn tất theo ack/commit của binder
       |
       +---- thất bại
                |
                v
        Còn lượt thử không?
           /        \
         Có          Không
         |             |
         v             v
   Chờ backoff     Error handling
         |          / DLQ / reject
         v
   Thử lại handler
```

Retry là một phần của quá trình xử lý message, không phải bảo đảm rằng message sẽ được xử lý thành công. Nếu mọi lần thử đều thất bại, ứng dụng cần một chính sách tiếp theo: gửi message đến dead-letter queue/topic, chuyển vào luồng cách ly, ghi nhận lỗi để xử lý thủ công hoặc để binder/broker áp dụng hành vi tương ứng.

## 2. `maxAttempts` được tính như thế nào?

`maxAttempts` là tổng số lần gọi handler cho cùng một message trong một chu kỳ retry. Giá trị bao gồm lần xử lý ban đầu, không chỉ số lần thử lại sau lỗi.

| `maxAttempts` | Lần xử lý ban đầu | Số lần retry tối đa |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 5 | 1 | 4 |
| 6 | 1 | 5 |

Ví dụ `maxAttempts: 5` có nghĩa handler được gọi tối đa năm lần: lần đầu và tối đa bốn lần retry nếu các lần trước thất bại. Nếu lần thứ hai thành công, framework dừng retry ngay; không cần thực hiện đủ năm lần.

Giá trị `1` tắt retry ở tầng consumer vì chỉ còn lần xử lý ban đầu. Đây là lựa chọn phù hợp khi muốn fail nhanh hoặc đã có một cơ chế retry khác được kiểm soát ở tầng nghiệp vụ.

Trong Spring Cloud Stream, cấu hình mặc định thường là ba lần thử. Khi cần hành vi rõ ràng giữa các môi trường, nên khai báo `maxAttempts` tường minh thay vì phụ thuộc vào mặc định của phiên bản framework đang dùng.

## 3. Cấu hình retry cho một consumer binding

Các thuộc tính retry được đặt trong `consumer` của binding đầu vào. Ví dụ một hàm xử lý đơn hàng đọc từ destination `orders.created`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          content-type: application/json
          consumer:
            max-attempts: 5
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
```

Ý nghĩa:

- `processOrder-in-0` là binding đầu vào của hàm `processOrder`.
- `max-attempts: 5` cho phép tối đa năm lần xử lý message.
- `back-off-initial-interval: 1000` đặt khoảng chờ đầu tiên là 1.000 mili giây.
- `back-off-max-interval: 10000` giới hạn khoảng chờ tối đa là 10.000 mili giây.
- `back-off-multiplier: 2.0` nhân đôi khoảng chờ sau mỗi lần retry, cho đến khi chạm giới hạn tối đa.

Các thuộc tính này nằm trong consumer binding. Nếu ứng dụng có nhiều input binding, có thể đặt chính sách khác nhau cho từng binding theo độ quan trọng, đặc điểm lỗi và SLA của luồng message.

## 4. Ba thuộc tính backoff

### `backOffInitialInterval`

Đây là khoảng nghỉ trước lần retry đầu tiên, tính bằng mili giây. Giá trị quá nhỏ có thể khiến consumer gọi lại dependency ngay khi dịch vụ chưa kịp phục hồi. Giá trị quá lớn làm tăng độ trễ của message ngay cả khi lỗi chỉ tồn tại trong thời gian ngắn.

Ví dụ `1000` tương đương một giây chờ trước lần retry đầu tiên.

### `backOffMultiplier`

Đây là hệ số nhân khoảng nghỉ sau mỗi lần retry. Với multiplier `2.0`, khoảng nghỉ tăng gấp đôi theo cấp số nhân. Với multiplier `1.0`, các khoảng nghỉ giữ nguyên, tương đương fixed backoff.

Multiplier lớn làm các lần thử về sau thưa hơn. Điều này giảm áp lực lên dependency đang lỗi nhưng có thể kéo dài thời gian hoàn tất một message.

### `backOffMaxInterval`

Đây là giới hạn trên của khoảng nghỉ. Dù phép nhân tiếp tục làm khoảng nghỉ tăng, framework không chờ lâu hơn giá trị này cho một lần retry.

Giới hạn trên giúp thời gian chờ có thể dự đoán được và tránh một message bị giữ quá lâu chỉ vì backoff tăng không giới hạn.

## 5. Fixed backoff và exponential backoff

Fixed backoff giữ nguyên khoảng nghỉ giữa các lần retry. Exponential backoff tăng khoảng nghỉ sau mỗi lần thất bại.

| Lần retry | Fixed 2 giây | Exponential: 1 giây, multiplier 2, max 10 giây |
|---:|---:|---:|
| 1 | 2 giây | 1 giây |
| 2 | 2 giây | 2 giây |
| 3 | 2 giây | 4 giây |
| 4 | 2 giây | 8 giây |
| 5 | 2 giây | 10 giây |
| 6 | 2 giây | 10 giây |

Exponential backoff phù hợp khi dependency có thể cần thêm thời gian để phục hồi. Fixed backoff phù hợp khi muốn nhịp retry ổn định và lỗi thường được giải quyết trong một khoảng thời gian tương đối cố định.

## 6. Tính khoảng chờ và tổng thời gian retry

Với exponential backoff, khoảng nghỉ ở lần retry thứ (n) có thể hình dung bằng:

\[
  d_n = \min(d_0 \times m^{n-1}, d_{max})
\]

Trong đó:

- (d_0) là `backOffInitialInterval`.
- (m) là `backOffMultiplier`.
- (d_{max}) là `backOffMaxInterval`.
- (n) bắt đầu từ 1 cho lần retry đầu tiên.

Ví dụ `maxAttempts: 5`, initial interval 1 giây, multiplier 2 và max interval 10 giây:

| Lượt xử lý | Hành động | Khoảng chờ trước lượt |
|---:|---|---:|
| 1 | Xử lý ban đầu | 0 |
| 2 | Retry lần 1 | 1 giây |
| 3 | Retry lần 2 | 2 giây |
| 4 | Retry lần 3 | 4 giây |
| 5 | Retry lần 4 | 8 giây |

Tổng thời gian chờ backoff tối đa là 15 giây nếu cả bốn lần retry đều diễn ra. Thời gian thực tế còn bao gồm thời gian chạy handler ở từng lượt, thời gian gọi dependency, scheduling và chi phí giao nhận của binder. Vì vậy, không thể dùng tổng backoff làm thời gian xử lý tối đa của message.

Nếu mỗi lần handler có thể chạy 3 giây, năm lượt xử lý có thể thêm tối đa khoảng 15 giây thời gian thực thi, chưa tính backoff. Cần đặt timeout và SLA phù hợp với tổng ngân sách này.

## 7. Chọn `maxAttempts` theo loại lỗi

Không phải exception nào cũng nên retry. Lỗi tạm thời có khả năng tự phục hồi; lỗi cố định thường cần sửa dữ liệu, quyền hoặc code trước khi xử lý lại.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout ngắn, connection reset, HTTP 503 | Retry có giới hạn và backoff |
| Quá tải | HTTP 429, pool connection cạn | Retry có backoff, tôn trọng `Retry-After` nếu tầng gọi hỗ trợ |
| Lỗi dữ liệu | JSON sai, trường bắt buộc thiếu, enum không hợp lệ | Không retry liên tục; cách ly hoặc DLQ |
| Lỗi nghiệp vụ | Đơn hàng không đủ điều kiện, tồn kho không đủ | Trả kết quả nghiệp vụ hoặc chuyển luồng xử lý tương ứng |
| Lỗi cấu hình/quyền | Sai credentials, không có quyền đọc destination | Không retry dài; sửa cấu hình hoặc quyền |
| Lỗi lập trình | Null dereference, invariant bị vi phạm | Thường không retry; ghi nhận và điều tra |

Spring Cloud Stream cho phép phân loại exception có thể retry thông qua cấu hình `retryableExceptions` và `defaultRetryable` ở consumer properties trong các phiên bản hỗ trợ. Có thể dùng cách này để chỉ retry một số lỗi tạm thời và loại trừ lỗi dữ liệu hoặc nghiệp vụ. Hãy xác nhận tên thuộc tính và cách binder áp dụng với phiên bản dependency của ứng dụng.

Ví dụ cấu hình theo hướng allowlist:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 4
            default-retryable: false
            retryable-exceptions:
              com.example.TransientInventoryException: true
              com.example.RemoteServiceUnavailableException: true
              com.example.InvalidOrderException: false
```

Với chính sách trên, các lỗi chưa được liệt kê mặc định không retry; hai lỗi phụ thuộc tạm thời được retry và lỗi dữ liệu đơn hàng bị loại khỏi retry. Nếu ứng dụng dùng phiên bản không hỗ trợ các thuộc tính này hoặc binder có cách xử lý riêng, cần cấu hình phân loại ở tầng handler hoặc error infrastructure tương ứng.

## 8. Cấu hình khác nhau theo từng binding

Một ứng dụng có thể có nhiều consumer với yêu cầu độ trễ và khả năng phục hồi khác nhau. Không nhất thiết dùng cùng `maxAttempts` cho mọi luồng.

```yaml
spring:
  cloud:
    function:
      definition: processPayment;updateMetrics
    stream:
      bindings:
        processPayment-in-0:
          destination: payments.requested
          group: payment-service
          consumer:
            max-attempts: 5
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
        updateMetrics-in-0:
          destination: orders.events
          group: metrics-service
          consumer:
            max-attempts: 2
            back-off-initial-interval: 250
            back-off-max-interval: 1000
            back-off-multiplier: 1.5
```

Luồng thanh toán có thể cần retry lâu hơn vì dependency có thể tạm thời gián đoạn; luồng metric có thể ưu tiên hoàn tất nhanh hoặc chuyển lỗi sang xử lý sau. Các con số trong ví dụ chỉ minh họa; cần dựa vào SLA, thời gian timeout, khả năng broker và tính idempotent của handler.

Đặt retry theo binding giúp từng luồng có ngân sách riêng, nhưng không nên làm chính sách quá phức tạp khiến vận hành khó hiểu. Hãy ghi lại lý do cho từng chính sách và theo dõi tỷ lệ retry thực tế.

## 9. Điều gì xảy ra sau khi hết `maxAttempts`?

Khi tất cả lượt xử lý đều thất bại, framework chuyển lỗi sang cơ chế error handling tương ứng. Hành vi cuối cùng phụ thuộc binder và cấu hình:

- Có thể phát lỗi lên error channel hoặc error handler.
- Có thể gửi message đến dead-letter destination nếu binder được cấu hình DLQ.
- Có thể reject, requeue hoặc để broker giao lại tùy semantics của binder.
- Có thể làm listener/container hoặc luồng xử lý báo lỗi và được nền tảng phục hồi.

`maxAttempts` chỉ giới hạn số lần retry ở tầng consumer; nó không tự bật DLQ và không quyết định mọi hành vi sau retry. Muốn message lỗi được lưu lại để điều tra, cần cấu hình dead-letter handling phù hợp.

### Kafka

Kafka binder có thể hỗ trợ DLQ cho consumer binding thông qua cấu hình binder như `enableDlq` và tên DLQ. Khi bật, message lỗi sau khi hết retry có thể được publish sang dead-letter topic theo cơ chế của binder. Cần cấu hình quyền ghi topic DLQ, số partition và chiến lược key/partition phù hợp. Kafka không có khái niệm queue requeue theo cách RabbitMQ thực hiện; consumer group offset và việc publish DLQ cần được hiểu theo semantics Kafka.

### RabbitMQ

Rabbit binder có thể cấu hình dead-letter exchange/queue và các tùy chọn tự khai báo topology. Khi retry của framework hết giới hạn, binder có thể reject hoặc republish message theo cấu hình DLQ. Cần phân biệt retry trong ứng dụng với requeue của broker; requeue không giới hạn có thể tạo vòng lặp nóng.

### Pulsar

Pulsar có dead-letter policy và retry-letter topic tùy subscription/binder hỗ trợ. Cần kiểm tra cách binder ánh xạ `maxAttempts` với cơ chế retry của Pulsar và cách cấu hình dead-letter policy trong phiên bản đang dùng. Không giả định thuộc tính Kafka hoặc Rabbit binder áp dụng trực tiếp cho Pulsar.

## 10. Phân biệt retry binder với retry trong code

Consumer retry ở tầng Spring Cloud Stream và retry trong code giải quyết những phạm vi khác nhau:

| Cơ chế | Phạm vi | Ví dụ |
|---|---|---|
| `maxAttempts` và backoff của consumer | Lần gọi handler/function ở ranh giới binding theo khả năng framework/binder | Consumer ném exception khi xử lý message |
| Reactor `retryWhen` | Một publisher hoặc thao tác bên trong reactive pipeline | Gọi lại API tồn kho khi timeout |
| Broker redelivery | Giao lại message theo trạng thái acknowledgement/offset của broker | Message chưa được ack hoặc commit |
| Retry destination | Chuyển message sang topic/queue retry để xử lý sau | Thử lại sau 1 phút hoặc theo lịch |

Không nên vô tình lồng nhiều tầng retry. Ví dụ consumer `maxAttempts: 4` và mỗi lần handler lại gọi một API với ba lần retry trong Reactor. Dependency có thể bị gọi tối đa mười hai lần cho một lần giao message ban đầu, chưa tính broker redelivery. Nếu broker còn giao lại hai lần, số lần gọi có thể tăng hơn nữa.

Hãy xác định một tầng chịu trách nhiệm retry chính cho từng lỗi. Dùng retry nội bộ cho dependency cụ thể; dùng binder/broker retry cho việc xử lý message ở ranh giới consumer; dùng retry topic/queue khi cần trì hoãn dài hoặc tách luồng retry khỏi luồng chính.

## 11. Retry có thể ảnh hưởng thứ tự và throughput

Trong Kafka, nếu handler của một partition đang retry đồng bộ, các record phía sau cùng partition có thể bị chậm lại tùy cách binder và container xử lý. Trong RabbitMQ, một message bị requeue có thể được giao lại và thứ tự quan sát có thể thay đổi khi có nhiều consumer. Trong Pulsar, retry và subscription type ảnh hưởng cách message được phân phối lại.

Retry dài có thể làm giảm throughput và tăng consumer lag hoặc backlog. Với một message độc hại hoặc luôn lỗi, việc retry tại chỗ quá lâu có thể chặn các message khác. Cần cân nhắc:

- Retry tại chỗ để giữ luồng và giới hạn việc bỏ qua message lỗi.
- Retry topic/queue để trì hoãn và cho phép message mới tiếp tục.
- DLQ để cách ly message không thể xử lý tự động.
- Partition key hoặc ordering key để giữ thứ tự theo aggregate.
- Concurrency và số partition/queue/subscription để đáp ứng tải.

Không tăng `maxAttempts` chỉ để giảm số message vào DLQ. Nếu lỗi là dữ liệu sai, nhiều lần retry không làm dữ liệu trở nên hợp lệ.

## 12. Tính ngân sách thời gian xử lý

Khi đặt retry, hãy tính cả thời gian xử lý và khoảng chờ. Giả sử:

- `maxAttempts = 5`.
- Mỗi lần xử lý có timeout tối đa 2 giây.
- Backoff là 0,5 giây, 1 giây, 2 giây và 4 giây.

Thời gian tối đa xấp xỉ nếu tất cả lần xử lý đều chạy hết timeout:

\[
T \approx 5 \times 2 + (0.5 + 1 + 2 + 4) = 17.5\text{ giây}
\]

Con số này chưa tính thời gian scheduling, broker, serialization và DLQ. Nếu nền tảng có timeout shutdown hoặc rebalance ngắn hơn, consumer có thể bị dừng giữa chu kỳ retry. Hãy đồng bộ timeout handler, timeout dependency, thời gian chờ backoff, thời gian shutdown và chính sách triển khai.

Nếu message có deadline nghiệp vụ 10 giây, chính sách retry tối đa 17,5 giây là không phù hợp. Có thể giảm số lần thử, giảm timeout từng lần, chuyển retry sang topic trì hoãn hoặc ghi nhận trạng thái chờ xử lý sau.

## 13. Idempotency khi handler được gọi nhiều lần

Retry có thể khiến cùng một message được xử lý nhiều lần. Một tình huống phổ biến:

1. Consumer nhận `PaymentRequested`.
2. Dịch vụ thanh toán đã tạo giao dịch.
3. Phản hồi bị timeout trước khi consumer nhận kết quả.
4. Consumer retry và gửi yêu cầu thanh toán lần nữa.

Nếu API không hỗ trợ idempotency, khách hàng có thể bị trừ tiền hai lần. Do đó, handler cần dùng event ID hoặc idempotency key ổn định qua mọi lần thử:

```java
Mono<PaymentResult> authorize(PaymentRequested event) {
    return paymentClient.authorize(
        event.orderId(),
        event.eventId()
    );
}
```

Nếu cập nhật database, có thể dùng inbox table với unique constraint trên `event_id` và ghi dấu xử lý cùng transaction với thay đổi nghiệp vụ. Nếu publish event sau khi commit database, transactional outbox giúp không mất sự kiện giữa hai thao tác. `maxAttempts` không cung cấp exactly-once; idempotency và transaction boundary mới quyết định tác động của xử lý lặp.

## 14. Retry của function reactive

Với function reactive như `Function<Flux<Event>, Flux<Result>>`, framework nhận một publisher thay vì gọi một handler imperative độc lập cho mỗi message. Vì vậy, không nên giả định `maxAttempts` và backoff của consumer sẽ tự retry từng phần tử trong `Flux` giống hệt consumer imperative.

Nếu cần retry một thao tác reactive, hãy đặt chính sách Reactor quanh publisher của thao tác đó:

```java
Flux<Result> results = events.flatMap(event ->
    Mono.defer(() -> service.process(event))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientFailure)
        )
        .onErrorResume(error -> recoverOne(event, error))
);
```

Đặt retry bên trong publisher của từng event để cô lập lỗi theo message. Nếu đặt `onErrorResume` bên ngoài toàn `Flux`, một lỗi có thể kết thúc publisher đầu vào và fallback thay thế phần còn lại của stream. Cần kiểm thử semantics reactive binding và acknowledgement của binder đang dùng.

## 15. Kiểm thử maxAttempts và backoff

Kiểm thử cần xác nhận số lần gọi, khoảng chờ, loại exception được retry và hành vi khi hết lượt:

| Kịch bản | Cách mô phỏng | Điều cần xác minh |
|---|---|---|
| Thành công lần đầu | Handler trả kết quả ngay | Chỉ có một lần gọi, không chờ backoff |
| Thành công sau một lỗi | Lần đầu ném exception, lần sau thành công | Handler được gọi lại đúng một lần |
| Hết lượt retry | Mọi lần gọi đều ném lỗi retryable | Tổng số lần gọi bằng `maxAttempts` |
| Lỗi không retry | Handler ném exception bị phân loại non-retryable | Chỉ gọi một lần rồi chuyển error handling |
| Backoff cố định | Đặt multiplier bằng 1 | Khoảng chờ giữa các lần retry không đổi |
| Exponential backoff | Multiplier lớn hơn 1 | Khoảng chờ tăng nhưng không vượt max interval |
| DLQ | Cấu hình binder DLQ và làm handler luôn lỗi | Message được chuyển đến DLQ theo binder |
| Broker restart | Ngắt broker trong lúc consumer chạy | Phân biệt reconnect của client với retry handler |
| Duplicate side effect | Giả lập timeout sau khi thao tác đã commit | Idempotency ngăn tác động lặp |

Unit test có thể dùng clock/scheduler hoặc retry policy được trích thành bean để kiểm tra mà không phải chờ thời gian dài. Integration test cần dùng binder test hoặc broker phù hợp để xác nhận số lần handler được gọi và hành vi ack/DLQ thực tế.

Không chỉ kiểm tra số lần retry trong code. Cần kiểm tra cả trường hợp message được giao lại bởi broker sau khi consumer restart, vì đây là một tầng khác với retry của handler.

## 16. Quan sát retry trong production

Các metric và log nên giúp trả lời:

- Bao nhiêu message được xử lý ngay lần đầu?
- Bao nhiêu message cần một hoặc nhiều lần retry?
- Số lần thử trung bình và phân bố số lần thử là bao nhiêu?
- Loại exception nào thường gây retry?
- Tổng thời gian message nằm trong retry là bao lâu?
- Có bao nhiêu message hết `maxAttempts` và đi vào DLQ?
- Consumer lag/backlog thay đổi ra sao trong lúc dependency gặp sự cố?
- Có dấu hiệu nhiều tầng retry lồng nhau hoặc retry storm không?

Log nên có `eventId`, binding name, exception class, attempt number, thời điểm retry tiếp theo và destination DLQ nếu có. Tránh ghi toàn bộ payload hoặc thông tin bí mật. Metric label nên giới hạn theo binding, loại lỗi và dependency; không dùng event ID hoặc tenant tùy ý làm label có cardinality cao.

## 17. Quy trình chọn maxAttempts và backoff

Khi cấu hình một consumer:

1. Xác định lỗi nào có thể tự phục hồi và lỗi nào cần xử lý ngay.
2. Chọn `maxAttempts` theo ngân sách thời gian và khả năng lặp an toàn của thao tác.
3. Chọn `backOffInitialInterval` theo thời gian phục hồi thường gặp của dependency.
4. Chọn `backOffMultiplier` để giảm tần suất gọi khi lỗi kéo dài.
5. Chọn `backOffMaxInterval` để giới hạn độ trễ tối đa giữa hai lần thử.
6. Cấu hình phân loại exception để không retry lỗi dữ liệu hoặc quyền.
7. Xác định hành vi sau khi hết lượt: DLQ, error channel, reject hoặc quy trình nghiệp vụ.
8. Tính tổng thời gian xử lý và đồng bộ với timeout/SLA/shutdown của nền tảng.
9. Kiểm tra idempotency, transaction và khả năng xử lý message trùng.
10. Kiểm thử với binder thật hoặc môi trường tương thích, gồm redelivery và DLQ.
11. Theo dõi retry rate, backlog, độ trễ và số message hết lượt trong production.

## 18. Tự kiểm tra

- [ ] Giải thích được `maxAttempts` bao gồm cả lần xử lý ban đầu.
- [ ] Tính được số lần retry tối đa từ `maxAttempts`.
- [ ] Phân biệt `backOffInitialInterval`, `backOffMultiplier` và `backOffMaxInterval`.
- [ ] Tính được lịch exponential backoff và tổng thời gian chờ.
- [ ] Cấu hình được retry riêng cho từng consumer binding.
- [ ] Phân biệt lỗi retryable và non-retryable.
- [ ] Biết rằng hết `maxAttempts` không tự động có nghĩa message được gửi vào DLQ.
- [ ] Phân biệt retry của binder, Reactor retry và broker redelivery.
- [ ] Nhận diện nguy cơ retry lồng nhau và tác dụng phụ bị lặp.
- [ ] Thiết kế được kiểm thử số lần gọi, backoff, DLQ và idempotency.

## Kết luận

`maxAttempts` giới hạn tổng số lần xử lý một message, bao gồm lần đầu; các thuộc tính backoff điều khiển khoảng nghỉ giữa những lần retry. `backOffInitialInterval` đặt khoảng chờ đầu, `backOffMultiplier` điều khiển tốc độ tăng và `backOffMaxInterval` giới hạn khoảng nghỉ. Hãy retry những lỗi có khả năng phục hồi, giới hạn ngân sách thời gian, bảo đảm handler idempotent và xác định rõ hành vi sau khi hết lượt. Retry của consumer, retry trong Reactor và redelivery của broker là các tầng khác nhau; cấu hình và kiểm thử riêng từng tầng giúp tránh retry storm, message trùng và độ trễ không kiểm soát.
