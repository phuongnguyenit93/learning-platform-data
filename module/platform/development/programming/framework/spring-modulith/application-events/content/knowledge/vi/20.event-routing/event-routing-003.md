# Topic và queue

*Định tuyến application event đến đúng nhóm consumer qua broker*

Khi application event vượt khỏi ranh giới của một ứng dụng Spring Modulith, hệ thống cần quyết định thông điệp sẽ đi đến đâu và thành phần nào sẽ nhận nó. Broker thường cung cấp hai cách tổ chức phổ biến là **topic** và **queue**. Topic phù hợp khi một sự kiện cần được nhiều nhóm hệ thống quan tâm độc lập; queue phù hợp khi một công việc cần được phân phối cho một nhóm worker xử lý. Chọn đúng mô hình giúp các module giao tiếp qua hợp đồng ổn định, giảm phụ thuộc trực tiếp và kiểm soát được tải xử lý.

Spring Modulith cho phép đánh dấu application event cần externalize và khai báo target identifier. Phần tích hợp broker ánh xạ target đó thành topic, exchange, queue hoặc destination cụ thể. Vì vậy, thiết kế định tuyến cần thống nhất cả ý nghĩa nghiệp vụ của event lẫn ngữ nghĩa giao nhận mà broker cung cấp.

## 1. Topic và queue giải quyết hai nhu cầu khác nhau

Hãy hình dung module `orders` phát `OrderCompleted`. Hệ thống phân tích cần nhận sự kiện để cập nhật báo cáo, dịch vụ thông báo cần gửi email và module hóa đơn cần tạo chứng từ. Ba bên này xử lý cùng một sự kiện vì các mục đích khác nhau. Mỗi bên nên có luồng nhận độc lập để tốc độ hoặc lỗi của một bên không làm dừng các bên còn lại.

Ngược lại, khi hệ thống cần tạo một tác vụ gửi email, có thể có nhiều worker cùng lấy việc từ một hàng đợi. Mỗi tác vụ chỉ cần được một worker trong nhóm xử lý thành công. Đây là mô hình phân phối công việc.

| Tiêu chí | Topic / publish-subscribe | Queue / competing consumers |
|---|---|---|
| Mục đích | Phát một loại sự kiện đến nhiều nhóm quan tâm | Phân phối công việc cho một nhóm worker |
| Quan hệ nhận | Mỗi subscription hoặc consumer group có luồng nhận riêng | Các consumer cùng đọc một queue và chia nhau message |
| Mở rộng | Thêm subscription hoặc consumer group mới cho một nhu cầu mới | Thêm worker để tăng năng lực xử lý của nhóm |
| Lỗi một bên nhận | Có thể được cô lập theo subscription/group | Thường ảnh hưởng việc xử lý message trong queue đó cho đến khi retry hoặc chuyển tiếp |
| Ví dụ | `orders.completed` cho phân tích, hóa đơn và thông báo | `email.delivery` cho các worker gửi email |

Tên gọi và chi tiết triển khai thay đổi theo broker. Kafka dùng topic và consumer group; RabbitMQ có exchange định tuyến message vào một hoặc nhiều queue. Không nên coi “topic” của Kafka và “topic exchange” của RabbitMQ là cùng một cấu trúc vật lý.

## 2. Topic: một sự kiện, nhiều luồng tiêu thụ độc lập

Topic thường đại diện cho một luồng sự kiện có cùng chủ đề hoặc hợp đồng. Producer publish message lên topic; các subscription hoặc consumer group nhận luồng đó theo cách độc lập. Ví dụ:

```text
                    +--> consumer group analytics
                    |
orders.completed ---+--> consumer group invoicing
                    |
                    +--> consumer group notifications
```

Trong Kafka, mỗi consumer group có offset riêng. Các consumer trong cùng group chia nhau partition của topic; một message trong một partition được một consumer thuộc group xử lý tại một thời điểm. Một group khác có thể đọc lại cùng message theo offset riêng. Vì vậy, ba nhóm `analytics`, `invoicing` và `notifications` có thể cùng nhận `OrderCompleted` mà không tranh nhau message.

Topic phù hợp khi mỗi nhóm cần tự quyết định tốc độ tiêu thụ, thời điểm xử lý và chính sách retry. Nếu dịch vụ thông báo tạm ngừng, nhóm phân tích vẫn có thể tiếp tục đọc message của nó, miễn là dữ liệu còn trong thời hạn retention và consumer không vượt quá khả năng khôi phục.

Topic không tự bảo đảm mọi consumer đều nhận được message vô thời hạn. Cần cấu hình retention, replication, partition, quyền truy cập và chính sách offset phù hợp. Với Kafka, message thường được giữ theo chính sách lưu trữ của topic thay vì bị xóa ngay khi một consumer đọc xong.

## 3. Queue: phân phối công việc cho các worker

Queue phù hợp với tác vụ mà một nhóm worker cùng chịu trách nhiệm. Ví dụ, ứng dụng tạo yêu cầu gửi email và đẩy message vào queue `email.delivery`. Nhiều worker cùng đọc queue; broker phân phối mỗi message cho một worker, và message được xác nhận sau khi xử lý thành công theo cơ chế của broker.

```text
                 +--> worker 1
email.delivery --+--> worker 2
                 +--> worker 3
```

Trong mô hình competing consumers, các worker chia nhau tải. Khi một worker xử lý chậm hoặc dừng, broker có thể giao lại message chưa được acknowledge theo cấu hình. Điều này tăng khả năng phục hồi nhưng cũng có nghĩa một worker có thể đã thực hiện side effect trước khi mất kết nối và sau đó nhận lại message. Consumer vẫn cần idempotent.

Queue thường có vòng đời message gắn với acknowledgement, retry, dead-letter và chính sách lưu trữ. Cần cấu hình durability, message persistence, visibility/acknowledgement timeout nếu broker hỗ trợ, giới hạn số lần giao và dead-letter queue. Những tùy chọn này là đặc tính broker, không tự được tạo chỉ bằng cách đặt tên target trong application event.

## 4. RabbitMQ: exchange định tuyến vào queue

Trong RabbitMQ, producer thường publish message vào exchange. Exchange áp dụng loại định tuyến và binding để quyết định queue nào nhận message. Một queue có thể nhận từ nhiều binding; một exchange có thể định tuyến message đến nhiều queue.

Các loại exchange thường gặp:

| Exchange | Cách định tuyến | Trường hợp dùng |
|---|---|---|
| Direct | Routing key phải khớp chính xác binding key | Định tuyến theo loại event hoặc nhóm đích cụ thể |
| Topic | Routing key khớp pattern gồm các đoạn phân tách bằng dấu chấm | Định tuyến theo chủ đề và phân cấp, ví dụ `orders.completed` |
| Fanout | Gửi đến mọi queue được bind | Phát cùng thông điệp đến nhiều queue mà không lọc routing key |
| Headers | So khớp theo header của message | Định tuyến dựa trên metadata thay vì routing key |

Với topic exchange, `*` khớp đúng một đoạn và `#` khớp không hoặc nhiều đoạn. Ví dụ binding `orders.*` có thể nhận `orders.completed` hoặc `orders.cancelled`; binding `orders.#` có thể nhận thêm `orders.payment.failed`. Mỗi queue được bind là một luồng nhận độc lập. Nếu ba queue cùng bind với pattern phù hợp, cả ba queue đều có thể nhận một bản message.

```text
Producer
   |
   v
orders.events (topic exchange)
   |-- orders.completed --> queue analytics.events
   |-- orders.completed --> queue invoice.commands
   +-- orders.# ---------> queue audit.events
```

Trong ví dụ, `analytics.events` và `invoice.commands` nhận event hoàn tất đơn hàng; `audit.events` nhận mọi event thuộc họ `orders`. Tên queue mô tả mục đích tiêu thụ, còn routing key mô tả chủ đề message. Giữ hai khái niệm tách biệt giúp thay đổi nhóm consumer mà không buộc producer biết từng queue.

## 5. Kafka: topic, partition và consumer group

Kafka tổ chức message thành các topic có một hoặc nhiều partition. Producer có thể chỉ định key; partitioner dùng key để chọn partition, nhờ đó các message cùng key thường đi vào cùng partition. Kafka bảo toàn thứ tự trong một partition, không bảo đảm thứ tự toàn cục giữa mọi partition.

Consumer group là đơn vị phối hợp đọc topic. Các consumer trong cùng group được chia partition; thông thường mỗi partition chỉ được gán cho tối đa một consumer trong group tại cùng thời điểm. Nếu group có ít consumer hơn số partition, một consumer có thể nhận nhiều partition. Nếu group có nhiều consumer hơn số partition, một số consumer sẽ không được gán partition.

Ví dụ, topic `orders.events` có sáu partition. Group `billing` có ba consumer thì mỗi consumer có thể xử lý hai partition. Group `analytics` có sáu consumer có thể xử lý song song từng partition. Cả hai group vẫn đọc cùng luồng topic theo offset riêng.

Chọn message key theo yêu cầu thứ tự nghiệp vụ. Nếu cần xử lý các thay đổi của cùng một đơn hàng theo thứ tự, `orderId` là key hợp lý. Nếu dùng key ngẫu nhiên, các event của cùng đơn hàng có thể nằm ở nhiều partition và được xử lý song song, làm phức tạp việc dựng trạng thái. Ngược lại, một key có lưu lượng quá lớn có thể tạo hot partition và giới hạn thông lượng.

Consumer group không phải queue vật lý. Nó là cơ chế phối hợp offset và phân công partition trên topic. Mỗi group độc lập có thể đọc cùng message; các consumer trong cùng group chia nhau message theo partition.

## 6. Khai báo ý định định tuyến với Spring Modulith

Trong Spring Modulith, module nghiệp vụ có thể đánh dấu event cần externalize bằng `@Externalized`. Target identifier biểu thị đích logic; integration adapter chịu trách nhiệm diễn giải identifier và gửi message theo cấu hình broker.

```java
import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
    UUID eventId,
    UUID orderId,
    Instant completedAt
) {}
```

Service nghiệp vụ phát event trong transaction:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CompleteOrder {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    CompleteOrder(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    void complete(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.complete();
        events.publishEvent(new OrderCompleted(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
```

Trong ví dụ, `orders.completed` là target identifier được chọn theo quy ước của ứng dụng. Adapter Kafka có thể ánh xạ nó thành topic; adapter RabbitMQ có thể ánh xạ nó thành exchange và routing key, rồi dùng binding để đưa message vào các queue. Đây là ánh xạ ở tầng tích hợp; annotation không tự khai báo partition, consumer group, exchange, queue hay binding.

Giữ module phát event phụ thuộc vào hợp đồng nghiệp vụ và cơ chế publish của Spring. Không đưa tên queue riêng của từng consumer vào service nghiệp vụ, vì điều đó khiến producer phải biết topology vận hành của mọi hệ thống nhận.

## 7. Thiết kế quy ước tên và topology

Tên topic, exchange, routing key và queue nên nhất quán, dễ tìm và phản ánh đúng vai trò:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Event type | `OrderCompleted` | Sự kiện nghiệp vụ đã xảy ra |
| Target logic | `orders.completed` | Đích externalization do ứng dụng quy ước |
| Kafka topic | `orders.events` | Luồng event của đơn hàng |
| Kafka message key | `orderId` | Khóa chọn partition và giữ thứ tự theo đơn hàng |
| Kafka consumer group | `billing` | Nhóm consumer xử lý cho nghiệp vụ hóa đơn |
| Rabbit exchange | `orders.events` | Điểm nhận message để áp dụng routing |
| Rabbit routing key | `orders.completed` | Chủ đề được dùng khi match binding |
| Rabbit queue | `billing.order-completed` | Hàng đợi riêng của consumer hóa đơn |

Không cần tạo một topic hoặc queue cho mọi class event nếu nhiều event thuộc cùng một luồng và có schema tương thích. Ngược lại, không nên dồn mọi loại message không liên quan vào một topic duy nhất nếu chúng có yêu cầu retention, quyền truy cập, thứ tự hoặc tải xử lý rất khác nhau.

Khi quyết định topology, hãy xem xét:

- Số nhóm consumer độc lập và khả năng xuất hiện consumer mới.
- Nhu cầu giữ thứ tự theo aggregate hoặc loại nghiệp vụ.
- Lưu lượng, kích thước message, partition và mức độ song song.
- Retention, replay, acknowledgement, retry và dead-letter.
- Ranh giới bảo mật, quyền publish/subscribe và dữ liệu được phép chia sẻ.
- Cách triển khai schema và thay đổi topology mà không làm gián đoạn consumer hiện tại.

## 8. Transaction, độ tin cậy và xử lý message trùng

Việc publish event cần gắn với transaction nghiệp vụ. Nếu message được gửi trước khi transaction commit, consumer có thể nhìn thấy một thay đổi sau đó bị rollback. Nếu transaction đã commit nhưng ứng dụng dừng trước khi publish, message có thể chưa đến broker. Event publication registry của Spring Modulith hỗ trợ theo dõi publication và xác định công việc giao event còn chưa hoàn tất, tùy theo persistence và integration được cấu hình.

Khi broker hoặc adapter retry, message có thể được giao nhiều lần. Với Kafka, consumer có thể đọc lại sau khi restart hoặc khi offset chưa được commit; với RabbitMQ, message chưa được acknowledge có thể được giao lại. Do đó, consumer nên lưu `eventId` đã xử lý và áp dụng side effect trong cùng transaction:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void handle(OrderCompleted event) {
    if (inbox.existsById(event.eventId())) {
        return;
    }

    billingProjection.recordCompletedOrder(event.orderId());
    inbox.save(new ProcessedEvent(event.eventId()));
}
```

Đặt unique constraint trên `eventId` để bảo vệ trường hợp nhiều worker nhận cùng event đồng thời. Nếu consumer gọi hệ thống bên ngoài, hãy truyền idempotency key hoặc dùng quy trình đối soát; transaction cục bộ không thể bảo đảm side effect ở dịch vụ khác chỉ xảy ra một lần.

Đối với lỗi tạm thời, dùng retry có backoff, jitter và giới hạn số lần thử. Lỗi không thể tự phục hồi như schema không hợp lệ cần chuyển sang dead-letter hoặc hàng chờ điều tra. Tránh retry vô hạn vì một message độc hại hoặc không tương thích có thể chiếm tài nguyên và cản trở các message khác.

## 9. Thứ tự, phân vùng và khả năng mở rộng

Định tuyến message không tự bảo đảm thứ tự nghiệp vụ. Kafka chỉ bảo toàn thứ tự trong một partition; RabbitMQ có thể thay đổi thứ tự quan sát được khi có nhiều consumer, retry, requeue hoặc nhiều queue. Nếu nghiệp vụ yêu cầu thứ tự, cần xác định rõ phạm vi: toàn hệ thống, theo khách hàng, theo đơn hàng hay theo aggregate.

Một cách phổ biến là dùng aggregate ID làm partition key hoặc routing key. Với Kafka, key giúp các event cùng aggregate vào cùng partition. Với RabbitMQ, có thể dùng routing key để đưa event của một aggregate đến một queue hoặc nhóm queue nhất định, nhưng cần thiết kế consumer để không xử lý song song sai thứ tự. Có thể dùng sequence number hoặc aggregate version để phát hiện event đến muộn hoặc bị thiếu.

Mở rộng consumer cũng cần gắn với topology. Tăng số consumer trong Kafka group chỉ tăng song song đến giới hạn số partition. Tăng worker đọc cùng Rabbit queue có thể tăng thông lượng, nhưng cần cân nhắc thứ tự và tải lên hệ thống phụ thuộc. Một queue hoặc partition có lưu lượng lệch lớn có thể trở thành nút thắt.

## 10. Bảo mật và quan sát định tuyến

Broker là ranh giới bảo mật giữa các tiến trình. Chỉ cấp quyền publish cho producer và subscribe cho đúng consumer; dùng TLS và cơ chế xác thực của nền tảng. Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào payload, header hay routing key. Routing key và tên topic thường hiển thị trong công cụ vận hành nên không nên chứa bí mật.

Để điều tra một event không đến đúng nơi, cần theo dõi:

- Event ID, correlation ID và trace ID xuyên suốt producer, broker và consumer.
- Target identifier và destination thực tế được adapter chọn.
- Tỷ lệ publish thành công, lỗi theo destination và tuổi publication đang chờ.
- Kafka: partition, offset, consumer group lag và rebalance.
- RabbitMQ: queue depth, unacknowledged messages, redelivery và dead-letter count.
- Độ trễ từ lúc event xảy ra đến lúc từng consumer hoàn tất xử lý.

Không ghi toàn bộ payload vào log mặc định. Log metadata định tuyến, định danh event và mã lỗi thường đủ để tìm message mà không làm lộ dữ liệu nghiệp vụ.

## 11. Kiểm thử topology và routing

Kiểm thử định tuyến cần chứng minh message đến đúng nhóm nhận và không bị gửi nhầm sang nhóm khác. Các trường hợp nên có:

1. **Target mapping:** event có `@Externalized` được ánh xạ đến đúng topic hoặc exchange theo cấu hình adapter.
2. **Nhiều nhóm nhận:** một event trên topic được các consumer group độc lập nhận; hoặc một message RabbitMQ được route đến tất cả queue có binding phù hợp.
3. **Queue competing consumers:** nhiều worker cùng đọc một queue và chia sẻ tải theo ngữ nghĩa broker.
4. **Routing key:** kiểm tra direct/topic/fanout binding hoặc quy tắc chọn partition key theo các trường hợp thực tế.
5. **Transaction rollback:** publisher rollback thì không phát ra message đại diện cho thay đổi chưa commit.
6. **Retry và duplicate:** mô phỏng lỗi, redelivery hoặc đọc lại và xác nhận consumer idempotent.
7. **Ordering:** phát nhiều event cùng aggregate và xác nhận thứ tự theo phạm vi nghiệp vụ đã chọn.
8. **Quyền truy cập:** producer và consumer chỉ truy cập destination được cấp quyền.

Unit test có thể kiểm tra quy tắc chọn target hoặc routing key. Integration test với broker tương thích cần xác nhận topology, serializer, binding, partition, acknowledgement và quyền truy cập. Mock một adapter không chứng minh cấu hình broker thực tế đúng.

## 12. Quy trình xử lý sự cố

Khi consumer không nhận được event, lần theo đường đi từ producer đến broker rồi đến consumer. Trước tiên xác nhận transaction publisher đã commit và publication được registry ghi nhận. Tiếp theo kiểm tra target identifier, ánh xạ destination, kết nối và quyền publish. Sau đó xác nhận topic hoặc exchange có tồn tại, routing key hoặc binding có khớp, message đã vào broker chưa và consumer có subscribe đúng topic, group hoặc queue không.

Nếu message đã vào broker nhưng chưa được xử lý, xem consumer lag, queue depth, trạng thái worker, offset hoặc acknowledgement và lỗi deserialize. Nếu message bị đưa vào dead-letter, giữ lại event ID và nguyên nhân trước khi quyết định sửa payload hay cấu hình rồi phát lại. Khi replay hoặc resubmit, duy trì event ID để consumer nhận diện bản gửi lại và tránh lặp side effect.

Không xóa queue, reset offset hoặc purge topic như bước xử lý đầu tiên. Những thao tác này có thể làm mất message hoặc khiến consumer xử lý lại lượng dữ liệu lớn. Chỉ thực hiện theo quy trình vận hành có đánh giá phạm vi ảnh hưởng và phương án khôi phục.

## 13. Những điểm cần nhớ

- Topic phù hợp cho publish-subscribe: nhiều nhóm consumer độc lập có thể nhận cùng một luồng event.
- Queue phù hợp cho competing consumers: một nhóm worker chia nhau xử lý công việc.
- Kafka dùng topic, partition và consumer group; RabbitMQ dùng exchange, routing key, binding và queue.
- `@Externalized` khai báo event và target logic; adapter cùng cấu hình broker quyết định destination và routing thực tế.
- Message có thể được giao lại; consumer cần idempotent, retry có giới hạn và có quan sát.
- Chọn key, partition, queue và binding theo yêu cầu thứ tự, tải, retention, bảo mật và khả năng phục hồi.

Khi mô hình topic và queue phản ánh đúng nhu cầu tiêu thụ, target externalization được ánh xạ rõ ràng và consumer có khả năng xử lý lặp an toàn, hệ thống Spring Modulith có thể mở rộng giao tiếp sự kiện qua broker mà vẫn giữ module nghiệp vụ độc lập với topology của các hệ thống nhận.
