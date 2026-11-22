# Thứ tự, trùng lặp, thất lạc và các mức bảo đảm giao nhận

## Mục tiêu

Trong hệ thống messaging, gửi được một message mới chỉ là bước đầu. Hệ thống còn phải xác định message có được lưu bền vững hay không, có thể được giao lại bao nhiêu lần, thứ tự nào được giữ, và điều gì xảy ra khi producer, broker hoặc consumer gặp sự cố.

Sau bài này, bạn có thể:

- Phân biệt thứ tự gửi, thứ tự nhận và thứ tự hoàn tất xử lý.
- Giải thích vì sao một message có thể bị giao trùng hoặc thất lạc.
- Phân biệt at-most-once, at-least-once và exactly-once.
- Hiểu phạm vi bảo đảm của các abstraction trong Spring Messaging.
- Thiết kế consumer idempotent và luồng xử lý có thể phục hồi sau lỗi.

## 1. Spring Messaging bảo đảm điều gì?

Spring Framework cung cấp mô hình message tổng quát để các thành phần trao đổi dữ liệu:

- `Message<T>`: một message gồm payload và headers.
- `MessageHeaders`: metadata như ID, timestamp và các header ứng dụng.
- `MessageChannel`: điểm gửi message.
- `MessageHandler`: thành phần xử lý message.
- `SubscribableChannel`: channel cho phép handler đăng ký nhận message.
- `PollableChannel`: channel cho phép consumer chủ động lấy message.

Ví dụ tạo message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(String eventId, String orderId, long sequence) {}

OrderCreated event = new OrderCreated("evt-42", "order-17", 3);

Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("eventId", event.eventId())
    .setHeader("aggregateId", event.orderId())
    .setHeader("sequence", event.sequence())
    .build();
~~~

Đoạn trên minh họa cách tạo envelope và gắn metadata; nó giả định kiểu OrderCreated đã được khai báo. Các header có thể giúp consumer nhận diện message, nhóm message theo đối tượng nghiệp vụ và kiểm tra thứ tự.

Điểm quan trọng: Spring Messaging định nghĩa abstraction trao đổi message. Bản thân `MessageChannel` không quy định message phải được lưu bền vững, phải được giao đúng một lần, phải được retry, hay phải giữ FIFO. Những hành vi đó phụ thuộc vào channel implementation, broker, adapter và cấu hình ứng dụng.

Một channel trong bộ nhớ của cùng tiến trình có đặc tính khác một queue hoặc topic được broker lưu trữ. Khi tiến trình dừng, message đang nằm trong cấu trúc dữ liệu chỉ tồn tại trong RAM có thể biến mất. Khi dùng Spring AMQP, Spring for Apache Kafka, JMS hoặc Spring Integration, cần đọc chính sách giao nhận của thành phần tương ứng; không thể suy ra chúng chỉ từ kiểu `Message<T>`.

## 2. Ba khái niệm về thứ tự

Cần phân biệt ba mốc:

1. **Thứ tự gửi:** producer tạo hoặc gửi message nào trước.
2. **Thứ tự nhận:** consumer nhìn thấy message nào trước.
3. **Thứ tự hoàn tất:** nghiệp vụ của message nào được commit xong trước.

Ba thứ tự này có thể khác nhau. Ví dụ, producer gửi sự kiện số 1 rồi số 2. Consumer nhận số 1 trước, nhưng xử lý số 1 chậm hơn nên sự kiện số 2 hoàn tất trước. Nếu consumer chạy song song, hiện tượng này rất dễ xảy ra.

### 2.1. Vì sao thứ tự có thể thay đổi?

- Nhiều producer cùng gửi vào một đích đến.
- Broker phân phối message cho nhiều consumer.
- Consumer xử lý bất đồng bộ hoặc dùng thread pool.
- Một message lỗi được retry trong khi message sau đã được xử lý.
- Message được đưa vào dead-letter queue rồi phát lại sau.
- Priority, routing hoặc nhiều partition tạo ra các luồng xử lý riêng.

FIFO ở một queue, nếu broker hỗ trợ và cấu hình đúng, chỉ nói về thứ tự trong phạm vi mà broker định nghĩa. Nó không tự bảo đảm thứ tự hoàn tất nghiệp vụ ở nhiều consumer hoặc thứ tự trên toàn hệ thống.

### 2.2. Giữ thứ tự theo đối tượng nghiệp vụ

Phần lớn hệ thống không cần một thứ tự toàn cục cho mọi message. Yêu cầu thực tế thường là: mọi sự kiện của cùng một đơn hàng, tài khoản hoặc hồ sơ phải được xử lý theo thứ tự; các đối tượng khác nhau vẫn có thể xử lý song song.

Một cách phổ biến:

- Gắn khóa nhóm như `aggregateId` vào message.
- Định tuyến các message cùng khóa vào cùng một partition hoặc luồng tuần tự.
- Giới hạn xử lý đồng thời trong từng luồng nếu thứ tự hoàn tất là bắt buộc.
- Gắn số thứ tự nghiệp vụ tăng dần như `sequence`.
- Consumer kiểm tra số thứ tự để phát hiện message đến muộn hoặc bị thiếu.

Ví dụ với đơn hàng `order-17`, consumer nhận sequence 5 trong khi sequence 4 chưa được xử lý. Consumer có thể tạm giữ message 5, retry, hoặc yêu cầu đối soát dữ liệu. Không nên âm thầm áp dụng sự kiện 5 rồi bỏ qua 4 nếu nghiệp vụ yêu cầu đầy đủ lịch sử.

Với Kafka, thứ tự được duy trì trong một partition; message có cùng key thường được đưa vào cùng partition theo chiến lược phân vùng. Thứ tự giữa các partition không phải một thứ tự toàn cục. Với các broker khác, phạm vi FIFO và cách phân phối cần kiểm tra theo tài liệu của broker.

## 3. Vì sao message bị giao trùng?

Giao trùng thường là hệ quả bình thường của cơ chế phục hồi, đặc biệt khi hệ thống dùng retry hoặc redelivery.

Các tình huống điển hình:

1. Consumer đã thực hiện nghiệp vụ nhưng chết trước khi gửi acknowledgement. Broker không biết nghiệp vụ đã hoàn tất nên giao lại message.
2. Producer gửi message nhưng mất kết nối trước khi nhận được kết quả xác nhận. Producer không biết broker đã nhận hay chưa nên gửi lại.
3. Consumer timeout trong lúc xử lý; broker hoặc adapter xem lần xử lý là thất bại và retry.
4. Ứng dụng chủ động phát lại message để khôi phục dữ liệu hoặc chạy lại một luồng xử lý.
5. Một message được gửi đến nhiều subscriber theo thiết kế pub/sub. Đây là nhiều lần phân phối có chủ đích, không nhất thiết là duplicate.

Ví dụ quan trọng: consumer cập nhật số dư thành công trong database, sau đó mất kết nối trước khi acknowledgement đến broker. Broker giao lại message. Nếu consumer cộng tiền lần nữa, số dư sai dù broker đang thực hiện đúng chính sách giao lại.

### 3.1. Idempotency

Một thao tác là **idempotent** khi thực hiện lặp lại với cùng một định danh đầu vào không làm thay đổi kết quả nghiệp vụ sau lần đầu.

Ví dụ:

- Không an toàn: mỗi lần nhận sự kiện OrderPaid thì cộng thêm 100 vào tổng doanh thu.
- An toàn hơn: ghi nhận sự kiện có eventId đã được áp dụng; nếu eventId xuất hiện lần nữa thì bỏ qua tác động nghiệp vụ.

Để làm được điều này:

- Producer tạo một eventId ổn định khi sự kiện nghiệp vụ được hình thành. Mọi lần retry phải dùng lại ID đó.
- Consumer lưu eventId đã xử lý trong một kho dữ liệu có ràng buộc duy nhất.
- Việc ghi nhận eventId và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction database khi có thể.
- Nếu gọi dịch vụ bên ngoài, truyền idempotency key nếu API đó hỗ trợ.

Không nên mặc định dùng message ID do framework hoặc broker cấp làm định danh nghiệp vụ lâu dài. Một lần tạo message mới hoặc phát lại dữ liệu có thể tạo ID vận chuyển khác. Hãy mang theo ID sự kiện ổn định của domain.

### 3.2. Inbox pattern

Inbox là bảng hoặc kho lưu trữ ghi nhận những message consumer đã áp dụng. Có thể thiết kế bảng với khóa duy nhất trên eventId:

~~~sql
CREATE TABLE processed_messages (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong một transaction:

1. Thử chèn eventId vào bảng inbox.
2. Nếu vi phạm khóa duy nhất, message đã được xử lý; không lặp lại tác động.
3. Nếu chèn thành công, cập nhật dữ liệu nghiệp vụ.
4. Commit cả hai thay đổi cùng lúc.
5. Chỉ acknowledgement message sau khi transaction thành công.

Nếu ứng dụng chết trước commit, cả dấu inbox và cập nhật nghiệp vụ đều rollback. Nếu commit thành công nhưng acknowledgement bị mất, message có thể được giao lại; khóa duy nhất giúp consumer nhận ra lần giao lại và không áp dụng nghiệp vụ lần thứ hai.

## 4. Vì sao message bị thất lạc?

Thất lạc có thể xảy ra ở nhiều chặng: producer, đường truyền, broker, routing, consumer hoặc lúc ghi dữ liệu nghiệp vụ.

| Điểm xảy ra | Ví dụ rủi ro | Biện pháp thường dùng |
|---|---|---|
| Producer | Ứng dụng chết sau khi commit nghiệp vụ nhưng trước khi gửi message | Transactional outbox |
| Gửi đến broker | Mất kết nối trước khi biết broker đã nhận | Publisher confirm và retry với eventId ổn định |
| Broker | Message chỉ nằm trong bộ nhớ hoặc cấu hình lưu trữ không đủ bền vững | Durable destination, persistent message, replication phù hợp |
| Routing | Không có queue/subscriber phù hợp hoặc cấu hình binding sai | Kiểm tra routing, mandatory return hoặc cơ chế tương đương của broker |
| Consumer | Acknowledge trước khi lưu kết quả nghiệp vụ | Acknowledge sau khi transaction nghiệp vụ commit |
| Xử lý lỗi | Retry hết hạn rồi message bị loại bỏ | Dead-letter queue, cảnh báo và quy trình replay |
| Vòng đời message | TTL hết hạn hoặc giới hạn dung lượng khiến message bị loại | Chọn TTL/retention và chính sách overflow phù hợp |

Một channel trong bộ nhớ chỉ phù hợp khi chấp nhận mất message lúc tiến trình dừng hoặc khi dữ liệu có thể được tạo lại. Với dữ liệu nghiệp vụ quan trọng, cần xác định rõ nơi lưu bền vững và cách phục hồi.

### 4.1. Transactional outbox

Có một khoảng trống nguy hiểm nếu ứng dụng làm hai thao tác riêng:

1. Commit thay đổi nghiệp vụ vào database.
2. Gửi event đến broker.

Nếu ứng dụng chết giữa hai bước, database đã đổi nhưng event chưa được gửi. Đảo thứ tự hai thao tác cũng có rủi ro ngược lại: event đã gửi nhưng transaction nghiệp vụ rollback.

Transactional outbox giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng transaction database. Một tiến trình relay đọc outbox rồi gửi đến broker. Sau khi xác nhận gửi thành công, relay đánh dấu bản ghi đã phát.

Relay có thể gửi trùng nếu nó chết sau khi broker nhận message nhưng trước khi đánh dấu outbox hoàn tất. Vì vậy outbox cần kết hợp với eventId ổn định và consumer idempotent. Outbox giúp không bỏ sót ý định phát event đã commit; nó không tự làm cho toàn bộ hệ thống exactly-once.

## 5. Các mức bảo đảm giao nhận

Các thuật ngữ sau mô tả số lần một message có thể được giao trong một phạm vi và theo một giả định lỗi nhất định.

| Mức bảo đảm | Ý nghĩa | Đánh đổi |
|---|---|---|
| **At-most-once** | Message được giao không quá một lần; có thể không được giao lần nào | Tránh giao trùng nhưng có thể mất message |
| **At-least-once** | Hệ thống tiếp tục giao lại cho đến khi đạt điều kiện xác nhận hoặc chính sách dừng | Giảm nguy cơ mất message nhưng consumer phải chịu được duplicate |
| **Exactly-once** | Một message có đúng một tác động trong phạm vi được cơ chế giao dịch bảo vệ | Phạm vi thường bị giới hạn; khó mở rộng qua nhiều hệ thống |
| **Effectively-once** | Message có thể được giao nhiều lần nhưng tác động nghiệp vụ được khử trùng lặp | Cần ID ổn định, idempotency và lưu trạng thái xử lý đúng cách |

### 5.1. At-most-once

Hệ thống không retry hoặc xác nhận message trước khi xử lý. Nếu consumer chết sau khi broker đã loại message nhưng trước khi nghiệp vụ hoàn tất, message bị mất.

Mức này có thể phù hợp với dữ liệu tạm thời, cập nhật trạng thái có thể lấy lại từ nguồn khác, hoặc telemetry mà mất một phần dữ liệu được chấp nhận.

### 5.2. At-least-once

Consumer chỉ xác nhận sau khi xử lý thành công. Nếu consumer chết trước acknowledgement, broker giao lại message. Cách này ưu tiên không bỏ sót, nhưng duplicate là điều phải dự kiến.

Đây là lựa chọn phổ biến cho nghiệp vụ quan trọng khi consumer được thiết kế idempotent. Cần có retry hữu hạn hoặc chính sách backoff, dead-letter queue và cảnh báo để message lỗi không lặp vô hạn.

### 5.3. Exactly-once và giới hạn thực tế

Exactly-once cần được hiểu theo phạm vi cụ thể. Một broker hoặc nền tảng stream có thể hỗ trợ giao dịch để bảo đảm một chuỗi thao tác đọc, xử lý và ghi vào các đích được quản lý bởi cùng cơ chế transaction. Điều đó không tự bảo đảm một email chỉ được gửi một lần, một lời gọi HTTP chỉ xảy ra một lần, hoặc một cập nhật database bên ngoài transaction broker chỉ xảy ra một lần.

Nếu consumer cập nhật database rồi gọi API thanh toán, hai hệ thống thường không cùng một transaction phân tán. Khi lỗi xảy ra giữa hai thao tác, ứng dụng cần idempotency key, outbox/inbox, retry có kiểm soát hoặc quy trình bù trừ. Vì vậy, trong thiết kế ứng dụng, mục tiêu thực tế thường là tạo **tác động nghiệp vụ effectively-once** bằng xử lý idempotent và transaction phù hợp.

## 6. Acknowledgement và retry

Acknowledgement (ack) là tín hiệu consumer gửi để broker biết message đã đạt đến một trạng thái xử lý nhất định. Cần phân biệt:

- **Publisher confirm:** xác nhận từ broker về kết quả tiếp nhận publish theo semantics của broker.
- **Consumer acknowledgement:** consumer xác nhận message đã được xử lý hoặc chấp nhận theo chính sách giao nhận.

Hai cơ chế nằm ở hai đầu khác nhau. Publisher confirm không chứng minh consumer đã xử lý. Consumer ack không chứng minh mọi tác động bên ngoài đã hoàn tất nếu ứng dụng ack quá sớm.

Một trình tự xử lý an toàn thường là:

~~~text
Producer
  -> ghi nghiệp vụ và outbox trong một database transaction
  -> relay publish message
  -> nhận publisher confirm
  -> Broker lưu message theo cấu hình durability
  -> Consumer nhận message
  -> kiểm tra inbox/eventId
  -> cập nhật nghiệp vụ và inbox trong một transaction
  -> commit
  -> Consumer acknowledgement
~~~

Nếu consumer lỗi trước commit, transaction rollback và message có thể được giao lại. Nếu consumer commit xong nhưng ack bị mất, message có thể được giao lại; inbox giúp bỏ qua tác động trùng.

Retry nên có giới hạn và khoảng chờ tăng dần (backoff). Phân loại lỗi:

- Lỗi tạm thời như timeout hoặc dịch vụ phụ thuộc không sẵn sàng: có thể retry.
- Lỗi dữ liệu hoặc schema không hợp lệ: retry thường không giải quyết được; chuyển sang dead-letter để điều tra.
- Lỗi nghiệp vụ có thể cần chờ điều kiện hoặc can thiệp; phải có chính sách rõ ràng.

Dead-letter queue không tự sửa message. Cần theo dõi, xác định nguyên nhân, sửa dữ liệu hoặc code, rồi replay có kiểm soát. Khi replay, phải giữ eventId gốc để cơ chế idempotency tiếp tục hoạt động.

## 7. Áp dụng các nguyên tắc qua Spring

Spring Messaging cung cấp hợp đồng chung để gửi và xử lý message. Ví dụ một handler:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;

public final class OrderCreatedHandler implements MessageHandler {
    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        Object eventId = message.getHeaders().get("eventId");
        Object aggregateId = message.getHeaders().get("aggregateId");

        // Xác thực metadata, sau đó gọi service nghiệp vụ idempotent.
        // Chính sách transaction và acknowledgement phụ thuộc adapter/broker.
    }
}
~~~

Đây là phần triển khai handler, không phải một ứng dụng độc lập có thể chạy ngay. Với một channel, lệnh gửi có thể có dạng:

~~~java
boolean accepted = messageChannel.send(message);
~~~

Giá trị trả về chỉ phải được diễn giải theo hợp đồng của channel đang dùng. Nó không phải bằng chứng chung rằng message đã được broker lưu bền vững hoặc consumer đã xử lý xong.

Khi tích hợp broker:

- Cấu hình publisher confirm/return theo khả năng của broker và adapter.
- Chọn persistent message, durable queue/topic, replication và retention theo yêu cầu khôi phục.
- Chọn acknowledgement mode và thời điểm ack phù hợp.
- Cấu hình retry, backoff, dead-letter và giới hạn số lần giao lại.
- Đặt eventId, aggregateId và sequence vào header hoặc payload theo hợp đồng dữ liệu của ứng dụng.
- Đo lường publish failure, redelivery, retry, độ trễ, message nằm lâu và dead-letter.

Các chi tiết cấu hình khác nhau giữa Spring AMQP, Spring for Apache Kafka, JMS và Spring Integration. Không sao chép một cấu hình ack hoặc retry từ broker này sang broker khác mà không kiểm tra semantics của adapter.

## 8. Ví dụ Java 17: consumer bỏ qua event đã gặp

Ví dụ độc lập dưới đây mô phỏng việc nhận cùng một event hai lần. Nó dùng một Set trong bộ nhớ để minh họa nguyên tắc idempotency; nó không phải cơ chế lưu trạng thái bền vững cho production.

Tệp: `IdempotentConsumerDemo.java`

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

record Event(String id, String type) {}

public class IdempotentConsumerDemo {
    private final Set<String> processedIds = ConcurrentHashMap.newKeySet();

    public void onMessage(Event event) {
        if (!processedIds.add(event.id())) {
            System.out.println("duplicate ignored: " + event.id());
            return;
        }

        applyBusinessEffect(event);
    }

    private void applyBusinessEffect(Event event) {
        System.out.println("processed: " + event.id() + " -> " + event.type());
    }

    public static void main(String[] args) {
        IdempotentConsumerDemo consumer = new IdempotentConsumerDemo();
        Event event = new Event("evt-42", "OrderCreated");

        consumer.onMessage(event);
        consumer.onMessage(event);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac IdempotentConsumerDemo.java
java IdempotentConsumerDemo
~~~

Kết quả stdout:

~~~text
processed: evt-42 -> OrderCreated
duplicate ignored: evt-42
~~~

Lần đầu, Set nhận eventId nên consumer thực hiện tác động. Lần thứ hai, eventId đã tồn tại nên consumer bỏ qua.

Trong ứng dụng thực tế, Set trong bộ nhớ mất dữ liệu khi tiến trình khởi động lại và không chia sẻ giữa nhiều instance. Cũng có một khe lỗi nếu ứng dụng thêm ID vào Set rồi chết trước khi thực hiện tác động nghiệp vụ. Hãy dùng inbox hoặc bảng deduplication bền vững, có khóa duy nhất, và ghi dấu đã xử lý cùng transaction với cập nhật nghiệp vụ.

## 9. Kết hợp bảo đảm theo yêu cầu

| Yêu cầu nghiệp vụ | Thiết kế thường phù hợp |
|---|---|
| Chấp nhận mất một phần dữ liệu, ưu tiên độ trễ thấp | At-most-once, nguồn dữ liệu có thể tái tạo |
| Không muốn bỏ sót event đã commit | Outbox, broker lưu bền vững, publisher confirm |
| Consumer có thể nhận lại message | At-least-once kết hợp inbox/idempotency |
| Giữ thứ tự thay đổi của từng đơn hàng | Partition/routing theo orderId và sequence |
| Phục hồi message lỗi | Retry có giới hạn, dead-letter queue và replay |
| Tác động qua nhiều dịch vụ | Stable eventId, idempotency key, outbox/inbox và quy trình bù trừ |

Không có một cấu hình duy nhất tối ưu cho mọi hệ thống. Cần xác định rõ điều gì quan trọng hơn: không mất dữ liệu, tránh xử lý trùng, giữ thứ tự, throughput hay độ trễ. Một hệ thống có thể giữ thứ tự theo từng aggregate nhưng xử lý song song giữa các aggregate; có thể dùng at-least-once ở tầng vận chuyển và effectively-once ở tầng nghiệp vụ.

## 10. Lỗi thiết kế thường gặp

- Cho rằng gọi `MessageChannel.send()` thành công nghĩa là broker đã lưu message bền vững.
- Dùng auto-ack hoặc ack trước khi transaction nghiệp vụ commit rồi kỳ vọng không mất dữ liệu.
- Retry message nhưng tạo eventId mới ở mỗi lần gửi, khiến consumer không nhận ra duplicate.
- Dùng payload giống nhau để suy luận hai message là một sự kiện; hai sự kiện hợp lệ có thể có payload giống hệt nhau.
- Dùng một consumer chạy song song nhưng giả định thứ tự hoàn tất luôn giống thứ tự nhận.
- Cho rằng FIFO của một queue bảo đảm thứ tự toàn cục qua nhiều queue, partition hoặc consumer.
- Chuyển message lỗi sang dead-letter rồi quên giám sát và quy trình replay.
- Ghi inbox và cập nhật nghiệp vụ ở hai transaction tách rời, tạo ra khe lỗi mới.
- Gọi một luồng là exactly-once mà không nói rõ phạm vi transaction và các hệ thống nằm ngoài phạm vi đó.

## 11. Checklist khi thiết kế

- [ ] Mỗi event nghiệp vụ có eventId ổn định qua mọi lần retry và replay.
- [ ] Đã xác định phạm vi thứ tự: toàn cục, theo partition hay theo aggregate.
- [ ] Có sequence nếu cần phát hiện sự kiện đến sai thứ tự hoặc bị thiếu.
- [ ] Đã chọn at-most-once hay at-least-once theo mức độ chấp nhận mất dữ liệu.
- [ ] Consumer idempotent; dấu inbox và tác động nghiệp vụ được commit cùng nhau khi có thể.
- [ ] Producer có outbox nếu việc phát event phải gắn với transaction nghiệp vụ.
- [ ] Đã cấu hình durability, publisher confirm và consumer acknowledgement theo broker.
- [ ] Retry có giới hạn, backoff và dead-letter queue.
- [ ] Có cảnh báo và quy trình điều tra/replay dead-letter.
- [ ] Theo dõi eventId, correlationId, aggregateId, sequence, số lần retry và độ trễ xử lý.
- [ ] Đã thử các tình huống crash trước commit, sau commit nhưng trước ack, và mất kết nối khi publish.

## 12. Tài liệu tham khảo

- [Spring Framework — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Framework — MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/)
