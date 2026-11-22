# Phân biệt thứ tự nghiệp vụ với thứ tự giao nhận trong Spring Messaging

Trong hệ thống messaging, hai message có thể được gửi theo một thứ tự nhưng được nhận, xử lý hoặc commit theo thứ tự khác. Vì vậy cần tách biệt **thứ tự nghiệp vụ** do miền ứng dụng quy định với **thứ tự giao nhận** do transport, broker, channel và consumer tạo ra.

Ví dụ trong một đơn hàng, nghiệp vụ yêu cầu `OrderCreated` xảy ra trước `PaymentAuthorized`, rồi mới tới `OrderShipped`. Consumer có thể nhận lần lượt sequence 1, 3, 2 vì event thứ hai bị chậm hoặc được retry. Nếu áp dụng event 3 ngay khi nhận, trạng thái đơn hàng có thể sai dù message cuối cùng đều đã tới.

## 1. Hai khái niệm và các mốc thứ tự khác nhau

**Thứ tự nghiệp vụ (business order)** là thứ tự hợp lệ theo quy tắc miền: trạng thái nào được phép chuyển trước, event nào phụ thuộc event nào, và phiên bản nào của một aggregate phải được áp dụng trước. Thứ tự này nên được biểu diễn bằng quy tắc hoặc số thứ tự logic rõ ràng, thường là sequence/version theo từng aggregate như `orderId`.

**Thứ tự giao nhận (delivery order)** là thứ tự message đi qua các bước kỹ thuật. Trong thực tế, cần phân biệt ít nhất các mốc sau:

| Mốc | Ý nghĩa | Điều nó không tự chứng minh |
| --- | --- | --- |
| Publish order | Producer phát message theo thứ tự nào | Broker hoặc consumer chắc chắn thấy cùng thứ tự đó |
| Broker/queue order | Broker nhận hoặc xếp message theo thứ tự nào | Nhiều consumer sẽ hoàn tất xử lý theo thứ tự đó |
| Receive order | Client/consumer đọc message theo thứ tự nào | Handler hoặc transaction sẽ hoàn tất theo thứ tự đó |
| Handling start order | Handler bắt đầu xử lý theo thứ tự nào | Các tác vụ chạy song song sẽ kết thúc theo thứ tự đó |
| Completion order | Xử lý bất đồng bộ kết thúc theo thứ tự nào | Dữ liệu đã commit bền vững theo cùng thứ tự đó |
| Commit order | Thay đổi trạng thái được lưu bền vững theo thứ tự nào | Các hệ thống downstream đã nhận và áp dụng cùng thứ tự đó |

Một ứng dụng chỉ có thể nói “đã giữ thứ tự” khi chỉ rõ đang giữ thứ tự ở mốc nào, trong phạm vi nào: một session, một connection, một queue, một partition, một aggregate hay toàn hệ thống.

Ví dụ một chuỗi nghiệp vụ hợp lệ:

```text
Business sequence của order-42
1. OrderCreated
2. PaymentAuthorized
3. OrderShipped

Thứ tự consumer nhận được
1. OrderCreated
3. OrderShipped  <- đến sớm do xử lý/retry/đường truyền khác nhau
2. PaymentAuthorized
```

Nhận được event số 3 không có nghĩa nghiệp vụ đã sẵn sàng áp dụng nó. Consumer phải kiểm tra sequence hoặc điều kiện trạng thái trước khi thay đổi dữ liệu.

## 2. Vì sao thứ tự giao nhận có thể khác thứ tự nghiệp vụ?

- **Nhiều producer:** hai producer cùng phát event cho một aggregate có thể cạnh tranh và không có thứ tự toàn cục nếu không dùng cơ chế đồng bộ hoặc sequence được cấp tại nơi ghi trạng thái.
- **Executor và thread pool:** message được nhận tuần tự nhưng giao cho nhiều worker. Worker xử lý lâu hơn có thể hoàn tất sau worker nhận message kế tiếp.
- **Consumer song song:** nhiều consumer hoặc nhiều subscription xử lý độc lập; thứ tự đọc từ queue không đồng nghĩa thứ tự hoàn tất.
- **Retry và redelivery:** event cũ có thể được gửi lại sau khi event mới đã tới; message bị delay hoặc chuyển qua dead-letter flow có thể quay lại muộn.
- **Broker partition hoặc queue khác nhau:** các nhóm message độc lập không có một thứ tự tổng thể chung. Broker thường chỉ cung cấp thứ tự trong phạm vi mà tài liệu của broker cam kết.
- **Reactive concurrency:** `flatMap` có thể chạy nhiều publisher con đồng thời và trộn kết quả khi chúng hoàn tất.
- **Nhiều connection/session:** thứ tự trên một connection không tạo ra thứ tự chung giữa các client hoặc producer khác nhau.

TCP giữ thứ tự byte trong cùng một kết nối TCP. Tuy nhiên, ứng dụng có thể đưa các message đã đọc vào executor, nhiều luồng hoặc nhiều reactive pipeline. Vì vậy thứ tự byte trên socket không tự bảo đảm thứ tự handler hoàn tất hoặc thứ tự commit trong database. Cũng không thể suy ra một thứ tự toàn cục giữa nhiều connection.

## 3. Spring Messaging và thứ tự message

Spring biểu diễn message bằng `Message<T>` gồm payload và headers; `MessageChannel` tách producer khỏi consumer. Channel hoặc broker là cơ chế vận chuyển/dispatch. Hợp đồng của `Message` và `MessageChannel` không tự tạo sequence nghiệp vụ, không tự sắp xếp event theo quy tắc aggregate và không bảo đảm transaction ở consumer đã commit.

Header `MessageHeaders.ID` nhận diện message; `MessageHeaders.TIMESTAMP` ghi thời điểm message được tạo. Chúng hữu ích cho tracing và quan sát, nhưng không thay thế sequence nghiệp vụ: timestamp có thể trùng, đồng hồ giữa máy lệch nhau, message có thể được tạo ở nhiều node và retry có thể đến muộn. ID cũng không thể hiện event nào phải xảy ra trước event nào.

### 3.1. STOMP over WebSocket: giữ thứ tự nhận và thứ tự publish

Trong STOMP, Spring thường dùng `clientInboundChannel` để nhận message từ WebSocket client, `brokerChannel` để chuyển message từ code phía server tới broker và `clientOutboundChannel` để gửi message về WebSocket client. Các channel inbound/outbound có thể dùng executor. Khi nhiều task chạy trên thread pool, thứ tự handler xử lý hoặc client nhận được có thể khác thứ tự ban đầu.

Spring Framework cung cấp hai tùy chọn riêng:

| API | Vị trí cấu hình | Phạm vi được giữ thứ tự |
| --- | --- | --- |
| `StompEndpointRegistry.setPreserveReceiveOrder(true)` | `registerStompEndpoints` | Message từ cùng một client session được đưa vào `clientInboundChannel` lần lượt theo thứ tự nhận. Có từ Spring Framework 6.1. |
| `MessageBrokerRegistry.setPreservePublishOrder(true)` | `configureMessageBroker` | Message gửi tới cùng một client session qua `clientOutboundChannel` được publish lần lượt theo thứ tự publish. Có từ Spring Framework 5.1. |

Ví dụ cấu hình cả hai chiều:

```java
@Configuration
@EnableWebSocketMessageBroker
public class StompOrderConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setPreservePublishOrder(true);
    }
}
```

Đây là cấu hình minh họa cho Spring Framework 6.1 trở lên vì có sử dụng `setPreserveReceiveOrder`. `setPreservePublishOrder` đã có từ Spring Framework 5.1. Hai cờ này giải quyết hai hướng khác nhau: message client gửi vào và message server/broker gửi ra. Chỉ bật cờ phù hợp với vấn đề đang gặp.

Các cờ này có chi phí hiệu năng vì giảm mức xử lý song song trong phạm vi session. Chúng chỉ giữ thứ tự trong cùng session tại các channel tương ứng; không tạo global order giữa nhiều session, không sắp xếp event theo `orderId`, không khắc phục việc producer phát sai thứ tự và không thay thế sequence/version trong domain.

### 3.2. RSocket và các request đồng thời

RSocket hỗ trợ nhiều interaction model như Request-Response, Request-Stream, Channel và Fire-and-Forget. Nhiều request độc lập có thể đang chạy đồng thời. Response của request gửi trước có thể hoàn tất sau response của request gửi sau nếu thời gian xử lý khác nhau. Không nên dựa vào thứ tự hoàn tất của các request đồng thời để suy ra thứ tự nghiệp vụ.

- Với một `Flux`, `concatMap` subscribe và xử lý publisher con tuần tự, giữ thứ tự phần tử đầu vào và không cho các publisher con xen kẽ.
- `flatMap` cho phép publisher con chạy đồng thời và trộn kết quả theo thời điểm phát ra; không phù hợp nếu side effect phải được thực hiện tuần tự.
- `flatMapSequential` có thể subscribe publisher con đồng thời nhưng xếp hàng kết quả để phát ra theo thứ tự đầu vào. Nó giữ thứ tự output, nhưng công việc bên trong vẫn có thể chạy song song; không dùng nó như một bảo đảm rằng các side effect đã xảy ra tuần tự.

Ví dụ xử lý lần lượt các command trong cùng một luồng:

```java
Flux<OrderCommand> commands = receiveCommands();

Flux<OrderResult> results = commands.concatMap(orderService::apply);
```

Đây là đoạn mã minh họa; `receiveCommands()` và `orderService` do ứng dụng cung cấp. `concatMap` tuần tự hóa việc subscribe và chờ publisher của command hiện tại hoàn tất trước khi xử lý publisher tiếp theo. Nếu các command thuộc các aggregate độc lập, có thể xử lý song song giữa các aggregate nhưng phải tuần tự bên trong từng aggregate.

## 4. Thiết kế thứ tự nghiệp vụ bằng sequence/version

Khi các event của một aggregate phải áp dụng theo thứ tự, hãy đưa thứ tự đó vào hợp đồng message. Một event thường có các trường như:

| Trường | Mục đích |
| --- | --- |
| `eventId` | Định danh duy nhất để nhận diện và loại bỏ bản gửi trùng |
| `aggregateId` | Khóa đối tượng nghiệp vụ mà event tác động, ví dụ `orderId` |
| `sequence` hoặc `aggregateVersion` | Số thứ tự tăng đơn điệu trong phạm vi aggregate |
| `eventType` | Loại sự kiện, ví dụ `PaymentAuthorized` |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra, phục vụ audit/quan sát |
| `correlationId` / `causationId` | Liên kết chuỗi tương tác và nguyên nhân tạo event |

`sequence` phải được cấp tại nơi có thẩm quyền ghi trạng thái aggregate. Nếu nhiều producer tự tạo sequence bằng đồng hồ hoặc bộ đếm cục bộ, có thể sinh số trùng hoặc thứ tự không nhất quán. Thường nên cập nhật version và ghi event trong cùng transaction database.

Ví dụ hợp đồng:

```json
{
  "eventId": "evt-9003",
  "aggregateId": "order-42",
  "sequence": 3,
  "eventType": "OrderShipped",
  "occurredAt": "2026-11-07T10:15:30Z"
}
```

Sequence thường chỉ cần duy nhất và liên tục trong một aggregate. Không cần ép tất cả đơn hàng, tài khoản hoặc session dùng một bộ đếm toàn cục. Phân vùng theo aggregate cho phép xử lý song song giữa các đối tượng độc lập trong khi giữ đúng thứ tự của từng đối tượng.

### 4.1. Quy tắc consumer khi nhận event

Giả sử consumer đã áp dụng tới sequence 1 và nhận sequence 3:

1. Nếu `sequence` nhỏ hơn hoặc bằng `lastAppliedSequence`, xem là bản trùng hoặc đến muộn; bỏ qua an toàn sau khi xác nhận event đã được xử lý.
2. Nếu `sequence == lastAppliedSequence + 1`, áp dụng event và tăng `lastAppliedSequence` trong cùng transaction với thay đổi nghiệp vụ.
3. Nếu `sequence > lastAppliedSequence + 1`, phát hiện khoảng trống. Tạm giữ event, đợi event thiếu, yêu cầu replay từ nguồn hoặc chuyển sang quy trình reconciliation.
4. Nếu khoảng trống không được lấp đầy trong thời hạn chính sách, phát cảnh báo và đưa aggregate vào trạng thái chờ xử lý. Không tự ý áp dụng event sau nếu điều đó phá vỡ invariant nghiệp vụ.

Buffer phải có giới hạn dung lượng và thời gian chờ. Nếu event số 2 không bao giờ tới, việc giữ event số 3 vô hạn có thể gây rò rỉ bộ nhớ hoặc làm tắc partition. Cần có chính sách timeout, replay, dead-letter, cảnh báo và thao tác khôi phục có kiểm soát.

### 4.2. Ví dụ Java 17: giữ thứ tự theo sequence

Chương trình dưới đây mô phỏng một consumer cho một aggregate. Event số 3 tới trước số 2 sẽ được giữ lại; khi số 2 tới, consumer áp dụng lần lượt số 2 rồi số 3. Event số 2 gửi lại sau đó được nhận diện là bản trùng/đến muộn.

**OrderSequenceDemo.java**

```java
import java.util.NavigableMap;
import java.util.TreeMap;

record OrderEvent(String orderId, long sequence, String type) { }

public class OrderSequenceDemo {

    static final class Processor {
        private final String orderId;
        private long nextSequence = 1;
        private final NavigableMap<Long, OrderEvent> pending = new TreeMap<>();

        Processor(String orderId) {
            this.orderId = orderId;
        }

        void accept(OrderEvent event) {
            if (!orderId.equals(event.orderId())) {
                throw new IllegalArgumentException("Unexpected aggregate");
            }

            if (event.sequence() < nextSequence) {
                System.out.printf("Ignored duplicate/late %s #%d%n",
                        event.orderId(), event.sequence());
                return;
            }

            OrderEvent previous = pending.putIfAbsent(event.sequence(), event);
            if (previous != null) {
                System.out.printf("Ignored duplicate pending %s #%d%n",
                        event.orderId(), event.sequence());
                return;
            }

            if (event.sequence() > nextSequence) {
                System.out.printf("Buffered %s #%d %s; waiting for #%d%n",
                        event.orderId(), event.sequence(), event.type(), nextSequence);
                return;
            }

            drain();
        }

        private void drain() {
            OrderEvent event;
            while ((event = pending.remove(nextSequence)) != null) {
                System.out.printf("Applied %s #%d %s%n",
                        event.orderId(), event.sequence(), event.type());
                nextSequence++;
            }
        }
    }

    public static void main(String[] args) {
        Processor processor = new Processor("order-42");
        processor.accept(new OrderEvent("order-42", 1, "OrderCreated"));
        processor.accept(new OrderEvent("order-42", 3, "OrderShipped"));
        processor.accept(new OrderEvent("order-42", 2, "PaymentAuthorized"));
        processor.accept(new OrderEvent("order-42", 2, "PaymentAuthorized"));
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac OrderSequenceDemo.java
java OrderSequenceDemo
```

Output chính xác:

```text
Applied order-42 #1 OrderCreated
Buffered order-42 #3 OrderShipped; waiting for #2
Applied order-42 #2 PaymentAuthorized
Applied order-42 #3 OrderShipped
Ignored duplicate/late order-42 #2
```

Ví dụ dùng `TreeMap` trong bộ nhớ để minh họa thuật toán, không phải triển khai production. Ứng dụng thực tế phải lưu `lastAppliedSequence` và các event đang chờ một cách bền vững, bảo vệ xử lý đồng thời cho cùng aggregate, và cập nhật sequence cùng side effect trong transaction. Nếu ứng dụng khởi động lại, buffer trong RAM của ví dụ sẽ mất.

## 5. Các mẫu triển khai trong hệ thống phân tán

### 5.1. Phân vùng theo aggregate hoặc ordering key

Gửi các event cùng `aggregateId` tới cùng partition, queue group hoặc consumer lane theo khả năng của broker. Khi broker bảo đảm thứ tự trong phạm vi đó, consumer có thể xử lý tuần tự trong phạm vi key và xử lý song song giữa các key. Tên gọi và bảo đảm cụ thể phụ thuộc broker; Spring Messaging không tự định nghĩa partition semantics.

Không dùng một consumer duy nhất cho toàn bộ hệ thống chỉ để có thứ tự toàn cục nếu nghiệp vụ chỉ cần thứ tự theo từng aggregate. Một luồng toàn cục làm giảm throughput và khiến một message chậm chặn các message không liên quan.

### 5.2. Transactional Outbox

Khi một transaction cập nhật đơn hàng và phát event, có thể ghi thay đổi nghiệp vụ cùng một bản ghi outbox trong cùng transaction database. Publisher đọc outbox và gửi event sau khi commit.

Outbox giúp tránh tình huống database đã commit nhưng event không được phát, hoặc event được phát khi transaction nghiệp vụ rollback. Tuy nhiên, outbox một mình chưa bảo đảm publish order: publisher vẫn phải đọc và gửi event theo sequence của aggregate, tránh nhiều worker phát cùng aggregate đồng thời, và dùng ordering key/partition phù hợp ở broker.

### 5.3. Idempotency và xử lý message trùng

Broker hoặc transport có thể giao lại message khi acknowledgement bị mất, consumer restart hoặc retry. Consumer nên lưu `eventId` đã xử lý hoặc kiểm tra sequence/version để một event không áp dụng side effect hai lần. Việc ghi dấu đã xử lý và cập nhật trạng thái aggregate cần được commit nguyên tử.

Nếu consumer commit database rồi mới ACK nhưng ACK bị mất, message có thể được giao lại; deduplication giúp lần giao lại không tạo side effect thứ hai. Nếu ACK trước khi commit và consumer chết giữa hai bước, message có thể bị mất khỏi luồng xử lý dù nghiệp vụ chưa được lưu. Thời điểm ACK cần theo semantics của broker và transaction.

### 5.4. Xử lý event bị thiếu hoặc đến quá muộn

Khi phát hiện sequence gap, hệ thống có thể chờ một khoảng ngắn, yêu cầu publisher replay, đọc lại event log, hoặc đưa aggregate vào hàng chờ reconciliation. Chính sách phải xác định rõ event nào được phép bỏ qua và ai có quyền xác nhận bỏ qua. Với event biểu diễn chuyển trạng thái không thể đảo ngược, tự sắp xếp theo timestamp hoặc áp dụng event mới nhất thường không an toàn.

## 6. Chọn mức bảo đảm phù hợp

| Nhu cầu | Cách tiếp cận | Đánh đổi |
| --- | --- | --- |
| Giữ thứ tự client gửi vào trong một STOMP session | `setPreserveReceiveOrder(true)` | Giảm song song inbound trong session đó |
| Giữ thứ tự server publish tới một STOMP session | `setPreservePublishOrder(true)` | Giảm song song outbound trong session đó |
| Giữ thứ tự side effect trong một reactive sequence | `concatMap` | Các publisher con được xử lý tuần tự, giảm concurrency |
| Giữ thứ tự output nhưng cho phép xử lý publisher con đồng thời | `flatMapSequential` | Có thể phải buffer kết quả; side effect vẫn có thể hoàn tất khác thứ tự |
| Giữ thứ tự event của từng đơn hàng/tài khoản | Sequence/version theo aggregate và consumer tuần tự theo key | Cần lưu sequence, deduplicate, xử lý gap và quản lý concurrency |
| Giữ thứ tự toàn cục giữa mọi message | Một luồng tuần tự hoặc cơ chế total ordering riêng | Throughput thấp, dễ tạo điểm nghẽn; thường không cần thiết |

Trước khi bật một cơ chế ordering, hãy xác định phạm vi cần bảo vệ. Nếu chỉ cần thứ tự theo đơn hàng, giữ thứ tự toàn cục là quá mức. Nếu cần client thấy message theo thứ tự server publish, sequence nghiệp vụ ở database không tự giải quyết việc executor outbound gửi sai thứ tự; cần cả cấu hình transport phù hợp.

## 7. Quy trình điều tra khi thấy message sai thứ tự

1. **Xác định định nghĩa nghiệp vụ.** Event nào phải đứng trước event nào? Phạm vi là một aggregate, một session, một người dùng hay toàn hệ thống?
2. **Ghi lại các mốc thời gian và sequence.** Log `eventId`, `aggregateId`, `sequence`, `occurredAt`, thời điểm publish, receive, handler start/end và commit. Dùng sequence để kiểm tra nghiệp vụ; timestamp giúp quan sát latency.
3. **Tìm nơi thứ tự bắt đầu lệch.** So sánh producer output, broker enqueue/partition, consumer receive, handler completion và database commit.
4. **Kiểm tra concurrency.** Xem executor size, số consumer, số subscription, reactive operator (`flatMap`, `concatMap`) và số connection/session.
5. **Kiểm tra retry và duplicate.** Một event cũ có thể được redeliver sau event mới. Đối chiếu event id, attempt count, retry delay và dead-letter/replay path.
6. **Kiểm tra STOMP nếu có WebSocket.** Xác định cần giữ thứ tự inbound hay outbound; xem `setPreserveReceiveOrder` và `setPreservePublishOrder` đã được bật đúng nơi chưa.
7. **Kiểm tra state transition.** Consumer có kiểm tra `sequence == lastAppliedSequence + 1` trước khi commit không? Sequence và side effect có cập nhật nguyên tử không?
8. **Kiểm thử tình huống xấu.** Gửi event 1, 3, 2; gửi lại event 2; làm chậm handler của event 1; restart consumer giữa commit và ACK. Xác nhận trạng thái cuối đúng và không có side effect trùng.

## 8. Những hiểu nhầm thường gặp

- **“TCP/WebSocket giữ thứ tự nên ứng dụng luôn đúng thứ tự.”** TCP giữ thứ tự byte trong một connection; executor, nhiều session, nhiều consumer và commit bất đồng bộ vẫn có thể làm lệch thứ tự xử lý.
- **“Bật `setPreservePublishOrder` là đã giữ business order.”** Cờ này giữ thứ tự publish tới cùng STOMP session; nó không xác minh sequence nghiệp vụ.
- **“Message timestamp mới hơn thì phải xử lý sau.”** Timestamp không phải sequence logic, có thể lệch đồng hồ và không mô tả quan hệ nhân quả.
- **“`flatMapSequential` khiến side effect tuần tự.”** Operator giữ thứ tự phát output, nhưng có thể chạy publisher con đồng thời.
- **“Message gửi thành công nghĩa là nghiệp vụ đã commit.”** Kết quả `send` ở một tầng chỉ nói về tầng đó. Muốn xác nhận nghiệp vụ cần ACK/reply hoặc trạng thái bền vững theo hợp đồng ứng dụng.
- **“Một consumer duy nhất giải quyết mọi vấn đề.”** Nó có thể tạo nút thắt toàn cục và vẫn không giải quyết producer phát sai thứ tự, duplicate hoặc retry.
- **“Exactly-once delivery tự giải quyết ordering.”** Delivery guarantee và ordering là hai thuộc tính khác nhau. Hệ thống vẫn cần sequence, idempotency và transaction phù hợp.

## 9. Ghi nhớ

- Thứ tự nghiệp vụ do domain định nghĩa; thứ tự giao nhận do các tầng kỹ thuật tạo ra.
- Phân biệt publish, receive, handling, completion và commit order trước khi nói một luồng đã giữ thứ tự.
- Spring STOMP có `setPreserveReceiveOrder` (từ 6.1) và `setPreservePublishOrder` (từ 5.1), đều giới hạn theo cùng client session.
- Reactor `concatMap` tuần tự hóa publisher con; `flatMap` cho phép xen kẽ; `flatMapSequential` giữ thứ tự output nhưng vẫn xử lý publisher con đồng thời.
- Dùng sequence/version theo aggregate để consumer phát hiện duplicate và gap; không dùng timestamp thay thế.
- Kết hợp partition/order key, transactional outbox, deduplication, transaction và replay để bảo vệ thứ tự trong hệ thống phân tán.

## Tài liệu tham khảo

- [Spring Framework Reference — Order of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework Reference — Flow of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework API — MessageBrokerRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework API — StompEndpointRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Reactor Core API — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)