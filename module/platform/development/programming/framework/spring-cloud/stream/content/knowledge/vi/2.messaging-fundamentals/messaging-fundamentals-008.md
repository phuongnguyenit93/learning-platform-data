# Thông điệp trùng lặp, đến muộn và không đúng thứ tự

Trong một hệ thống xử lý sự kiện, producer gửi message lên broker và consumer xử lý chúng khi có thể. Giữa thời điểm phát và thời điểm xử lý có thể xảy ra lỗi mạng, khởi động lại tiến trình, retry, backlog hoặc thay đổi số lượng consumer. Vì vậy, một message có thể được giao nhiều lần, đến sau một message mới hơn hoặc được xử lý sau một sự kiện xảy ra muộn hơn trong nghiệp vụ.

Đây là những tình huống bình thường cần được dự liệu trong thiết kế messaging. Một ứng dụng Spring Cloud Stream có thể dùng cùng mô hình hàm `Supplier`/`Function`/`Consumer` với Kafka, RabbitMQ hoặc Pulsar, nhưng mỗi broker và binder có ngữ nghĩa giao nhận, định tuyến, xác nhận và thứ tự riêng. Logic nghiệp vụ phải xác định message nào đã được áp dụng, message nào còn thiếu tiền nhiệm và dữ liệu đến muộn được xử lý ra sao.

Bài thuộc chương **Nền tảng truyền tin** của module `SPRING_CLOUD_STREAM`. Mục tiêu là phân biệt ba hiện tượng, hiểu nguồn gốc của chúng, rồi xây dựng consumer an toàn trước trùng lặp, độ trễ và sai thứ tự.

## 1. Phân biệt ba hiện tượng

Ba khái niệm thường bị gộp làm một, nhưng chúng mô tả những vấn đề khác nhau:

| Hiện tượng | Ý nghĩa | Ví dụ |
|---|---|---|
| Message trùng lặp (duplicate) | Cùng một sự kiện được giao hoặc xử lý hơn một lần | Consumer đã cập nhật đơn hàng nhưng tiến trình dừng trước khi broker nhận được xác nhận; broker giao lại message |
| Message đến muộn (late) | Message được xử lý muộn so với thời điểm sự kiện xảy ra hoặc thời hạn nghiệp vụ mong đợi | Sự kiện thanh toán xảy ra lúc 10:00 nhưng chỉ được consumer xử lý lúc 10:08 do backlog |
| Message không đúng thứ tự (out of order) | Các sự kiện có quan hệ thứ tự được xử lý theo thứ tự khác với thứ tự nghiệp vụ | Consumer nhận `OrderShipped` trước `OrderPaid` dù thanh toán xảy ra trước khi giao hàng |

Một message có thể vừa đến muộn vừa không đúng thứ tự. Message trùng lặp cũng có thể đến sau một message mới hơn. Do đó, không thể dùng một biện pháp duy nhất như tăng số lần retry để giải quyết cả ba vấn đề.

Ví dụ, đơn hàng `ORD-42` phát ra ba sự kiện:

```text
Thứ tự nghiệp vụ:
v1 OrderPlaced  ------> v2 PaymentAuthorized ------> v3 OrderShipped

Thứ tự consumer quan sát được:
v1 OrderPlaced  ------> v3 OrderShipped ----------> v2 PaymentAuthorized
                         ^
                         |
                   v1 có thể được giao lại
```

Consumer cần biết `v1`, `v2`, `v3` thuộc cùng đơn hàng và có thứ tự phiên bản. Chỉ dựa vào thời điểm nhận message sẽ không đủ để kết luận sự kiện nào đúng trước.

## 2. Vì sao message có thể bị giao nhiều lần?

Trong mô hình giao nhận at-least-once, broker hoặc framework cố gắng giao message cho đến khi nhận được xác nhận theo cơ chế tương ứng. Điều này giảm nguy cơ mất message, nhưng có thể tạo ra bản giao lặp. Một số nguyên nhân phổ biến:

- Consumer đã thực hiện nghiệp vụ nhưng bị dừng trước khi xác nhận message. Khi consumer khởi động lại hoặc quyền sở hữu partition/queue được chuyển giao, message có thể được giao lại.
- Xác nhận bị thất lạc trên đường truyền. Broker không biết consumer đã xử lý thành công nên tiếp tục giao message.
- Producer gửi lại sau timeout vì không nhận được xác nhận từ broker, trong khi lần gửi trước thực tế đã được ghi nhận.
- Cấu hình retry, redelivery hoặc thao tác phát lại từ dead-letter queue (DLQ) khiến cùng một sự kiện quay lại luồng xử lý.
- Tiến trình chuyển tiếp transactional outbox gửi lại một bản ghi chưa được đánh dấu đã phát, dù lần phát trước có thể đã đến broker.

Hãy xét tình huống consumer cập nhật số lượng tồn kho bằng cách trừ 1:

1. Consumer nhận `InventoryReserved`.
2. Database đã giảm tồn kho từ 20 xuống 19.
3. Tiến trình dừng trước khi broker nhận được xác nhận.
4. Broker giao lại cùng message.
5. Consumer giảm tồn kho lần nữa, kết quả thành 18.

Broker đã thực hiện hành vi giao lại phù hợp với cơ chế bảo đảm giao nhận. Lỗi nằm ở chỗ nghiệp vụ không nhận diện được sự kiện đã áp dụng. Consumer cần có tính idempotent: xử lý lại cùng một sự kiện không làm thay đổi kết quả nghiệp vụ lần thứ hai.

## 3. At-most-once, at-least-once và exactly-once

Các thuật ngữ này mô tả số lần một message hoặc hiệu ứng xử lý có thể xuất hiện trong một phạm vi bảo đảm nhất định:

| Cơ chế | Đặc điểm | Đánh đổi |
|---|---|---|
| At-most-once | Message được giao hoặc xử lý không quá một lần theo phạm vi cấu hình | Có thể mất message nếu xác nhận trước khi xử lý xong và tiến trình gặp sự cố |
| At-least-once | Message được thử giao cho đến khi đạt điều kiện xác nhận | Có thể giao lặp; consumer phải xử lý trùng lặp an toàn |
| Exactly-once | Hiệu ứng được bảo đảm đúng một lần trong phạm vi hệ thống hỗ trợ | Phạm vi thường bị giới hạn bởi broker, giao dịch và cách tích hợp; không tự động bao phủ mọi hệ thống bên ngoài |

Không nên hiểu exactly-once là một message chỉ đi qua mạng đúng một lần. Một hệ thống có thể giao message nhiều lần nhưng dùng transaction hoặc cơ chế khử trùng lặp để bảo đảm kết quả cuối cùng chỉ được ghi nhận một lần trong một phạm vi nhất định. Nếu consumer vừa cập nhật database vừa gọi một API thanh toán bên ngoài, giao dịch của broker thường không tự động bao trùm cả hai thao tác.

Vì thế, thiết kế thực tế thường kết hợp at-least-once với consumer idempotent. Cách này cho phép hệ thống phục hồi sau lỗi mà không biến một lần giao lại thành một lần thực hiện nghiệp vụ mới.

## 4. Nhận diện sự kiện bằng định danh ổn định

Mỗi sự kiện nghiệp vụ nên có một `eventId` ổn định, được tạo khi sự kiện được hình thành và được giữ nguyên qua mọi lần retry hoặc replay. Ngoài ra, một sự kiện thường cần định danh đối tượng nghiệp vụ, phiên bản và thời điểm xảy ra:

```json
{
  "eventId": "7f4bcb2a-4f75-4d6b-ae61-1b3a6c2b1a70",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 1,
  "aggregateId": "ORD-42",
  "aggregateVersion": 2,
  "occurredAt": "2026-11-24T03:00:00Z",
  "correlationId": "checkout-9d81",
  "amount": 1250000,
  "currency": "VND"
}
```

Các trường có vai trò khác nhau:

- `eventId` nhận diện một lần phát sinh sự kiện. Consumer dùng nó để phát hiện cùng một sự kiện được giao lại.
- `aggregateId` xác định đối tượng mà chuỗi sự kiện mô tả, chẳng hạn mã đơn hàng.
- `aggregateVersion` hoặc `sequenceNumber` biểu thị thứ tự sự kiện trong phạm vi một đối tượng. Nó giúp phát hiện sự kiện cũ, sự kiện trùng và khoảng trống trong chuỗi.
- `occurredAt` ghi thời điểm nghiệp vụ xảy ra, thường chuẩn hóa về UTC. Đây không nhất thiết là thời điểm broker nhận message.
- `schemaVersion` cho biết phiên bản cấu trúc payload để consumer áp dụng quy tắc tương thích phù hợp.
- `correlationId` liên kết các message thuộc cùng một luồng xử lý, hữu ích khi truy vết qua nhiều dịch vụ.

Không dùng timestamp làm định danh duy nhất. Hai sự kiện có thể có cùng timestamp, đồng hồ giữa các máy có thể lệch và độ chính xác của thời gian không đủ để biểu diễn thứ tự tuyệt đối. `eventId` và số thứ tự theo aggregate giải quyết hai nhu cầu riêng biệt.

## 5. Xây dựng consumer idempotent

Một cách phổ biến là dùng **inbox table** để lưu những event ID đã được xử lý. Bảng này có ràng buộc duy nhất trên `event_id`. Trong cùng giao dịch database, consumer kiểm tra hoặc ghi nhận event ID và cập nhật dữ liệu nghiệp vụ. Nếu message được giao lại, consumer nhận ra nó đã có trong inbox và bỏ qua hiệu ứng lặp.

Ví dụ cấu trúc dữ liệu:

```sql
CREATE TABLE processed_message (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    processed_at   TIMESTAMP NOT NULL
);
```

Phần xử lý nghiệp vụ có thể được tổ chức như sau. Các repository là abstraction của ứng dụng; `findByIdForUpdate` cần khóa bản ghi aggregate trong giao dịch hoặc dùng cơ chế kiểm soát đồng thời tương đương.

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

record OrderEvent(
    UUID eventId,
    String orderId,
    long version,
    String eventType,
    Instant occurredAt
) {}

@Service
class OrderEventHandler {

    private final ProcessedMessageRepository processedMessages;
    private final OrderRepository orders;

    OrderEventHandler(
            ProcessedMessageRepository processedMessages,
            OrderRepository orders) {
        this.processedMessages = processedMessages;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderEvent event) {
        if (processedMessages.existsById(event.eventId())) {
            return;
        }

        Order order = orders.findByIdForUpdate(event.orderId())
            .orElseThrow();

        if (event.version() <= order.getVersion()) {
            // Sự kiện cũ hoặc đã được phản ánh trong trạng thái hiện tại.
            processedMessages.save(event.eventId(), event.orderId());
            return;
        }

        if (event.version() != order.getVersion() + 1) {
            throw new MissingPredecessorException(
                "Missing event before version " + event.version());
        }

        order.apply(event);
        processedMessages.save(event.eventId(), event.orderId());
    }
}
```

Ví dụ này minh họa nguyên tắc, không phải bộ repository có thể chạy độc lập. Trong triển khai thật:

- Ghi inbox và cập nhật aggregate phải nằm trong cùng transaction database. Nếu cập nhật nghiệp vụ commit nhưng ghi inbox không commit, message được giao lại vẫn có thể gây hiệu ứng lặp.
- `event_id` cần unique ở database. Kiểm tra `existsById` đơn thuần có thể gặp race condition khi hai luồng đồng thời xử lý cùng một event; ràng buộc duy nhất và xử lý xung đột là lớp bảo vệ cuối.
- Khóa hoặc optimistic locking phải bảo vệ cập nhật cùng aggregate khi nhiều message được xử lý đồng thời.
- Cần xác định thời gian lưu inbox. Nếu xóa dấu vết quá sớm, một lần replay lịch sử có thể làm nghiệp vụ chạy lại.

Nếu consumer gọi dịch vụ bên ngoài như cổng thanh toán hoặc nhà cung cấp email, transaction database không thể tự hoàn tác tác động bên ngoài. Hãy truyền một idempotency key ổn định nếu API đích hỗ trợ, hoặc ghi yêu cầu gửi đi vào outbox để một tiến trình khác thực hiện và theo dõi kết quả. Với thao tác không thể lặp an toàn, cần có quy trình đối soát và xử lý thủ công khi trạng thái không rõ ràng.

## 6. Phát hiện message cũ, mới và bị thiếu

`aggregateVersion` cho phép consumer so sánh sự kiện với trạng thái đã lưu:

| Điều kiện | Diễn giải | Hướng xử lý thường dùng |
|---|---|---|
| `event.version` nhỏ hơn hoặc bằng phiên bản hiện tại | Sự kiện cũ, trùng hoặc đã được phản ánh | Kiểm tra event ID; nếu trạng thái đã bao hàm phiên bản đó thì bỏ qua hiệu ứng lặp và ghi nhận đã xử lý |
| `event.version` bằng phiên bản hiện tại cộng một | Sự kiện kế tiếp đúng chuỗi | Áp dụng sự kiện và tăng phiên bản trong cùng transaction |
| `event.version` lớn hơn phiên bản hiện tại cộng một | Có khoảng trống, thiếu sự kiện tiền nhiệm | Chờ có giới hạn, lưu tạm, yêu cầu phát lại hoặc đồng bộ lại trạng thái; không âm thầm bỏ qua khoảng trống |

Ví dụ consumer đang ở phiên bản 4 nhưng nhận phiên bản 6. Nếu áp dụng ngay phiên bản 6, trạng thái có thể bỏ qua thay đổi ở phiên bản 5. Nếu nghiệp vụ yêu cầu mọi chuyển đổi đều phải được thực hiện, consumer cần chờ hoặc khôi phục sự kiện còn thiếu. Nếu message là một snapshot đầy đủ và phiên bản mới hơn thay thế hoàn toàn trạng thái cũ, có thể áp dụng quy tắc khác; hợp đồng sự kiện phải nói rõ điều đó.

Không phải lúc nào cũng nên ném lỗi để retry vô hạn. Nếu message phiên bản 6 chặn partition trong khi phiên bản 5 nằm phía sau cùng partition, việc retry tại chỗ có thể khiến phiên bản 5 không bao giờ được xử lý. Tùy broker và luồng nghiệp vụ, có thể lưu phiên bản 6 vào bảng pending, chuyển nó sang luồng retry có thời hạn, hoặc yêu cầu producer phát lại từ nguồn sự thật. Khi phiên bản 5 đến, consumer xử lý lại các phiên bản đang chờ theo thứ tự.

## 7. Message đến muộn và thời gian sự kiện

Một message có ít nhất ba mốc thời gian cần phân biệt:

- **Event time:** thời điểm sự kiện thực sự xảy ra trong nghiệp vụ, thường được producer ghi vào `occurredAt`.
- **Ingestion time:** thời điểm broker hoặc hệ thống streaming tiếp nhận message.
- **Processing time:** thời điểm consumer thực sự bắt đầu hoặc hoàn tất xử lý message.

Ví dụ, một thiết bị ghi nhận nhiệt độ lúc 10:00 nhưng mất kết nối và gửi dữ liệu lúc 10:12. Event time là 10:00, ingestion time là 10:12 và processing time có thể là 10:12:03. Nếu báo cáo chỉ nhóm theo processing time, dữ liệu sẽ xuất hiện ở khoảng 10:12 dù nó mô tả điều đã xảy ra lúc 10:00.

Message đến muộn có thể do producer ngoại tuyến, broker có backlog, consumer thiếu năng lực xử lý, retry kéo dài, DLQ được phát lại hoặc mạng bị gián đoạn. Trong hệ thống phân tích theo cửa sổ thời gian, một sự kiện có event time cũ có thể đến sau khi cửa sổ tương ứng đã được tính toán.

Với xử lý theo event time, hệ thống streaming thường dùng khái niệm watermark để ước lượng mức độ hoàn tất của dữ liệu theo thời gian sự kiện. Cửa sổ có thể cho phép một khoảng trễ (grace period) để nhận dữ liệu đến muộn. Sau thời hạn đó, hệ thống có thể bỏ qua sự kiện, cập nhật kết quả đã công bố hoặc phát ra một bản hiệu chỉnh tùy yêu cầu nghiệp vụ. Watermark là ước lượng tiến độ dữ liệu, không phải bằng chứng rằng sẽ không bao giờ có message cũ hơn.

Với nghiệp vụ trực tuyến, chính sách đến muộn có thể khác xử lý phân tích. Ví dụ, một sự kiện `PaymentAuthorized` đến muộn sau khi đơn hàng đã bị hủy cần được xử lý theo quy tắc bù trừ hoặc hoàn tiền, chứ không chỉ bỏ qua vì timestamp cũ. Thời điểm xảy ra giúp giải thích lịch sử; trạng thái hiện tại và quy tắc chuyển trạng thái quyết định hành động hợp lệ.

## 8. Vì sao thứ tự message có thể thay đổi?

Broker thường chỉ bảo đảm thứ tự trong một phạm vi cụ thể. Thứ tự toàn cục trên toàn bộ topic, queue hoặc subscription có thể không tồn tại khi hệ thống chia partition, dùng nhiều consumer hoặc retry message lỗi.

Các nguyên nhân thường gặp gồm:

1. Producer gửi song song nhiều message, khiến thứ tự gửi và thứ tự broker ghi nhận khác nhau.
2. Message được chia sang các partition hoặc queue khác nhau; mỗi luồng có thứ tự riêng.
3. Nhiều consumer xử lý đồng thời, nên message nhận trước có thể hoàn tất sau message nhận sau.
4. Message lỗi được retry hoặc requeue trong khi message mới hơn tiếp tục được xử lý.
5. Consumer group rebalance hoặc thay đổi số instance làm quyền xử lý được chuyển sang consumer khác.
6. Producer hoặc consumer bất đồng bộ hóa việc gửi, nhận và ghi dữ liệu mà không giữ thứ tự theo aggregate.

### Thứ tự theo broker

| Broker | Phạm vi thứ tự cần lưu ý | Hệ quả thiết kế |
|---|---|---|
| Kafka | Thứ tự được bảo đảm trong một partition; không có thứ tự tổng thể giữa các partition | Dùng key ổn định như `orderId` để các sự kiện của cùng đơn hàng đi vào cùng partition; xử lý song song giữa các partition |
| RabbitMQ | Một queue có thứ tự giao nhận cơ bản, nhưng nhiều consumer, prefetch, redelivery, priority và requeue có thể làm thứ tự xử lý hoàn tất khác thứ tự ban đầu | Nếu cần thứ tự chặt, giới hạn consumer song song cho luồng đó hoặc phân luồng theo aggregate và tuần tự hóa cập nhật |
| Pulsar | Thứ tự phụ thuộc loại subscription, partition và key; các subscription chia tải có thể xử lý song song | Chọn subscription phù hợp; dùng ordering key hoặc Key_Shared với cấu hình producer tương thích khi cần giữ thứ tự theo key |

Ngay cả khi broker giao message theo thứ tự, ứng dụng vẫn có thể phá vỡ thứ tự nếu nhận message rồi đưa công việc vào một thread pool bất đồng bộ không có điều phối theo key. Bảo đảm thứ tự phải đi xuyên suốt từ producer, broker, binder đến consumer và database.

### Consumer group và mức song song

Consumer group cho phép nhiều instance cùng chia tải của một luồng đầu vào. Với Kafka, trong một consumer group, một partition tại một thời điểm được gán cho một consumer; số partition giới hạn mức song song tiêu thụ của group. Các group khác nhau có thể đọc cùng topic độc lập. RabbitMQ và Pulsar có mô hình chia tải/subscription riêng, dù Spring Cloud Stream cung cấp abstraction group tương tự.

Tăng concurrency có thể tăng throughput, nhưng không tự động giữ thứ tự nghiệp vụ. Nếu các sự kiện cùng một aggregate được xử lý ở nhiều luồng mà không khóa hoặc kiểm tra phiên bản, cập nhật có thể ghi đè lẫn nhau. Hãy chọn mức song song theo đơn vị có thể xử lý độc lập, thường là giữa các aggregate khác nhau.

## 9. Giữ thứ tự theo aggregate

Khi thứ tự quan trọng, hãy xác định rõ **đơn vị cần có thứ tự**. Trong hệ thống đặt hàng, các sự kiện của một đơn hàng cần theo thứ tự; hai đơn hàng khác nhau có thể xử lý song song. Từ đó:

1. Gắn `aggregateId` và `aggregateVersion` vào từng sự kiện.
2. Dùng `aggregateId` làm partition key, routing key hoặc ordering key theo khả năng broker.
3. Cấu hình consumer để các message của cùng key không bị xử lý song song theo cách làm đảo thứ tự.
4. Dùng kiểm tra phiên bản hoặc optimistic locking tại database để phát hiện cập nhật sai thứ tự.
5. Xác định cách xử lý khi thiếu một phiên bản và cách khôi phục sau retry hoặc replay.

Với Kafka, producer có thể định tuyến các message cùng key đến cùng partition. Tuy nhiên, việc tăng hoặc thay đổi số partition có thể làm cách ánh xạ key thay đổi tùy partitioner; cần lên kế hoạch khi mở rộng topic nếu thứ tự lịch sử theo key là yêu cầu nghiêm ngặt. Với RabbitMQ, routing key chỉ quyết định định tuyến theo cấu hình exchange; muốn gom một aggregate vào một luồng tuần tự cần topology và consumer phù hợp. Với Pulsar, ordering key và loại subscription phải được chọn cùng nhau.

Ví dụ cấu hình binding đầu vào của Spring Cloud Stream:

```yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-in-0:
          destination: orders.events
          group: inventory-projection
          consumer:
            concurrency: 3
```

`group` xác định nhóm consumer theo abstraction của Spring Cloud Stream. `concurrency` yêu cầu binder tạo mức xử lý song song phù hợp với khả năng của nó. Đoạn cấu hình này không tự tạo thứ tự theo `orderId`, cũng không có nghĩa một aggregate được bảo vệ khỏi xử lý đồng thời. Việc phân vùng producer, key expression, routing hoặc ordering key và các tùy chọn giao nhận cụ thể được cấu hình theo binder đang dùng.

## 10. Ví dụ consumer Spring Cloud Stream

Một hàm `Consumer` có thể nhận `Message<OrderEvent>` để đọc payload và headers. Phần nghiệp vụ được chuyển sang một service riêng để transaction database có ranh giới rõ ràng:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderEventConsumerConfiguration {

    @Bean
    Consumer<Message<OrderEvent>> orderEvents(OrderEventHandler handler) {
        return message -> {
            OrderEvent event = message.getPayload();
            handler.handle(event);
        };
    }
}
```

Binding mặc định của hàm là `orderEvents-in-0`, có thể nối với destination và group trong cấu hình. Khi binder xác định việc xử lý đã thành công hay thất bại, nó áp dụng cơ chế xác nhận, retry hoặc chuyển lỗi theo cấu hình và khả năng broker. Chi tiết acknowledgement và DLQ khác nhau giữa Kafka binder, Rabbit binder và Pulsar binder; không nên sao chép một cấu hình lỗi của binder này sang binder khác.

Một số nguyên tắc khi triển khai consumer:

- Để hàm kết thúc thành công sau khi nghiệp vụ đã commit. Nếu xác nhận message trước khi dữ liệu được lưu, sự cố có thể làm mất hiệu ứng cần thiết.
- Nếu xử lý thất bại tạm thời, dùng retry có giới hạn và backoff; tránh retry dồn dập làm tăng tải.
- Nếu message không thể xử lý do dữ liệu sai hoặc schema không tương thích, chuyển đến DLQ hoặc luồng cách ly theo chính sách để điều tra.
- Khi phát lại DLQ, giữ nguyên `eventId`, `aggregateId`, phiên bản và event time. Replay là lần giao lại của sự kiện cũ, không phải một sự kiện nghiệp vụ mới.
- Tránh thực hiện công việc lâu trong thread nhận message nếu điều đó làm giữ partition hoặc consumer quá lâu. Nếu tách xử lý bất đồng bộ, phải có cơ chế giới hạn và giữ thứ tự theo key khi cần.

## 11. Retry, DLQ và nguy cơ đảo thứ tự

Retry giải quyết lỗi có khả năng tự phục hồi như timeout ngắn hoặc dịch vụ phụ thuộc tạm thời không khả dụng. DLQ cô lập message không thể xử lý sau chính sách thử lại. Hai cơ chế này ảnh hưởng trực tiếp đến thứ tự:

- Retry tại chỗ có thể giữ luồng xử lý ở message lỗi. Điều này giúp không vượt qua message lỗi trong một số cấu hình, nhưng có thể chặn các message khác cùng partition hoặc queue.
- Requeue hoặc retry qua topic/queue khác có thể cho phép message mới hơn đi tiếp trước message đang lỗi.
- DLQ tách message ra khỏi luồng chính. Khi message được sửa và phát lại sau đó, nó có thể đến sau nhiều phiên bản mới hơn.

Vì vậy, cần phân loại lỗi. Lỗi tạm thời có thể retry với số lần và thời gian chờ giới hạn. Lỗi dữ liệu hoặc vi phạm hợp đồng thường cần DLQ và can thiệp. Lỗi thiếu phiên bản tiền nhiệm cần cơ chế chờ hoặc đồng bộ lại, không nên bị coi như lỗi hạ tầng thông thường.

Trước khi replay, hãy xác định consumer có thể xử lý sự kiện cũ mà không làm lùi trạng thái hay không. Có thể dùng version check, inbox và quy trình phát lại theo aggregate. Nếu message bị bỏ qua vì trạng thái đã tiến xa hơn, cần ghi nhận lý do để phục vụ audit.

## 12. Kiểm thử các tình huống bất thường

Một bài kiểm thử chỉ gửi một message thành công chưa đủ chứng minh consumer an toàn. Hãy tạo các kịch bản có chủ đích:

| Kịch bản | Cách mô phỏng | Kết quả cần xác minh |
|---|---|---|
| Giao cùng message hai lần | Gửi hai bản có cùng `eventId` | Dữ liệu nghiệp vụ chỉ thay đổi một lần |
| Dừng sau khi commit nhưng trước xác nhận | Ngắt consumer tại ranh giới phù hợp rồi cho broker giao lại | Consumer nhận ra bản giao lại và không lặp hiệu ứng |
| Message cũ đến sau | Gửi phiên bản 3 sau khi trạng thái đã ở phiên bản 4 | Trạng thái không bị lùi; sự kiện được đánh dấu hoặc xử lý theo chính sách |
| Thiếu phiên bản | Gửi phiên bản 6 khi consumer đang ở phiên bản 4 | Consumer phát hiện khoảng trống và đi theo quy trình chờ/khôi phục |
| Đến muộn sau khi cửa sổ đóng | Gửi event time cũ sau watermark hoặc grace period đã cấu hình | Kết quả được bỏ qua, hiệu chỉnh hoặc cách ly đúng chính sách |
| Retry và DLQ | Làm handler thất bại liên tiếp rồi phát lại message | Số lần retry, nội dung DLQ và replay được kiểm soát |
| Tải song song | Gửi nhiều aggregate và nhiều sự kiện cùng aggregate | Các aggregate độc lập chạy song song; thứ tự bắt buộc trong cùng aggregate được giữ |

Kiểm thử tích hợp nên dùng broker thật hoặc môi trường tương thích đủ để xác nhận hành vi của binder, vì mock hàm consumer không kiểm chứng được partition, acknowledgement, redelivery hay subscription semantics. Kiểm thử cũng cần xác nhận cấu hình đang dùng đúng binder và đúng phiên bản dependency của ứng dụng.

## 13. Quan sát và vận hành

Các chỉ số sau giúp phát hiện vấn đề trước khi chúng trở thành sai lệch dữ liệu:

- Số message được xử lý, số lần giao lặp và số event ID bị bỏ qua do đã xử lý.
- Consumer lag hoặc backlog, tuổi của message cũ nhất và độ trễ từ `occurredAt` đến thời điểm xử lý.
- Số lần retry, tỷ lệ lỗi, số message trong DLQ và số lần replay.
- Số sự kiện sai thứ tự, số khoảng trống version và thời gian chờ khôi phục một aggregate.
- Thời gian xử lý, tỷ lệ transaction rollback và xung đột optimistic locking.

Log nên có `eventId`, `aggregateId`, `aggregateVersion` và `correlationId` khi có thể. Không ghi toàn bộ payload nhạy cảm vào log. Khi điều tra, cần phân biệt message bị giao lại với một sự kiện nghiệp vụ mới có nội dung giống nhau.

## 14. Quy trình xử lý đề xuất

Khi thiết kế một consumer Spring Cloud Stream, có thể đi theo trình tự sau:

1. Xác định message đại diện cho sự kiện hay command và quy định `eventId` ổn định.
2. Xác định aggregate, version/sequence và phạm vi cần giữ thứ tự.
3. Chọn broker, binder, group, partition hoặc subscription phù hợp với yêu cầu tải và thứ tự.
4. Làm consumer idempotent bằng inbox, unique constraint hoặc cơ chế lưu dấu tương đương.
5. Đặt cập nhật nghiệp vụ và ghi dấu đã xử lý trong cùng transaction database khi cả hai cùng nằm trong database đó.
6. Xây dựng chính sách cho message cũ, message thiếu tiền nhiệm và message đến muộn theo event time.
7. Cấu hình retry có giới hạn, backoff, DLQ và quy trình replay.
8. Kiểm thử giao lặp, lỗi tại ranh giới xác nhận, tải song song, sai thứ tự và khôi phục dữ liệu.
9. Theo dõi lag, độ trễ, duplicate, version gap, retry và DLQ trong môi trường triển khai.

## 15. Tự kiểm tra

- [ ] Phân biệt được message trùng lặp, message đến muộn và message không đúng thứ tự.
- [ ] Giải thích được vì sao at-least-once có thể giao lại message và vì sao consumer cần idempotent.
- [ ] Biết vai trò của `eventId`, `aggregateId`, `aggregateVersion`, `occurredAt` và `correlationId`.
- [ ] Mô tả được cách inbox table và transaction database ngăn hiệu ứng lặp.
- [ ] Phân biệt event time, ingestion time và processing time.
- [ ] Biết thứ tự được bảo đảm trong phạm vi nào của Kafka, RabbitMQ và Pulsar.
- [ ] Hiểu rằng consumer group và concurrency giúp chia tải nhưng không tự bảo đảm thứ tự nghiệp vụ.
- [ ] Có chính sách retry, DLQ, replay và quan sát cho message lỗi hoặc đến muộn.

## Kết luận

Message trùng lặp, đến muộn và sai thứ tự là những tình huống phải tính đến trong hệ thống bất đồng bộ. `eventId` giúp nhận diện lần phát sinh, inbox và transaction giúp ngăn hiệu ứng lặp, còn aggregate version và key định tuyến giúp phát hiện hoặc giảm sai thứ tự. Event time hỗ trợ xử lý dữ liệu đến muộn, trong khi retry, DLQ và replay cần chính sách rõ ràng để không làm trạng thái nghiệp vụ sai lệch. Spring Cloud Stream cung cấp abstraction thống nhất cho ứng dụng, nhưng bảo đảm cuối cùng vẫn phụ thuộc vào binder, broker và cách consumer thiết kế transaction cùng trạng thái.
