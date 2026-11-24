# autoBindDlq, dead-letter exchange và dead-letter routing key

Khi một message không thể được xử lý, RabbitMQ cần một đường đi để giữ message lỗi mà không làm consumer lặp lại vô hạn. Cơ chế dead-letter của RabbitMQ thực hiện việc này bằng cách chuyển message từ queue nguồn sang một **dead-letter exchange (DLX)**. Exchange định tuyến message đến **dead-letter queue (DLQ)** dựa trên routing key và binding đã cấu hình.

RabbitMQ Binder của Spring Cloud Stream có thuộc tính `autoBindDlq` để tự khai báo các tài nguyên dead-letter cần thiết cho consumer. `deadLetterExchange` xác định exchange nhận message lỗi; `deadLetterRoutingKey` xác định routing key được dùng khi định tuyến message vào DLQ. Khi cấu hình đúng, binder có thể tạo DLX, DLQ và binding tương ứng, đồng thời cấu hình queue nguồn để dead-letter message sang DLX.

Bài thuộc chương **Độ tin cậy RabbitMQ** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào mô hình hàm `Supplier`/`Function`/`Consumer`, RabbitMQ Binder, retry, reject/nack, dead-letter exchange, dead-letter routing key, provisioning, quyền truy cập, replay và vận hành production.

## 1. Vì sao cần dead-letter flow?

Một consumer có thể nhận message nhưng không thể xử lý do nhiều nguyên nhân:

- Payload không hợp lệ hoặc không thể deserialize.
- Dữ liệu nghiệp vụ thiếu thông tin bắt buộc.
- Dependency tạm thời hoặc liên tục thất bại.
- Handler phát sinh lỗi lập trình.
- Message hết TTL hoặc queue đạt giới hạn độ dài.
- Message bị reject mà không yêu cầu requeue.

Nếu message cứ được requeue và giao lại ngay, consumer có thể rơi vào vòng lặp nóng. Một message lỗi có thể chiếm tài nguyên, tạo log liên tục và làm backlog tăng. Dead-letter flow chuyển message sang một queue riêng để đội vận hành điều tra hoặc replay sau khi nguyên nhân được sửa.

```text
Queue nguồn: orders.events.order-processor
              |
              | message bị reject / hết TTL / vượt giới hạn
              v
Dead-letter exchange: orders.dlx
              |
              | routing key: orders.failed
              v
Dead-letter queue: orders.events.order-processor.dlq
              |
              v
Điều tra / sửa dữ liệu / replay có kiểm soát
```

DLX là exchange nhận message bị dead-letter; DLQ là queue lưu message sau khi exchange định tuyến. Hai tài nguyên này có vai trò khác nhau và đều cần được khai báo đúng.

## 2. Phân biệt các thành phần

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Queue nguồn | Giữ message để consumer chính xử lý | `orders.events.order-processor` |
| Dead-letter exchange (DLX) | Nhận message bị dead-letter từ queue nguồn | `orders.dlx` |
| Dead-letter routing key | Khóa định tuyến message từ DLX đến queue đích | `orders.failed` |
| Dead-letter queue (DLQ) | Lưu message lỗi để điều tra hoặc xử lý lại | `orders.events.order-processor.dlq` |
| Binding | Liên kết DLX với DLQ theo routing key/pattern | `orders.dlx` → `orders.failed` → DLQ |

Producer gửi message vào exchange nguồn. Consumer nhận từ queue nguồn. Khi message bị dead-letter, RabbitMQ dùng cấu hình dead-letter trên queue nguồn để publish message đến DLX. Sau đó DLX áp dụng loại exchange và binding key để tìm queue đích.

Không nhầm `deadLetterExchange` với `deadLetterQueueName`. Exchange định tuyến message; queue mới lưu message. Cũng không nhầm `deadLetterRoutingKey` với routing key ban đầu của producer: đây là routing key được dùng trong dead-letter flow theo cấu hình queue/binder.

## 3. Cách RabbitMQ dead-letter một message

RabbitMQ có thể dead-letter message trong một số trường hợp phổ biến:

1. Consumer reject hoặc nack message với `requeue=false`.
2. Message hết TTL trong queue.
3. Queue vượt giới hạn độ dài hoặc giới hạn dung lượng theo policy/queue arguments.
4. Message đạt delivery limit trong các cấu hình quorum queue hỗ trợ giới hạn giao lại.

Khi queue nguồn được cấu hình `x-dead-letter-exchange`, broker chuyển message đến DLX. Nếu queue có `x-dead-letter-routing-key`, broker sử dụng routing key đó. Nếu không có routing key thay thế, routing key ban đầu có thể được giữ lại trong quá trình dead-lettering.

Việc message bị dead-letter không có nghĩa mọi lỗi trong Java function đều tự động được chuyển sang DLQ. Handler phải kết thúc theo cách khiến binder/broker reject hoặc binder phải chủ động republish message theo cấu hình. Nếu ứng dụng bắt exception rồi trả về bình thường, cơ chế retry/DLQ có thể không được kích hoạt.

## 4. `autoBindDlq` làm gì?

`autoBindDlq` là thuộc tính consumer riêng của RabbitMQ Binder. Khi bật, binder tự khai báo các tài nguyên và cấu hình cần thiết cho dead-letter flow theo các thuộc tính liên quan, thường bao gồm:

- Dead-letter exchange.
- Dead-letter queue.
- Binding từ DLX đến DLQ.
- Dead-letter exchange/routing key arguments trên queue nguồn.

Điều này giúp giảm thao tác khai báo topology thủ công trong môi trường phát triển hoặc khi binder được phép quản lý tài nguyên. Trong production, vẫn cần xác minh quyền configure, durability, queue arguments, exchange type và chính sách provisioning của broker.

Ví dụ cấu hình consumer:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-exchange: orders.dlx
              dead-letter-routing-key: orders.failed
              dead-letter-queue-name: orders.events.order-processor.dlq
              dead-letter-exchange-type: direct
```

Các tên thuộc tính trong YAML dùng kebab-case. Trong Java/configuration metadata, chúng có thể xuất hiện dưới dạng camelCase như `autoBindDlq`, `deadLetterExchange` và `deadLetterRoutingKey`.

Ví dụ đặt tên tường minh giúp topology dễ kiểm tra. Hãy xác nhận các thuộc tính có trong đúng phiên bản Spring Cloud Stream Rabbit binder đang sử dụng; không sao chép namespace Kafka Binder sang RabbitMQ Binder.

Consumer nên khai báo `group` ổn định khi cần queue nguồn và DLQ bền vững. Group giúp binder tạo tên queue gắn với consumer logic và giữ tên tài nguyên ổn định qua restart. Consumer ẩn danh thường dùng queue tạm/ẩn danh; kiểu subscription đó không phù hợp với một dead-letter flow cần lưu message lỗi trong thời gian ứng dụng offline.

Ví dụ function được binding trên:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration
class OrderProcessingConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
```

Nếu `orderService.process` ném exception ra khỏi consumer, binder có thể áp dụng retry/error handling đã cấu hình. Nếu code tự bắt lỗi rồi trả về bình thường, binder không nhìn thấy một lần xử lý thất bại để chuyển sang DLQ.

## 5. `deadLetterExchange` xác định exchange nhận message lỗi

`deadLetterExchange` là tên exchange mà queue nguồn dùng làm đích khi message bị dead-letter. Có thể chọn một DLX riêng cho từng domain hoặc một DLX dùng chung nếu các queue có routing key và quyền truy cập được quản lý rõ ràng.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-exchange: orders.dlx
              dead-letter-exchange-type: direct
```

Khi queue nguồn được khai báo, binder có thể đặt queue argument `x-dead-letter-exchange` trỏ đến `orders.dlx`. Broker dùng exchange này khi cần dead-letter message.

DLX cần tồn tại trong cùng vhost với queue nguồn. Nếu exchange không tồn tại hoặc không có quyền truy cập phù hợp, quá trình dead-letter có thể thất bại. Hãy kiểm tra DLX đã được provision hoặc binder có quyền khai báo nó.

### Chọn exchange type

Loại exchange quyết định cách DLX định tuyến message:

| Exchange type | Hành vi | Khi phù hợp |
|---|---|---|
| `direct` | Routing key phải khớp binding key | Một nhóm message lỗi đi đến một DLQ cụ thể |
| `topic` | Routing key khớp pattern với `*` và `#` | Nhiều loại lỗi/domain được phân tuyến theo pattern |
| `fanout` | Gửi đến mọi queue được bind | Cần phát bản sao tới nhiều queue giám sát/cách ly |
| `headers` | Dựa trên message headers và binding arguments | Định tuyến theo metadata thay vì routing key |

Ví dụ bài học sử dụng `direct` để mapping routing key chính xác và dễ kiểm soát. Nếu đổi exchange type của một exchange đã tồn tại, RabbitMQ có thể từ chối redeclare cùng tên với thuộc tính không tương thích. Hãy thống nhất type giữa binder và hệ thống provisioning.

## 6. `deadLetterRoutingKey` điều khiển đường đi đến DLQ

`deadLetterRoutingKey` chỉ định routing key dùng trong dead-letter flow. Với direct exchange, routing key phải khớp binding key của DLQ. Nếu không khớp, DLX không định tuyến được message đến queue mong muốn.

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-exchange: orders.dlx
              dead-letter-exchange-type: direct
              dead-letter-routing-key: orders.failed
```

Topology tương ứng:

```text
Queue nguồn
  x-dead-letter-exchange = orders.dlx
  x-dead-letter-routing-key = orders.failed
          |
          v
Exchange orders.dlx (direct)
          |
          | binding key = orders.failed
          v
Queue orders.events.order-processor.dlq
```

Với direct exchange, binding key của DLQ phải khớp chính xác `orders.failed`. Với topic exchange, có thể dùng pattern như `orders.#`; cần xác minh routing key thực tế mà binder phát ra và pattern đã khai báo.

Không tự thêm routing key vào tên DLQ hoặc ngược lại. Tên queue và routing key là hai giá trị riêng; chúng chỉ liên hệ thông qua binding.

## 7. Dead-letter queue name

Tên DLQ có thể được cấu hình bằng `deadLetterQueueName`/`dead-letter-queue-name` ở các phiên bản Rabbit binder hỗ trợ. Nếu không chỉ định, binder có quy ước đặt tên dựa trên destination và group. Với production, tên tường minh giúp đội vận hành dễ quản lý và provision.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-queue-name: orders.events.order-processor.dlq
```

Nếu nhiều consumer group cùng đọc một destination, mỗi group thường cần DLQ riêng để tránh trộn message lỗi từ các ứng dụng có logic và schema khác nhau. Nếu chủ động dùng chung DLQ, cần có metadata phân biệt source destination, group và loại message, đồng thời thống nhất quy trình replay.

## 8. `autoBindDlq` và `republishToDlq`

Hai thuộc tính này liên quan nhưng không đồng nghĩa:

- `autoBindDlq` yêu cầu binder tự khai báo dead-letter topology theo cấu hình.
- `republishToDlq` điều khiển việc binder chủ động publish lại message lỗi đến DLQ, thường bổ sung header chứa thông tin exception.

Khi binder chỉ dựa vào broker dead-lettering, queue nguồn được cấu hình DLX và message bị reject không requeue; RabbitMQ chuyển message đến DLX. Metadata lỗi ở tầng Java có thể không đầy đủ như khi binder republish.

Khi bật `republishToDlq`, binder có thể chủ động gửi message đến DLQ và thêm thông tin chẩn đoán như exception class, message và stack trace theo giới hạn header/cấu hình. Cơ chế này khác với việc broker tự dead-letter do queue arguments. Hãy kiểm tra phiên bản binder, giới hạn kích thước header và thứ tự acknowledgement khi bật republish.

Ví dụ cấu hình minh họa:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              republish-to-dlq: true
              dead-letter-exchange: orders.dlx
              dead-letter-routing-key: orders.failed
```

Không bật đồng thời nhiều cơ chế republish/requeue mà không hiểu thứ tự của chúng. Nếu binder republish thành công rồi ack message nguồn, message lỗi được giữ trong DLQ. Nếu publish DLQ thất bại, cần xác minh binder có thể để message nguồn chưa ack/requeue hoặc phát lỗi theo cấu hình; không giả định message đã được lưu an toàn.

## 9. Retry diễn ra trước dead-letter flow

Retry cho phép thử lại lỗi có thể phục hồi trước khi message được cách ly. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 8000
            back-off-multiplier: 2.0
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              auto-bind-dlq: true
              dead-letter-exchange: orders.dlx
              dead-letter-routing-key: orders.failed
```

`max-attempts: 4` là tổng số lần xử lý tối đa, bao gồm lần đầu và tối đa ba lần retry. Nếu xử lý thành công trong một lần thử, message không cần đi vào DLQ. Nếu mọi lần đều thất bại, error handling có thể reject/republish message theo cấu hình binder.

Không retry vô hạn các lỗi dữ liệu hoặc lỗi lập trình. Retry cần có giới hạn, backoff và phân loại exception. Với lỗi cần trì hoãn dài, retry queue/TTL có thể phù hợp hơn retry tại chỗ vì tránh giữ consumer thread trong thời gian chờ.

## 10. Reject, nack và requeue

RabbitMQ phân biệt việc từ chối message với việc đưa message trở lại queue:

| Hành động | Ý nghĩa | Có thể kích hoạt DLX? |
|---|---|---|
| `basic.reject` với `requeue=false` | Từ chối và không đưa lại queue nguồn | Có, nếu queue có DLX |
| `basic.nack` với `requeue=false` | Từ chối một hoặc nhiều message và không requeue | Có, nếu queue có DLX |
| `basic.reject`/`basic.nack` với `requeue=true` | Đưa message trở lại queue để giao lại | Không dead-letter chỉ vì thao tác này |
| Ack thành công | Xác nhận message đã được xử lý | Không |

Binder và listener container quyết định cách exception trong handler được chuyển thành ack/nack/reject. `requeueRejected`, retry interceptor và error handler có thể ảnh hưởng kết quả. Cần kiểm tra cấu hình thực tế của Rabbit binder và tránh cấu hình requeue vô hạn cho poison message.

## 11. TTL và queue length cũng có thể tạo dead-letter

DLX không chỉ nhận message từ handler reject. RabbitMQ còn có thể dead-letter khi message hết TTL hoặc queue vượt giới hạn theo cấu hình.

Ví dụ queue retry có TTL:

```text
Main queue
    |
    | reject/no requeue
    v
Retry exchange / retry queue
    |
    | message TTL expires
    v
Dead-letter exchange
    |
    v
Main queue (retry after delay)
```

Mẫu retry queue/TTL có thể trì hoãn message trước khi quay lại queue chính. Cần thiết kế routing key và DLX hai chiều cẩn thận để không tạo vòng lặp không giới hạn. Đặt TTL ở queue hoặc message có semantics khác nhau; message hết hạn có thể bị dead-letter khi tới đầu queue tùy loại queue và broker behavior.

Queue length limit hoặc overflow policy cũng có thể làm message bị dead-letter hoặc loại bỏ theo policy. Với dữ liệu quan trọng, cần chọn overflow behavior rõ ràng và theo dõi metric dropped/dead-lettered.

## 12. Topology cần tồn tại trong cùng virtual host

Exchange, queue và binding phải nằm trong cùng RabbitMQ virtual host để kết nối với nhau. Một queue ở vhost `/orders` không thể dùng DLX ở vhost `/shared` chỉ bằng cách ghi tên exchange. Tên tài nguyên có thể giống nhau ở vhost khác nhau nhưng chúng là tài nguyên độc lập.

Khi dùng `autoBindDlq`, tài khoản kết nối của binder có thể cần quyền configure để tạo exchange, queue và binding; quyền read trên queue nguồn; và quyền write lên exchange khi republish. Nếu topology được provision trước, binder có thể chỉ cần quyền runtime phù hợp, tùy cấu hình declaration.

Hãy kiểm tra:

- Queue nguồn có `x-dead-letter-exchange` đúng không?
- Routing key argument có đúng giá trị không?
- DLX tồn tại trong đúng vhost không?
- DLQ được bind vào DLX bằng key/pattern đúng không?
- Exchange type có tương thích với binding không?
- Principal của binder có quyền configure/read/write cần thiết không?

## 13. Durability và độ tin cậy của dead-lettering

DLQ là queue lưu message lỗi, nhưng việc có DLQ không tự đảm bảo message được lưu bền vững trong mọi tình huống.

| Thành phần | Cần xem xét |
|---|---|
| Queue nguồn | Durable hay không; loại queue; policy và replication |
| DLX | Exchange tồn tại và được quản lý ổn định |
| DLQ | Durable, loại queue, replication, retention/TTL |
| Message | Delivery mode/persistence và thuộc tính message |
| Dead-letter transfer | Cơ chế broker hoặc binder republish; xác nhận publish và lỗi khi chuyển |
| Consumer DLQ | Ack sau khi lưu/điều tra message theo yêu cầu |

RabbitMQ dead-lettering nội bộ có semantics phụ thuộc loại queue và cấu hình broker. Với một số cấu hình, việc broker chuyển message đến DLX có thể không tương đương publisher confirm của một producer ứng dụng. Nếu yêu cầu at-least-once dead-letter transfer, cần đánh giá khả năng quorum queue và dead-letter strategy tương ứng của phiên bản RabbitMQ đang chạy. Không suy ra bảo đảm bền vững chỉ từ `autoBindDlq: true`.

Nếu dùng `republishToDlq`, cần kiểm tra cách binder gửi message và xử lý kết quả publish trước khi xác nhận message nguồn. Cơ chế binder republish và broker dead-lettering có failure mode khác nhau; test failover và mất kết nối khi chuyển DLQ là cần thiết.

## 14. Đọc message từ DLQ

DLQ có thể được đọc bởi một consumer riêng để audit hoặc hỗ trợ vận hành. Ví dụ:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderDlqAuditConfiguration {

    @Bean
    Consumer<Message<byte[]>> inspectFailedOrder(
            DeadLetterAuditService auditService) {
        return message -> auditService.record(
            message.getPayload(),
            message.getHeaders()
        );
    }
}
```

Consumer DLQ nên có group riêng và chỉ đọc queue dead-letter. Dùng `byte[]` có thể hữu ích nếu payload gốc không deserialize được thành DTO. Audit service cần lưu event ID, nguồn, routing key, thời điểm, lỗi và trạng thái xử lý theo chính sách dữ liệu.

Không để consumer audit tự động xóa hoặc replay message trước khi có quy trình phê duyệt. DLQ có thể chứa dữ liệu nhạy cảm hoặc payload không hợp lệ; quyền truy cập cần hạn chế.

## 15. Replay message từ DLQ

Sau khi sửa lỗi, có thể publish lại message vào exchange/topic nguồn hoặc một recovery destination. Quy trình replay nên:

1. Đọc message và xác định nguyên nhân dead-letter.
2. Kiểm tra payload, schema và trạng thái nghiệp vụ hiện tại.
3. Sửa dữ liệu hoặc deploy phiên bản xử lý đã khắc phục.
4. Giữ nguyên event ID để consumer idempotency nhận diện bản gửi lại.
5. Chọn exchange và routing key đích chính xác.
6. Không giữ nguyên các header chẩn đoán lỗi nếu chúng không còn phù hợp.
7. Ghi audit về người/tiến trình replay, thời điểm, số lượng và kết quả.
8. Theo dõi queue chính và xác nhận message đã được xử lý.

Không replay toàn bộ DLQ liên tục khi nguyên nhân chưa được sửa. Điều đó có thể tạo vòng lặp lỗi. Nếu replay một message đã có tác động nghiệp vụ một phần, consumer cần idempotency hoặc quy trình bù trừ phù hợp.

## 16. DLX dùng chung hay riêng theo consumer?

Có thể tạo một DLX dùng chung cho nhiều domain, nhưng nên tách routing key và DLQ theo consumer group để dễ quản trị:

```text
orders.dlx (direct)
    |
    +-- orders.inventory.failed --> orders.inventory.dlq
    |
    +-- orders.billing.failed   --> orders.billing.dlq
    |
    +-- orders.analytics.failed --> orders.analytics.dlq
```

Một DLX dùng chung giúp giảm số exchange, nhưng yêu cầu routing key duy nhất và quyền truy cập cẩn thận. DLX riêng theo domain giúp cách ly quyền và vòng đời topology, nhưng tăng số tài nguyên cần quản lý.

Chọn cách nào cũng cần giữ metadata xác định destination nguồn, consumer group, event ID và loại lỗi. Không để các message có schema hoặc quyền xử lý khác nhau trộn vào một DLQ mà không có hợp đồng chung.

## 17. Các lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Bật `autoBindDlq` nhưng không có quyền configure | Binder không tạo được DLX/DLQ/binding | Provision trước hoặc cấp quyền configure tối thiểu |
| `deadLetterExchange` không tồn tại | Broker không thể định tuyến dead-letter | Tạo DLX trong cùng vhost và kiểm tra declaration |
| Routing key không khớp binding key | Message không vào DLQ mong muốn | Đồng bộ `deadLetterRoutingKey` và binding key/pattern |
| Exchange type không thống nhất | Declaration có thể bị broker từ chối hoặc routing sai | Dùng cùng exchange type ở binder và hạ tầng |
| Queue nguồn không có DLX argument | Broker không biết dead-letter đến đâu | Kiểm tra autoBindDlq hoặc queue provisioning |
| Handler bắt exception rồi trả bình thường | Binder không quan sát thấy lỗi để retry/reject | Chỉ nuốt lỗi khi đã xử lý có chủ đích |
| Requeue vô hạn | Poison message lặp nóng | Giới hạn retry và chuyển sang DLQ |
| DLQ không durable hoặc retention quá ngắn | Message lỗi có thể mất trước khi điều tra | Chọn durability/retention phù hợp |
| Nhầm DLX với DLQ | Cấu hình exchange như queue hoặc ngược lại | Tách rõ exchange, queue và binding |
| Bật `republishToDlq` mà không kiểm tra publish failure | Có thể hiểu sai trạng thái lưu message lỗi | Test mất kết nối và xác minh ack/republish semantics |
| Replay tạo event ID mới | Consumer không nhận diện duplicate | Giữ nguyên event ID gốc |

## 18. Kiểm thử autoBindDlq và routing

Nên có integration test với RabbitMQ tương thích để xác minh topology và hành vi dead-letter thực tế:

| Kịch bản | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Auto bind | Bật `auto-bind-dlq` | DLX, DLQ và binding được khai báo đúng |
| Custom DLX | Đặt `dead-letter-exchange` | Queue nguồn trỏ đến đúng DLX |
| Custom routing key | Đặt `dead-letter-routing-key` | Message vào đúng DLQ qua binding key tương ứng |
| Handler thành công | Consumer xử lý bình thường | Message không vào DLQ |
| Handler lỗi rồi thành công | Lần đầu lỗi, retry sau thành công | Message hoàn tất, không dead-letter |
| Hết retry | Handler luôn lỗi | Message đi theo error handling đến DLQ |
| Reject/no requeue | Tạo reject theo cấu hình | Broker dead-letter message nếu queue có DLX |
| Requeue | Nack với requeue true | Message được giao lại theo broker behavior, không coi là dead-letter ngay |
| TTL | Đặt TTL và để message hết hạn | Message được chuyển đến DLX nếu queue cấu hình phù hợp |
| Routing key sai | Đổi binding key không khớp | Phát hiện message không đến DLQ mong đợi |
| DLX không tồn tại | Xóa hoặc không provision exchange | Lỗi dead-letter được quan sát; xác minh broker behavior |
| Thiếu ACL | Thu hồi quyền ghi/configure | Binder không thể khai báo hoặc chuyển message; lỗi được phát hiện |
| Republish failure | Ngắt kết nối trong lúc binder republish | Xác minh message nguồn không bị xác nhận sai và có thể phục hồi |
| Replay | Đọc DLQ rồi publish lại | Giữ event ID và consumer xử lý an toàn |

Test binder kiểm tra được function và binding ở tầng Spring nhưng không thay thế integration test cho queue arguments, exchange binding, TTL, reject, ACL và dead-letter transfer. Dùng RabbitMQ Management UI/API hoặc CLI để xác minh topology vật lý.

## 19. Quan sát DLQ trong production

Theo dõi:

- Số message đi vào DLQ theo source queue và consumer group.
- Backlog và tuổi message cũ nhất trong DLQ.
- Exception class hoặc reason dead-letter phổ biến.
- Số lần retry trước khi message được cách ly.
- Lỗi publish/route vào DLX hoặc DLQ.
- Số message không được định tuyến và số queue không có consumer.
- Số lần replay, kết quả replay và tỷ lệ message tiếp tục thất bại.
- Dung lượng DLQ và thời gian retention còn lại.

Log nên có event ID, source queue, DLX, routing key, DLQ, consumer group và exception class nếu metadata có sẵn. Không ghi credential hoặc payload nhạy cảm. Metric label nên giới hạn theo destination/group/error class, không dùng event ID làm label có cardinality cao.

Đặt cảnh báo khi DLQ tăng đột biến, message cũ vượt SLA, DLX/DLQ không thể publish hoặc queue chính liên tục reject. DLQ không được giám sát có thể biến thành nơi chứa lỗi vô thời hạn.

## 20. Quy trình triển khai

1. Xác định consumer binding và queue nguồn cần dead-letter.
2. Đặt `group` ổn định cho consumer logic.
3. Chọn `max-attempts` và backoff phù hợp với loại lỗi.
4. Bật `auto-bind-dlq: true` trên Rabbit consumer binding.
5. Chọn `dead-letter-exchange` và `dead-letter-exchange-type`.
6. Chọn `dead-letter-routing-key` khớp với binding key của DLQ.
7. Đặt `dead-letter-queue-name` tường minh nếu topology được quản lý bằng IaC.
8. Quyết định có cần `republish-to-dlq` để bổ sung exception metadata hay không.
9. Provision exchange, queue, binding, durability, retention và ACL phù hợp.
10. Kiểm thử retry exhaustion, reject/requeue, TTL, routing và publish failure.
11. Xây dựng quy trình điều tra và replay có audit, giữ event ID.
12. Theo dõi backlog, tuổi message, lỗi dead-letter và kết quả replay.

## 21. Tự kiểm tra

- [ ] Phân biệt queue nguồn, dead-letter exchange, routing key và DLQ.
- [ ] Giải thích được vai trò của `autoBindDlq`.
- [ ] Cấu hình được `deadLetterExchange` và `deadLetterRoutingKey`.
- [ ] Biết routing key phải khớp binding key/pattern của DLQ.
- [ ] Phân biệt broker dead-lettering với binder `republishToDlq`.
- [ ] Biết retry diễn ra trước khi message được chuyển sang DLQ theo chính sách consumer.
- [ ] Phân biệt reject/no-requeue với nack/requeue.
- [ ] Kể được các nguyên nhân dead-letter như reject, TTL và queue limit.
- [ ] Xác định được yêu cầu provisioning, vhost, durability và ACL.
- [ ] Thiết kế được replay an toàn bằng event ID ổn định.
- [ ] Kiểm thử được DLX/DLQ topology và lỗi publish dead-letter trên RabbitMQ.

## Kết luận

`autoBindDlq` giúp RabbitMQ Binder tự khai báo dead-letter topology cho consumer. Queue nguồn chuyển message lỗi đến `deadLetterExchange`; exchange sử dụng `deadLetterRoutingKey` cùng binding để định tuyến đến DLQ. Retry, reject/requeue và binder republish quyết định thời điểm cũng như cách message đi vào dead-letter flow. Cần phân biệt DLX với DLQ, đồng bộ routing key và binding key, provision tài nguyên trong đúng vhost, cấp ACL phù hợp và kiểm thử cả trường hợp chuyển DLQ thất bại. DLQ chỉ hữu ích khi có retention, monitoring, quy trình điều tra và replay an toàn.
