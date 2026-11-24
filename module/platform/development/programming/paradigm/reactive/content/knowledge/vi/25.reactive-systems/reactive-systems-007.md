# Bão thử lại, giới hạn thử lại và tính lũy đẳng

Khi một dịch vụ phụ thuộc vào database, message broker hoặc API từ xa, lỗi tạm thời có thể xuất hiện do timeout, mất kết nối, giới hạn tốc độ hoặc một node đang khởi động lại. Thử lại (*retry*) giúp một thao tác có cơ hội thành công sau khi sự cố ngắn hạn qua đi. Nhưng nếu nhiều client cùng thử lại ngay lập tức, tải lên dịch vụ đang gặp sự cố sẽ tăng thêm. Hiện tượng đó có thể tạo thành **bão thử lại** (*retry storm*), làm sự cố nhỏ lan thành gián đoạn diện rộng.

Một chính sách retry an toàn cần trả lời bốn câu hỏi: lỗi nào có thể thử lại, thử tối đa bao nhiêu lần, chờ bao lâu giữa các lần thử và làm thế nào để thao tác lặp không tạo side effect trùng. Trong Reactor, `retryWhen` kết hợp với `Retry` giúp biểu diễn chính sách thử lại ngay trong pipeline `Mono` hoặc `Flux`. Tính lũy đẳng (*idempotency*) ở tầng nghiệp vụ và lưu trữ bảo vệ hệ thống khi kết quả lần gọi trước không rõ ràng.

Bài học thuộc chương **Hệ thống phản ứng** của module `REACTIVE_PROGRAMMING`, tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java.

## 1. Retry thực sự làm gì?

Trong Reactor, retry không tiếp tục từ đúng vị trí đã lỗi. Khi nhận `onError`, operator retry đăng ký lại publisher upstream. Với một publisher cold được tạo theo subscription, thao tác nguồn thường được thực thi lại từ đầu.

```java
Mono<Profile> profile = profileClient.findById(profileId)
    .retry(2);
```

Nếu lần gọi đầu tiên lỗi, `retry(2)` cho phép đăng ký lại tối đa hai lần. Tổng số lần thực thi có thể là ba: một lần ban đầu và hai lần retry. Nếu nguồn hoàn tất bình thường, retry không làm gì. Nếu nguồn phát lỗi sau khi đã phát một số phần tử, subscription mới có thể bắt đầu lại luồng và phát lại những phần tử trước đó.

Điều này có hệ quả quan trọng với `Flux`: downstream có thể đã nhận một phần dữ liệu trước khi lỗi xảy ra. Khi retry đăng ký lại nguồn, những phần tử đó có thể xuất hiện lần nữa. Vì vậy, retry một luồng không đồng nghĩa với việc tiếp tục chính xác từ phần tử bị lỗi. Muốn tiếp tục từ checkpoint, ứng dụng phải lưu vị trí đã xử lý và tạo nguồn mới bắt đầu sau checkpoint đó.

### Phân biệt số lần thử và số lần retry

| Cấu hình | Số lần retry tối đa | Tổng số lần thử tối đa |
|---|---:|---:|
| Không retry | 0 | 1 |
| `retry(1)` | 1 | 2 |
| `retry(2)` | 2 | 3 |
| `retry(3)` | 3 | 4 |

Khi đặt tên cấu hình hoặc metric, hãy phân biệt `attempt` (một lần thực thi) với `retry` (một lần đăng ký lại). Cách gọi không rõ ràng dễ khiến giới hạn thực tế bị tính sai.

## 2. Không phải lỗi nào cũng nên retry

Retry chỉ hữu ích khi có khả năng lần thực thi tiếp theo thành công và việc thực thi lặp là an toàn. Một lỗi xác thực hoặc dữ liệu sai thường không tự biến mất sau 200 mili giây. Retry các lỗi đó chỉ tạo thêm tải và trì hoãn phản hồi cho caller.

Có thể phân loại lỗi theo hướng sau:

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Tạm thời ở tầng kết nối | Connection reset, lỗi DNS thoáng qua, node vừa khởi động lại. | Có thể retry có giới hạn và backoff. |
| Quá tải hoặc giới hạn tốc độ | HTTP 429, một số phản hồi 503. | Tuân thủ `Retry-After` nếu có, giảm concurrency và retry có giới hạn. |
| Timeout với kết quả không rõ | Client hết thời gian chờ nhưng server có thể đã thực hiện thao tác. | Chỉ retry khi thao tác có tính lũy đẳng hoặc có idempotency key. |
| Lỗi xác thực/phân quyền | HTTP 401 hoặc 403, token không hợp lệ. | Làm mới thông tin xác thực theo chính sách; không retry mù quáng. |
| Lỗi dữ liệu/nghiệp vụ | Validation failure, trạng thái chuyển đổi không hợp lệ. | Trả lỗi hoặc xử lý theo quy tắc nghiệp vụ. |
| Vi phạm constraint | Unique constraint, foreign key, dữ liệu không hợp lệ. | Thường không retry cùng payload; cần sửa dữ liệu hoặc xử lý xung đột. |

Phân loại cần dựa trên loại exception, mã phản hồi và ngữ cảnh thao tác. Không nên retry mọi `RuntimeException` hoặc mọi `WebClientResponseException` bằng một predicate chung.

### Chỉ retry lỗi được xác định là tạm thời

```java
boolean isTransient(Throwable error) {
    return error instanceof IOException
        || error instanceof TimeoutException
        || error instanceof ServiceUnavailableException;
}

Mono<Inventory> loadInventory(String sku) {
    return inventoryClient.fetch(sku)
        .retryWhen(Retry.max(2).filter(this::isTransient));
}
```

Ví dụ chỉ minh họa cách lọc loại lỗi. Trong ứng dụng thật, cần xem xét exception cụ thể của HTTP client, database driver hoặc broker. Một `IOException` có thể là lỗi tạm thời, nhưng cũng có thể biểu thị một điều kiện không thể phục hồi. Predicate nên phản ánh hợp đồng của dependency.

## 3. Giới hạn retry để tránh vòng lặp vô hạn

Retry không giới hạn có thể giữ request sống quá lâu, chiếm tài nguyên và làm dependency bị lỗi tiếp tục chịu tải. Với request tương tác, hãy đặt số lần retry tối đa và deadline tổng cho thao tác.

`Retry.max(n)` giới hạn số lần retry sau lần thực thi đầu tiên:

```java
Mono<Quote> quote = quoteClient.fetch(symbol)
    .retryWhen(Retry.max(2));
```

`Retry.fixedDelay(n, delay)` chờ một khoảng cố định giữa các lần retry:

```java
Mono<Quote> quote = quoteClient.fetch(symbol)
    .retryWhen(Retry.fixedDelay(
        3,
        Duration.ofMillis(250)
    ));
```

Fixed delay đơn giản nhưng nhiều client có thể retry cùng thời điểm. Khi có hàng nghìn request cùng thất bại, các lần thử lại sẽ tạo thành những đợt tải đồng bộ. Đối với hệ thống phân tán, exponential backoff kết hợp jitter thường phù hợp hơn.

### Tổng thời gian chờ cũng cần giới hạn

Giả sử mỗi lần gọi có timeout 1 giây và chính sách cho phép ba lần retry. Chỉ riêng thời gian chờ thực thi có thể lên đến khoảng bốn giây, chưa tính backoff, lập lịch và thời gian xử lý khác. Nếu caller chỉ cho phép request tồn tại trong hai giây, chính sách đó không phù hợp.

Có thể đặt timeout cho từng lần gọi và một timeout tổng cho toàn bộ chuỗi retry:

```java
Mono<Quote> quote = Mono.defer(() ->
        quoteClient.fetch(symbol)
            .timeout(Duration.ofSeconds(1))
    )
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .maxBackoff(Duration.ofMillis(500))
        .filter(this::isTransient))
    .timeout(Duration.ofSeconds(2));
```

Timeout nằm bên trong `defer` áp dụng cho từng lần gọi nguồn. Timeout bên ngoài giới hạn toàn bộ thời gian mà caller chờ chuỗi retry. Khi timeout tổng xảy ra, downstream nhận lỗi và hủy subscription upstream. Một client blocking không hỗ trợ cancellation vẫn có thể tiếp tục thực thi ở thread nền; hãy cấu hình timeout ngay tại HTTP client hoặc driver nếu có thể.

## 4. Exponential backoff và jitter

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại. Một dạng đơn giản là:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Trong đó:

- `d0` là khoảng chờ ban đầu.
- `n` là số thứ tự của lần retry.
- `dmax` là giới hạn thời gian chờ tối đa.

Ví dụ với `d0 = 100 ms` và `dmax = 2 s`, chuỗi thời gian chờ cơ sở có thể là 100 ms, 200 ms, 400 ms, 800 ms, 1.600 ms rồi giữ ở mức tối đa 2 giây.

Jitter thêm độ ngẫu nhiên vào khoảng chờ để các client không đồng loạt retry cùng thời điểm. Nếu tất cả client nhận lỗi tại cùng một thời điểm và đều chờ đúng 400 ms, chúng có thể cùng tạo một đợt request mới. Jitter phân tán thời điểm đó trong một khoảng rộng hơn.

Reactor hỗ trợ exponential backoff bằng `Retry.backoff`:

```java
Retry retryPolicy = Retry.backoff(
        4,
        Duration.ofMillis(100)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isTransient)
    .doBeforeRetry(signal -> log.warn(
        "Retry attempt {}, cause: {}",
        signal.totalRetries() + 1,
        signal.failure().toString()
    ));

Mono<Inventory> inventory = inventoryClient.fetch(sku)
    .retryWhen(retryPolicy);
```

`Retry.backoff(4, ...)` cho phép tối đa bốn lần retry sau lần đầu. `maxBackoff` giới hạn thời gian chờ cơ sở, `jitter` thêm độ lệch ngẫu nhiên và `filter` chỉ cho phép retry các lỗi đã phân loại. Callback `doBeforeRetry` phù hợp để ghi nhận metric hoặc log ngắn gọn; không nên thực hiện I/O blocking hoặc side effect nghiệp vụ trong callback này.

Jitter không thay thế giới hạn retry. Một chính sách có jitter nhưng retry vô hạn vẫn có thể tạo tải kéo dài. Cần kết hợp số lần thử tối đa, deadline, giới hạn concurrency và circuit breaker khi phù hợp.

## 5. Retry storm hình thành như thế nào?

Một retry storm thường bắt đầu khi dependency chậm hoặc lỗi. Client chờ timeout, retry ngay, làm lượng request tăng. Dependency vốn đang quá tải phải xử lý thêm các request lặp, khiến latency và tỷ lệ lỗi tăng hơn nữa. Nhiều client tiếp tục timeout và retry, tạo vòng phản hồi khuếch đại.

```text
Dependency bắt đầu chậm
          |
          v
Request timeout ở nhiều client
          |
          v
Các client retry gần như đồng thời
          |
          v
Lượng request đến dependency tăng
          |
          v
Dependency quá tải hơn, latency tăng
          |
          +-----------> timeout và retry tăng tiếp
```

Những yếu tố làm bão retry nghiêm trọng hơn:

- Retry ngay lập tức hoặc dùng fixed delay giống nhau cho mọi client.
- Retry không giới hạn hoặc số lần retry quá cao.
- Mỗi tầng service đều tự retry mà không chia sẻ deadline.
- Không giới hạn số request đang hoạt động.
- Retry cả lỗi validation, authentication hoặc lỗi không thể phục hồi.
- Client retry thao tác ghi không có idempotency.
- Không tôn trọng `Retry-After` hoặc tín hiệu quá tải từ dependency.
- Tăng số lần retry để che giấu latency hoặc capacity issue kéo dài.

### Retry ở nhiều tầng có thể nhân số lần gọi

Giả sử gateway cho phép tối đa ba lần retry và service downstream cũng cho phép tối đa ba lần retry. Mỗi tầng có thể thực hiện bốn lần thử tính cả lần đầu. Trong trường hợp xấu nhất, một request ban đầu có thể tạo ra đến 16 lần gọi ở tầng sâu hơn. Nếu có ba tầng với cùng chính sách, con số lý thuyết có thể tăng lên 64 lần.

| Số tầng có retry | Tổng lần thử mỗi tầng | Số lần gọi tối đa ở dependency cuối |
|---:|---:|---:|
| 1 | 4 | 4 |
| 2 | 4 | 16 |
| 3 | 4 | 64 |

Đây là phép nhân trong trường hợp mỗi lần thử ở tầng trên lại kích hoạt đầy đủ chính sách retry của tầng dưới. Trong thực tế, timeout, lỗi và nhánh xử lý có thể làm số lần khác đi. Dù vậy, ví dụ cho thấy retry độc lập ở nhiều tầng có thể khuếch đại tải rất nhanh.

Hãy quyết định tầng nào sở hữu retry cho một dependency. Nếu nhiều tầng phải retry, cần chia sẻ deadline, giới hạn số lần thử tổng và tránh nhân chính sách một cách vô tình.

## 6. Tính lũy đẳng: điều kiện để retry thao tác ghi an toàn

Một thao tác là lũy đẳng nếu thực hiện một lần hay nhiều lần với cùng đầu vào đều tạo ra cùng kết quả quan sát được.

\[
f(f(x)) = f(x)
\]

Ví dụ, đặt trạng thái đơn hàng thành `SHIPPED` có thể là lũy đẳng nếu thao tác chỉ ghi trạng thái đích và không tạo side effect mới mỗi lần. Ngược lại, thao tác “cộng thêm 100 điểm” không lũy đẳng: gọi hai lần sẽ cộng 200 điểm.

| Thao tác | Có thể lũy đẳng? | Điều kiện |
|---|---|---|
| Đọc thông tin theo ID | Thường có. | Cùng điều kiện đọc và cùng snapshot dữ liệu cho cùng kết quả tại một thời điểm. |
| Đặt trạng thái thành `CANCELLED` | Có thể. | Lệnh đặt trạng thái đích không phát sinh side effect lặp. |
| Tạo đơn hàng mới | Không mặc định. | Cần idempotency key hoặc unique command ID. |
| Trừ tồn kho 1 đơn vị | Không mặc định. | Cần ghi nhận command/event đã xử lý trong cùng transaction. |
| Gửi email hoặc thông báo | Không mặc định. | Cần deduplication key ở hệ thống gửi hoặc một outbox có trạng thái gửi. |
| Thanh toán thẻ | Không mặc định. | Dùng idempotency key do provider hỗ trợ và lưu kết quả tương ứng. |

Retry một thao tác ghi sau timeout đặc biệt nguy hiểm vì client không biết server đã thực hiện hay chưa. Có thể server đã ghi database nhưng response bị mất trên mạng. Lần retry tiếp theo nếu tạo một giao dịch mới sẽ nhân đôi side effect.

## 7. Idempotency key cho request có side effect

Idempotency key là một định danh ổn định cho một ý định nghiệp vụ. Client tạo key một lần cho command, sau đó gửi lại cùng key ở mọi lần retry. Server lưu key cùng kết quả xử lý và trả lại kết quả cũ nếu nhận lại cùng command.

Ví dụ client gửi lệnh thanh toán:

```java
record PaymentCommand(
    String orderId,
    BigDecimal amount,
    String idempotencyKey
) {}

Mono<PaymentResult> charge(PaymentCommand command) {
    return Mono.defer(() -> paymentClient.charge(
            command.orderId(),
            command.amount(),
            command.idempotencyKey()
        ))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.5)
            .filter(this::isTransient));
}
```

`idempotencyKey` nằm trong command và được tái sử dụng qua mọi subscription. Không tạo key mới bên trong `Mono.defer`, vì mỗi lần retry sẽ chạy lại supplier; nếu key được tạo ở đó, mỗi lần thử trở thành một command mới và cơ chế deduplication không còn hiệu lực.

Với HTTP API, key thường được truyền qua header như `Idempotency-Key`. Server cần quy định thời gian lưu key, phạm vi unique, cách xử lý cùng key nhưng payload khác và cách trả kết quả khi request đầu vẫn đang được xử lý.

### Server phải lưu key và kết quả một cách nguyên tử

Một bảng idempotency có thể lưu:

```sql
CREATE TABLE idempotency_record (
    idempotency_key VARCHAR(120) PRIMARY KEY,
    request_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    response_payload TEXT,
    created_at TIMESTAMP NOT NULL
);
```

Luồng xử lý khái quát:

1. Nhận key và tính hash từ payload chuẩn hóa.
2. Tạo bản ghi key trong transaction với ràng buộc unique.
3. Nếu key đã tồn tại và hash giống nhau, trả lại kết quả đã lưu hoặc trạng thái đang xử lý.
4. Nếu key đã tồn tại nhưng hash khác, từ chối vì cùng key đang được dùng cho một command khác.
5. Thực hiện side effect nghiệp vụ.
6. Lưu kết quả và đánh dấu command hoàn tất trong cùng transaction thích hợp.

Ràng buộc unique giúp hai request đồng thời dùng cùng key không cùng thực hiện side effect. Việc kiểm tra key và ghi kết quả phải được bảo vệ bằng transaction hoặc cơ chế đồng bộ tương đương. Chỉ kiểm tra bằng một câu `SELECT` rồi thực hiện thao tác ở ngoài transaction vẫn có race condition: hai request có thể cùng thấy key chưa tồn tại.

Nếu side effect nằm ở hệ thống bên ngoài database, transaction local không thể tự bảo đảm atomicity xuyên hai hệ thống. Khi đó cần provider hỗ trợ idempotency key, outbox/inbox, saga hoặc một giao thức phối hợp phù hợp.

## 8. Deduplication cho consumer xử lý sự kiện

Message broker thường cung cấp giao nhận at-least-once: một thông điệp có thể được giao lại nếu consumer xử lý xong nhưng chưa commit offset/ack trước khi crash. Consumer cần idempotent để sự kiện lặp không làm thay đổi kết quả hai lần.

Một mẫu inbox lưu `eventId` đã xử lý trong cùng transaction với cập nhật projection:

```text
BEGIN TRANSACTION
    INSERT event_id INTO processed_event
        (unique constraint on event_id)

    IF insert succeeds:
        apply event to projection
    ELSE:
        event was already processed; skip projection update
COMMIT

ACK message only after transaction commits
```

Ví dụ Java minh họa:

```java
Mono<Void> handle(OrderEvent event) {
    return transactionalOperator.transactional(
        inboxRepository.insertIfAbsent(event.eventId())
            .flatMap(inserted -> {
                if (!inserted) {
                    return Mono.empty();
                }

                return orderProjection.apply(event);
            })
    );
}
```

Đoạn mã giả định `insertIfAbsent` thực hiện thao tác insert có ràng buộc unique và trả `true` khi bản ghi mới được tạo, `false` khi event đã tồn tại. Trong hệ thống thật, cách bắt unique conflict và cách triển khai `insertIfAbsent` phụ thuộc database. Acknowledge message chỉ nên thực hiện sau khi publisher transaction hoàn tất thành công.

Nếu consumer crash sau transaction commit nhưng trước acknowledgement, broker có thể giao lại event. Lần xử lý thứ hai, inbox phát hiện `eventId` đã tồn tại và bỏ qua side effect trùng, sau đó consumer có thể acknowledge. Đây là cách kết hợp at-least-once delivery với xử lý idempotent để đạt kết quả nghiệp vụ đáng tin cậy.

## 9. Retry và tính lũy đẳng trong Reactor

Một pipeline retry cần đặt operator quanh đúng phần công việc có thể chạy lại. Hãy tránh đặt retry quá rộng quanh cả chuỗi gồm nhiều side effect không liên quan.

Ví dụ chỉ retry lời gọi đọc dữ liệu:

```java
Mono<Customer> customer = customerClient.findById(customerId)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isTransient));

Mono<OrderResult> result = customer
    .flatMap(value -> orderService.createFor(value));
```

Ở đây lỗi trong `createFor` không bị retry bởi chính sách đặt trên publisher `customer`. Điều này tránh việc một lỗi ghi đơn hàng khiến lời gọi đọc customer bị thực thi lại một cách không cần thiết.

Nếu đặt retry ở cuối:

```java
Mono<OrderResult> risky = customerClient.findById(customerId)
    .flatMap(orderService::createFor)
    .retryWhen(retryPolicy);
```

thì cả thao tác đọc customer và `createFor` đều có thể chạy lại. Nếu `createFor` không idempotent, đơn hàng có thể được tạo nhiều lần. Phạm vi retry nên càng hẹp càng tốt và bao quanh đúng thao tác được bảo vệ.

### `defer` để tạo một lần thử mới đúng thời điểm

`Mono.defer` gọi supplier mỗi khi có subscription. Điều này hữu ích khi mỗi attempt cần tạo một request hoặc đọc trạng thái mới:

```java
Mono<Response> callRemote(Command command) {
    return Mono.defer(() -> remoteClient.execute(command))
        .retryWhen(retryPolicy);
}
```

Nhưng dữ liệu nhận diện command phải ổn định qua các lần thử. Hãy tạo idempotency key trước khi xây dựng publisher và giữ nguyên nó trong `Command`; `defer` chỉ nên tạo lại request attempt, không tạo ý định nghiệp vụ mới.

## 10. Retry có thể làm lặp side effect nằm trước lỗi

Một publisher có thể thực hiện side effect rồi mới phát lỗi. Ví dụ, server ghi dữ liệu thành công nhưng kết nối bị ngắt trước khi response về. Từ góc nhìn client, lần gọi thất bại; từ góc nhìn server, side effect đã hoàn tất.

```text
Client                    Server
  |                          |
  |------ POST command ----->|
  |                          | commit database
  |<----- response ----------X  connection lost
  |
  | timeout/error
  |
  |------ retry POST ------->|
  |                          | side effect có thể lặp
```

Đây là lý do không thể suy ra “server chưa làm gì” chỉ từ việc client nhận timeout. Retry phải được bảo vệ bằng idempotency key, unique command ID hoặc một thao tác vốn đã idempotent.

Không nên dùng `doOnSuccess` để ghi một side effect quan trọng rồi retry publisher bao quanh nó mà không có deduplication. Nếu callback được thực thi trước khi một lỗi downstream làm subscription retry lại, callback có thể chạy nhiều lần. Hãy đưa side effect vào một thao tác có tính lũy đẳng hoặc lưu trạng thái xử lý một cách nguyên tử.

## 11. Retry phối hợp với circuit breaker, bulkhead và rate limit

Retry là một phần của khả năng phục hồi, không phải cơ chế duy nhất. Các mẫu khác giải quyết vấn đề liên quan:

| Mẫu | Vai trò | Khi hữu ích |
|---|---|---|
| Retry | Thử lại lỗi có khả năng tạm thời. | Sự cố ngắn, xác suất lần tiếp theo thành công. |
| Circuit breaker | Tạm ngừng gọi dependency khi tỷ lệ lỗi vượt ngưỡng. | Dependency đang lỗi kéo dài hoặc quá tải. |
| Bulkhead | Giới hạn tài nguyên/concurrency dành cho một dependency. | Tránh một dependency chiếm hết worker hoặc connection. |
| Rate limiter | Giới hạn tốc độ request. | Bảo vệ quota hoặc capacity của dịch vụ đích. |
| Timeout/deadline | Giới hạn thời gian chờ. | Tránh giữ request và tài nguyên quá lâu. |
| Fallback | Trả kết quả thay thế khi dependency không khả dụng. | Nghiệp vụ cho phép dữ liệu cũ, cache hoặc kết quả suy giảm. |

Một circuit breaker có thể ngăn retry tiếp tục đập vào dependency đang lỗi. Bulkhead giới hạn số lời gọi đồng thời. Rate limiter bảo vệ quota. Các mẫu này cần được phối hợp để retry không vượt quá deadline hoặc capacity.

Nếu dùng resilience library như Resilience4j với Reactor, hãy xác định thứ tự decorator. Retry bên ngoài circuit breaker có thể tạo nhiều lần gọi đi qua breaker; circuit breaker bên ngoài retry có thể xem toàn bộ chuỗi retry như một lần gọi. Chọn thứ tự dựa trên metric và chính sách mong muốn, rồi kiểm thử hành vi khi breaker mở.

## 12. Tôn trọng `Retry-After` và tín hiệu quá tải

Một số dịch vụ trả HTTP 429 hoặc 503 cùng header `Retry-After`. Header có thể biểu diễn số giây chờ hoặc thời điểm HTTP-date. Nếu dependency đưa ra thời gian chờ rõ ràng, client nên tuân thủ trong giới hạn deadline và chính sách retry của mình.

Không nên retry ngay khi nhận 429. Điều đó khiến client tiếp tục vượt quota. Hãy:

- Đọc và parse `Retry-After` theo định dạng server gửi.
- Giới hạn thời gian chờ tối đa theo deadline của request.
- Thêm jitter nếu nhiều client có thể cùng nhận một thời điểm retry.
- Giảm concurrency hoặc tốc độ gửi nếu quota tiếp tục bị vượt.
- Ghi nhận metric số lần bị rate limit và thời gian chờ đã áp dụng.

Nếu header yêu cầu chờ lâu hơn deadline của request, thường nên trả lỗi cho caller hoặc chuyển sang cơ chế xử lý nền thay vì giữ request mở vô thời hạn.

## 13. Quan sát retry mà không tạo thêm tải

Retry cần được đo lường. Nếu chỉ ghi log lỗi cuối cùng, đội vận hành có thể không thấy dependency đang thất bại nhiều lần trước khi một request thành công.

Các metric hữu ích:

- Số attempt và số retry theo dependency, operation và loại lỗi.
- Tỷ lệ request thành công ngay lần đầu so với thành công sau retry.
- Tỷ lệ retry exhaustion (đã dùng hết số lần thử).
- Thời gian chờ backoff và tổng latency bao gồm retry.
- Số request đang chờ, concurrency và queue size.
- Số lần nhận HTTP 429/503 và phân bố `Retry-After`.
- Tỷ lệ duplicate bị idempotency/inbox phát hiện.
- Số lần circuit breaker mở và thời gian ở trạng thái open/half-open.

Ví dụ ghi nhận trước mỗi lần retry:

```java
Retry policy = Retry.backoff(3, Duration.ofMillis(100))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isTransient)
    .doBeforeRetry(signal -> retryCounter.increment(
        Tags.of(
            "dependency", "inventory",
            "exception", signal.failure().getClass().getSimpleName()
        )
    ));
```

Metric nên dùng nhãn có cardinality giới hạn. Không dùng request ID, user ID hoặc idempotency key làm tag metric vì số giá trị có thể tăng không giới hạn. Những định danh chi tiết có thể nằm trong log hoặc trace có kiểm soát.

Log retry nên chứa dependency, operation, số lần retry, loại lỗi và thời gian chờ. Tránh ghi payload nhạy cảm hoặc token. Không log toàn bộ stack trace ở mọi lần retry nếu điều đó có thể tạo thêm áp lực I/O khi sự cố xảy ra; có thể ghi chi tiết ở lần cuối và dùng metric cho các lần trước.

## 14. Kiểm thử retry và backoff bằng thời gian ảo

Không dùng `Thread.sleep` để kiểm tra backoff. Reactor Test cung cấp `StepVerifier.withVirtualTime` để tiến thời gian mà không phải chờ thật. Publisher phải được tạo bên trong supplier của `withVirtualTime` để scheduler ảo được cài đặt trước khi pipeline khởi tạo.

Ví dụ kiểm thử hai lần thất bại rồi thành công:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IOException("temporary"));
    }
    return Mono.just("ok");
});

StepVerifier.withVirtualTime(() ->
        source.retryWhen(Retry.backoff(
            2,
            Duration.ofSeconds(1)
        ).jitter(0))
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("ok")
    .verifyComplete();

assertEquals(3, attempts.get());
```

Với `jitter(0)`, thời gian chờ trong test có thể được kiểm soát xác định. Trong production, jitter nên được bật để phân tán retry. Thời gian ảo không điều khiển những scheduler tùy chỉnh hoặc client thật nằm ngoài scheduler được thay thế; hãy tiêm scheduler hoặc tách adapter để kiểm thử độc lập.

### Kiểm thử lỗi không được retry

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> invalidRequest = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.error(new IllegalArgumentException("invalid input"));
}).retryWhen(Retry.backoff(3, Duration.ofMillis(100))
    .filter(this::isTransient));

StepVerifier.create(invalidRequest)
    .expectError(IllegalArgumentException.class)
    .verify();

assertEquals(1, attempts.get());
```

Test xác minh lỗi không thuộc nhóm tạm thời chỉ tạo một attempt. Khi viết test thực tế, predicate nên được dùng chung với code production để tránh test một chính sách khác với chính sách triển khai.

### Kiểm thử retry exhaustion

Hãy kiểm tra lỗi cuối cùng sau khi đã hết số lần retry, loại exception mà caller nhận và metric retry exhaustion được cập nhật. Đừng chỉ xác minh rằng publisher phát lỗi; cần xác minh số attempt đúng với giới hạn cấu hình.

## 15. Tình huống thực tế: cập nhật tồn kho qua API từ xa

Một dịch vụ đơn hàng cần giữ chỗ tồn kho qua API inventory. API có thể tạm thời trả 503 hoặc timeout. Command giữ chỗ có side effect, vì vậy mỗi đơn hàng cần một idempotency key ổn định.

```java
record ReserveInventoryCommand(
    String orderId,
    String sku,
    int quantity,
    String idempotencyKey
) {}

Mono<Reservation> reserve(ReserveInventoryCommand command) {
    Retry retryPolicy = Retry.backoff(
            3,
            Duration.ofMillis(150)
        )
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(error -> error instanceof IOException
            || error instanceof TimeoutException
            || error instanceof InventoryUnavailableException);

    return Mono.defer(() -> inventoryClient.reserve(
            command.sku(),
            command.quantity(),
            command.idempotencyKey()
        ))
        .timeout(Duration.ofSeconds(1))
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(5));
}
```

Thiết kế có các đặc điểm:

1. Command mang key ổn định được tạo ở tầng gọi, không tạo key mới trong mỗi attempt.
2. `Mono.defer` tạo request mới cho mỗi subscription retry.
3. Timeout bên trong giới hạn từng lần gọi; timeout bên ngoài giới hạn toàn bộ thời gian chờ.
4. Chỉ lỗi kết nối, timeout và service unavailable đã chọn mới được retry.
5. Backoff tăng dần và jitter phân tán thời điểm gọi lại.
6. API inventory phải lưu idempotency key và kết quả để request lặp không giữ tồn kho lần thứ hai.

Nếu API trả lỗi “insufficient stock”, đây là kết quả nghiệp vụ và không nên retry. Nếu API trả 429, cần bổ sung xử lý `Retry-After` và giới hạn quota. Nếu timeout xảy ra sau khi inventory đã giữ hàng nhưng response bị mất, lần thử tiếp theo với cùng key phải trả lại reservation đã tạo trước đó.

## 16. Checklist thiết kế retry an toàn

- Xác định chính xác publisher nào được phép chạy lại; đặt retry quanh phạm vi nhỏ nhất cần thiết.
- Phân loại lỗi tạm thời và lỗi vĩnh viễn bằng predicate rõ ràng.
- Giới hạn số lần retry và tính tổng số attempt bao gồm lần đầu.
- Dùng exponential backoff, max backoff và jitter để tránh retry đồng bộ.
- Đặt timeout cho từng attempt và deadline tổng cho toàn chuỗi.
- Tuân thủ `Retry-After` và tín hiệu rate limit trong giới hạn deadline.
- Giới hạn concurrency, queue và số request đang hoạt động.
- Tránh retry lặp ở nhiều tầng nếu không có ngân sách retry tổng.
- Đảm bảo thao tác ghi idempotent hoặc dùng idempotency key ổn định.
- Lưu idempotency key và kết quả nguyên tử; phát hiện cùng key nhưng payload khác.
- Dùng inbox/deduplication cho consumer at-least-once và acknowledge sau khi lưu bền vững.
- Không giả định timeout có nghĩa server chưa thực hiện side effect.
- Theo dõi attempt, retry exhaustion, latency, duplicate và trạng thái circuit breaker.
- Kiểm thử số lần gọi, lỗi không retry, retry exhaustion và backoff bằng thời gian ảo.

Retry giúp hệ thống vượt qua lỗi tạm thời khi được giới hạn và đặt đúng chỗ. Backoff cùng jitter giảm nguy cơ nhiều client đồng loạt gọi lại dependency; deadline, concurrency và circuit breaker bảo vệ tài nguyên khi sự cố kéo dài. Tính lũy đẳng và idempotency key xử lý trường hợp kết quả lần gọi trước không rõ ràng, giúp request hoặc message được thử lại mà không nhân đôi side effect nghiệp vụ.
