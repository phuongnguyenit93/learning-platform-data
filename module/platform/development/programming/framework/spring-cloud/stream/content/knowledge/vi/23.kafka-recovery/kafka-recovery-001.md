# Cấu hình enableDlq, dlqName và yêu cầu consumer group

Khi consumer Kafka không thể xử lý một message sau số lần thử lại đã cấu hình, hệ thống cần một nơi giữ message để điều tra hoặc xử lý sau. Kafka Binder của Spring Cloud Stream hỗ trợ **dead-letter topic (DLT/DLQ)**: message lỗi được publish sang một Kafka topic riêng sau khi xử lý thất bại theo chính sách retry.

Ba cấu hình cần hiểu cùng nhau là `enableDlq`, `dlqName` và `group`. `enableDlq` bật việc chuyển message lỗi sang dead-letter topic; `dlqName` cho phép chỉ định tên topic đó; `group` xác định consumer group logic nhận message ban đầu và là yêu cầu để Kafka Binder định danh nơi xử lý lỗi. Consumer ẩn danh không có group ổn định nên không thể dùng cơ chế DLQ này theo cách thông thường.

Bài thuộc chương **Khôi phục Kafka** của module `SPRING_CLOUD_STREAM`, tập trung vào cấu hình Kafka Binder trong mô hình hàm `Supplier`/`Function`/`Consumer`, cách đặt tên DLQ, quan hệ giữa consumer group và DLQ, provisioning topic, retry, phân vùng, quyền truy cập, replay và kiểm thử.

## 1. DLQ giải quyết vấn đề gì?

Một consumer có thể gặp message không thể xử lý tự động: payload sai schema, dữ liệu nghiệp vụ không hợp lệ, tham chiếu đến thực thể không tồn tại hoặc một dependency liên tục thất bại. Nếu chỉ retry vô hạn, message đó có thể giữ luồng xử lý, tạo tải không cần thiết và khiến consumer lag tăng.

DLQ là một topic riêng để giữ các message đã thất bại sau chính sách xử lý lỗi. Consumer chính tiếp tục xử lý message mới theo cơ chế binder/broker, còn message lỗi được lưu lại để điều tra, sửa dữ liệu hoặc replay sau khi nguyên nhân được khắc phục.

```text
Kafka topic: orders.events
          |
          v
Consumer group: order-processor
          |
          v
   processOrder function
          |
          +---- xử lý thành công ----> hoàn tất theo cơ chế commit/ack
          |
          +---- xử lý thất bại
                    |
                    v
             Retry theo cấu hình
                    |
          +---------+---------+
          |                   |
       Thành công         Hết lượt thử
                              |
                              v
                 Kafka dead-letter topic
                 orders.events.order-processor.dlq
```

DLQ không sửa message và cũng không tự giải quyết lỗi. Nó giữ lại bằng chứng về message thất bại, giúp luồng chính tránh bị mắc kẹt bởi một record không thể xử lý. Đội vận hành vẫn cần quy trình quan sát, phân loại, sửa lỗi và replay.

## 2. Phân biệt destination, consumer group và DLQ name

Ba tên này đại diện cho ba vai trò khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `destination` | Kafka topic nguồn mà binding nhận message | `orders.events` |
| `group` | Consumer group logic phối hợp xử lý topic nguồn | `order-processor` |
| `dlqName` | Kafka topic nhận message đã thất bại | `orders.events.order-processor.dlq` |

`destination` và `group` được khai báo ở binding chung của Spring Cloud Stream. `enableDlq` và `dlqName` là thuộc tính riêng của Kafka Binder, đặt dưới cấu hình Kafka consumer của binding đó.

Không dùng tên DLQ làm `group`. DLQ là topic đích để lưu record lỗi; group là danh tính consumer logic của topic nguồn. Một topic nguồn có thể có nhiều group độc lập, mỗi group xử lý cùng dữ liệu theo mục đích khác nhau.

## 3. Vì sao Kafka DLQ yêu cầu consumer group?

Kafka Binder yêu cầu một consumer group được khai báo khi bật DLQ. Một consumer không khai báo `group` là consumer ẩn danh; nó không có danh tính xử lý ổn định để binder gắn chính sách lỗi và dead-letter destination theo nhóm.

Khai báo group tường minh giúp:

- Xác định các replica nào đang phối hợp xử lý cùng một luồng nghiệp vụ.
- Phân biệt nhiều ứng dụng độc lập cùng đọc một topic.
- Tạo tên DLQ mặc định gắn với destination và group.
- Giữ cấu hình DLQ ổn định khi ứng dụng restart hoặc scale.
- Tránh các consumer ẩn danh tạo ra cách xử lý lỗi khó dự đoán.

Ví dụ hai ứng dụng cùng đọc `orders.events`:

| Consumer | Group | Mục đích | DLQ mặc định theo quy ước binder |
|---|---|---|---|
| Inventory projection | `inventory-projection` | Cập nhật tồn kho | `orders.events.inventory-projection.dlq` |
| Analytics projection | `analytics-projection` | Cập nhật số liệu | `orders.events.analytics-projection.dlq` |

Hai group nhận dữ liệu độc lập và có thể có kết quả xử lý lỗi khác nhau. Một message có thể thành công ở inventory nhưng thất bại ở analytics; khi đó chỉ luồng analytics cần giữ message trong DLQ của nó.

Không tạo một group mới cho mỗi pod/replica. Các replica của cùng một consumer logic phải dùng chung group để chia tải; nếu mỗi replica dùng group riêng, mỗi group có thể nhận toàn bộ bản sao của luồng topic.

## 4. Cấu hình `enableDlq`

Giả sử ứng dụng có function `processOrder` nhận sự kiện đơn hàng từ topic `orders.events`. Cấu hình consumer group và bật DLQ:

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
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
```

Giải thích:

- `processOrder-in-0` là input binding của function `processOrder`.
- `destination: orders.events` chọn topic nguồn.
- `group: order-processor` tạo consumer group có danh tính ổn định.
- `max-attempts: 3` cho phép tối đa ba lần xử lý, bao gồm lần đầu.
- `enable-dlq: true` bật dead-letter handling của Kafka Binder cho binding này.

`enable-dlq` thuộc namespace `spring.cloud.stream.kafka.bindings.<bindingName>.consumer`. Nó không phải thuộc tính generic dùng giống nhau cho RabbitMQ hoặc Pulsar. Các binder khác có cơ chế dead-letter riêng.

Khi handler tiếp tục thất bại sau số lần thử được phép, Kafka Binder có thể chuyển message sang DLQ theo error handling của binder. Nếu handler thành công trong một lần retry, message không cần chuyển sang DLQ.

## 5. Cấu hình `dlqName`

Nếu không chỉ định tên riêng, Kafka Binder sử dụng quy ước tên DLQ mặc định dựa trên destination và group, thường có dạng:

```text
<destination>.<group>.dlq
```

Với `destination = orders.events` và `group = order-processor`, tên theo quy ước là:

```text
orders.events.order-processor.dlq
```

Có thể chỉ định tên topic khác bằng `dlq-name`:

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
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.failed.v1
```

`dlq-name` là tên Kafka topic nhận message lỗi. Tên này phải tuân theo quy tắc đặt tên topic và được provision hoặc cho phép tự tạo theo chính sách cluster. Dùng tên rõ ràng giúp đội vận hành nhận diện luồng lỗi, nhưng tránh dùng một DLQ chung cho nhiều consumer có schema và quyền xử lý khác nhau nếu không có hợp đồng thống nhất.

Tên mặc định và các chi tiết provisioning có thể phụ thuộc phiên bản Kafka Binder. Với production, nên cấu hình `dlq-name` tường minh khi tên topic là một phần của hạ tầng được quản lý, sau đó xác minh topic thực tế khi ứng dụng khởi động.

## 6. Ví dụ function consumer hoàn chỉnh

Function có thể là `Consumer<OrderEvent>` thông thường:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
```

Nếu `orderService.process` ném exception, lỗi được đưa vào cơ chế error handling của binding. Binder áp dụng retry theo cấu hình; khi retry không thành công và DLQ được bật, message được chuyển đến topic lỗi theo cấu hình Kafka Binder.

Ví dụ này giả định `OrderService` ném lỗi khi xử lý thất bại. Nếu service tự bắt exception rồi chỉ log hoặc trả về bình thường, binder sẽ không thấy lỗi để áp dụng retry/DLQ. Chỉ bắt lỗi khi ứng dụng thực sự đã xử lý hoặc chuyển trách nhiệm lỗi sang một cơ chế khác có chủ đích.

## 7. `maxAttempts` quyết định khi nào message đi vào DLQ

DLQ thường nhận message sau khi cơ chế retry của consumer đã hết lượt. `max-attempts` là tổng số lần xử lý, bao gồm lần đầu tiên.

| `max-attempts` | Lần xử lý ban đầu | Số lần retry tối đa |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 1 | 1 |
| 3 | 1 | 2 |
| 5 | 1 | 4 |

Ví dụ `max-attempts: 3` có nghĩa handler có thể được gọi tối đa ba lần cho message trước khi error handling chuyển sang bước tiếp theo. Không phải ba lần retry cộng thêm lần đầu.

Có thể cấu hình backoff để tránh retry liên tục:

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
```

Retry và DLQ giải quyết hai giai đoạn khác nhau: retry cho lỗi có thể phục hồi; DLQ giữ lại message khi xử lý tự động không thành công. Không tăng `max-attempts` vô hạn để tránh DLQ, vì message lỗi dữ liệu hoặc lỗi lập trình thường không tự hết khi thử lại.

## 8. Phân loại lỗi trước khi chuyển DLQ

Không phải lỗi nào cũng nên retry. Lỗi tạm thời như timeout hoặc broker phụ thuộc gián đoạn có thể phục hồi. Lỗi schema, dữ liệu sai hoặc vi phạm quy tắc nghiệp vụ thường cần cách ly hoặc sửa dữ liệu.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | API trả 503, connection reset | Retry có giới hạn và backoff |
| Quá tải | Dependency trả 429 | Backoff; tôn trọng giới hạn của dependency |
| Lỗi dữ liệu | Thiếu `orderId`, JSON sai | Không retry kéo dài; chuyển error handling/DLQ |
| Lỗi nghiệp vụ | Đơn hàng không hợp lệ | Tạo kết quả nghiệp vụ hoặc cách ly theo chính sách |
| Lỗi cấu hình/quyền | Producer không có quyền ghi DLQ | Sửa ACL/cấu hình; message có thể chưa được chuyển an toàn |
| Lỗi lập trình | Null dereference | Điều tra code; DLQ giúp giữ message nhưng không thay việc sửa lỗi |

Kafka Binder hỗ trợ phân loại retryable exception ở consumer properties trong các phiên bản phù hợp. Hãy kiểm tra `defaultRetryable` và `retryableExceptions` theo phiên bản đang sử dụng nếu muốn chỉ retry một tập exception cụ thể. Không nên giả định mọi exception đều được xử lý giống nhau khi cấu hình custom error handler.

## 9. DLQ topic cần được provision và cấp quyền

Bật `enable-dlq` không thay thế việc chuẩn bị hạ tầng Kafka. Topic DLQ phải có thể được tạo hoặc đã tồn tại theo chính sách cluster. Tùy cấu hình binder, việc tự provision topic có thể được bật hoặc tắt; trong môi trường production thường nên quản lý topic bằng quy trình hạ tầng rõ ràng.

Kiểm tra các điều kiện:

- Topic DLQ tồn tại hoặc principal của binder được phép tạo topic theo chính sách.
- Consumer/producer principal có quyền cần thiết trên topic nguồn và DLQ.
- Producer của binder có quyền ghi vào DLQ.
- Retention, replication factor và số partition của DLQ phù hợp với yêu cầu lưu lỗi.
- Công cụ vận hành có quyền đọc DLQ và quy trình replay có quyền publish lại topic nguồn.
- Monitoring theo dõi được lỗi publish vào DLQ.

Nếu consumer đọc được topic nguồn nhưng không có quyền ghi DLQ, đường xử lý lỗi có thể thất bại đúng lúc cần lưu message. Không chỉ kiểm tra quyền đọc topic chính; cần kiểm tra quyền ghi vào dead-letter topic nữa.

## 10. Partition của DLQ

Với topic nguồn có nhiều partition, cần quyết định message lỗi sẽ được ghi vào partition nào của DLQ. Việc này quan trọng nếu muốn giữ metadata phân vùng hoặc replay theo thứ tự/key.

Một số điểm cần xác minh:

- Số partition của DLQ có tương thích với cách binder chọn partition không.
- Có cần giữ key gốc của record không.
- Có cần ánh xạ partition nguồn sang partition DLQ tương ứng không.
- Có custom `DlqPartitionFunction` hay cấu hình partitioning riêng không.
- Khi replay, consumer có phụ thuộc thứ tự theo key hay không.

Trong các cấu hình partitioned, Kafka Binder có thể cần DLQ có số partition phù hợp với topic nguồn hoặc một chiến lược phân vùng DLQ rõ ràng. Không mặc định một DLQ chỉ có một partition là phù hợp cho mọi topic. Hãy kiểm tra hướng dẫn của đúng phiên bản binder và topology thực tế trước khi provision.

## 11. Mỗi consumer group nên có DLQ logic riêng

Giả sử `orders.events` được hai nhóm xử lý:

```text
                         orders.events
                         /           \
                        /             \
                       v               v
             inventory-projection   analytics-projection
                       |               |
                       v               v
        orders.events.inventory-   orders.events.analytics-
        projection.dlq             projection.dlq
```

Inventory và analytics có thể dùng schema validation, dependency và chính sách retry khác nhau. Nếu một event làm analytics lỗi nhưng inventory xử lý thành công, chỉ analytics cần đưa bản ghi vào DLQ riêng.

DLQ riêng theo group giúp:

- Không trộn message lỗi từ nhiều ứng dụng có cách xử lý khác nhau.
- Cấp quyền đọc/replay theo nhóm chịu trách nhiệm.
- Theo dõi tỷ lệ lỗi và backlog độc lập.
- Replay vào đúng topic/group có hợp đồng tương ứng.

Nếu cố ý dùng chung `dlq-name` cho nhiều group, cần thiết kế schema, metadata nguồn, quyền truy cập, partition và quy trình replay thống nhất. Nếu không, message có thể bị xử lý bởi công cụ hoặc consumer không phù hợp.

## 12. Metadata cần giữ trong dead-letter message

Khi message được chuyển sang DLQ, đội vận hành cần biết nó đến từ đâu và thất bại vì lý do gì. Tùy phiên bản binder và cơ chế error handling, message dead-letter có thể mang các header metadata như:

- Topic nguồn.
- Partition và offset nguồn.
- Consumer group liên quan.
- Exception class và thông tin lỗi.
- Timestamp hoặc thông tin về lần xử lý.
- Key và payload gốc.

Tên header cụ thể có thể khác theo phiên bản và cơ chế binder. Hãy đọc metadata từ message thực tế trong integration test, không hardcode tên header dựa trên giả định.

Không ghi thông tin bí mật hoặc toàn bộ stack trace vào header nếu hệ thống DLQ có phạm vi truy cập rộng. Cần cân bằng khả năng điều tra với yêu cầu bảo vệ dữ liệu. Payload gốc nên được giữ nguyên nếu cần replay, đồng thời có thể bổ sung metadata chẩn đoán đã được kiểm soát.

## 13. Đọc và xử lý message trong DLQ

DLQ là Kafka topic nên có thể được đọc bằng một consumer riêng. Ví dụ consumer chuyên ghi nhận message lỗi để đội vận hành tra cứu:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class DeadLetterAuditConfiguration {

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

Consumer DLQ nên có group riêng, ví dụ `order-dlq-audit`, để việc đọc phục vụ giám sát không ảnh hưởng consumer nghiệp vụ. Nếu cần giữ nguyên payload bất kể schema lỗi, dùng kiểu byte array có thể phù hợp hơn việc deserialize ngay thành DTO nghiệp vụ.

Không để consumer audit tự động xóa hoặc replay message trước khi có chính sách rõ ràng. DLQ có thể là nguồn dữ liệu điều tra; retention và quyền đọc phải được quản lý giống các topic nghiệp vụ khác.

## 14. Replay message từ DLQ

Sau khi nguyên nhân được khắc phục, có thể replay message lỗi về topic nguồn hoặc một topic phục hồi riêng. Replay cần được kiểm soát để tránh tạo thêm lỗi hoặc tác động nghiệp vụ trùng.

Quy trình nên có:

1. Đọc message DLQ và kiểm tra nguyên nhân lỗi.
2. Xác minh schema, dữ liệu và phiên bản code đã được sửa.
3. Xác định message có còn hợp lệ về mặt nghiệp vụ hay đã hết hạn.
4. Giữ nguyên event ID để consumer idempotency nhận diện bản giao lại.
5. Giữ key và metadata nghiệp vụ cần thiết; không giữ nguyên header lỗi nếu chúng không còn phù hợp.
6. Publish vào topic nguồn hoặc recovery topic đã được phê duyệt.
7. Ghi audit về người/tiến trình replay, thời điểm, số lượng và kết quả.
8. Theo dõi consumer group đích và xác nhận message đã được xử lý.

Không replay toàn bộ DLQ liên tục khi nguyên nhân gốc chưa được sửa. Điều đó tạo vòng lặp lỗi và có thể làm backlog tăng nhanh. Với dữ liệu thanh toán hoặc tồn kho, cần kiểm tra trạng thái hiện tại trước khi replay; idempotency ngăn duplicate nhưng không tự làm một sự kiện đã lỗi nghiệp vụ trở nên hợp lệ.

## 15. Khác biệt với retry topic và broker redelivery

DLQ không giống retry topic và cũng không giống broker redelivery:

| Cơ chế | Mục tiêu | Thời điểm sử dụng |
|---|---|---|
| Retry tại chỗ | Thử lại nhanh cùng message | Lỗi tạm thời có thể phục hồi trong thời gian ngắn |
| Retry topic | Trì hoãn message rồi thử lại sau | Lỗi cần backoff dài hoặc không muốn chặn luồng chính |
| Broker redelivery | Broker giao lại message chưa được xác nhận | Consumer/handler thất bại theo semantics broker |
| DLQ | Cách ly message đã thất bại sau chính sách xử lý | Message cần điều tra, sửa hoặc replay có chủ đích |

Kafka không có cơ chế queue requeue giống RabbitMQ. Consumer group quản lý offset; việc retry và DLQ thường được thực hiện ở binder/application bằng cách publish record sang topic khác. Cần phân biệt việc offset được commit, record được publish vào DLQ và lỗi publish DLQ.

## 16. Bảo mật và quản trị DLQ

DLQ thường chứa message lỗi có thể bao gồm dữ liệu nhạy cảm, payload không hợp lệ hoặc thông tin nội bộ. Cần áp dụng:

- ACL chỉ cho consumer lỗi và công cụ vận hành được phép đọc.
- Quyền ghi DLQ chỉ cho producer/binder cần thiết.
- Retention và cleanup policy phù hợp với yêu cầu audit.
- Mã hóa khi truyền và khi lưu theo chính sách cluster.
- Audit mọi thao tác replay, xóa hoặc export dữ liệu.
- Giới hạn người có quyền publish trực tiếp vào topic nguồn trong quy trình replay.
- Giám sát dung lượng và cảnh báo khi DLQ tăng bất thường.

Không cấp quyền `ALL` trên toàn cluster chỉ để ứng dụng có thể ghi DLQ. Cấp quyền theo topic nguồn, DLQ và các tài nguyên thực sự cần thiết.

## 17. Kiểm thử enableDlq, dlqName và group

Một bộ kiểm thử nên xác minh cả cấu hình hợp lệ và các điều kiện hạ tầng:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| DLQ tắt | `enable-dlq: false` hoặc không khai báo | Không kỳ vọng binder publish message vào DLQ |
| DLQ bật và có group | `enable-dlq: true`, group ổn định | Binding khởi tạo theo cấu hình và có thể dùng DLQ |
| DLQ bật nhưng thiếu group | Bỏ `group` | Cấu hình không đáp ứng yêu cầu Kafka Binder; xác minh lỗi khởi động/validation của phiên bản |
| Tên DLQ mặc định | Không khai báo `dlq-name` | Xác minh tên topic được binder sử dụng theo quy ước phiên bản |
| Tên DLQ tùy chỉnh | Đặt `dlq-name: orders.failed.v1` | Message lỗi đến đúng topic tùy chỉnh |
| Handler lỗi rồi thành công | Lần đầu ném lỗi, lần sau thành công | Message không vào DLQ nếu retry thành công |
| Hết `max-attempts` | Handler luôn ném lỗi | Message được chuyển theo cơ chế DLQ đã cấu hình |
| Topic DLQ không tồn tại | Tắt auto provisioning hoặc không tạo topic | Lỗi provisioning/publish được phát hiện và quan sát |
| Thiếu ACL ghi DLQ | Thu hồi quyền producer trên DLQ | Lỗi chuyển DLQ được phát hiện; không giả định message đã được lưu |
| Nhiều consumer group | Hai group cùng đọc một topic | Mỗi group có hành vi lỗi và DLQ độc lập |
| Topic nhiều partition | Gửi message ở nhiều partition | Kiểm tra ánh xạ partition/key sang DLQ |
| Replay | Đọc DLQ rồi gửi lại sau khi sửa lỗi | Event ID được giữ và consumer xử lý an toàn |

Test binder giúp kiểm tra function và binding ở tầng Spring, nhưng không thay thế integration test với Kafka thật khi cần xác nhận topic provisioning, ACL, partition, offset và dead-letter publishing.

## 18. Quan sát DLQ trong production

Các chỉ số cần theo dõi:

- Số message được publish vào DLQ theo topic nguồn và group.
- Tốc độ tăng và tổng backlog của từng DLQ.
- Tuổi message cũ nhất trong DLQ.
- Loại exception thường gặp và binding phát sinh lỗi.
- Số lần retry trung bình trước khi vào DLQ.
- Lỗi publish DLQ, lỗi ACL và lỗi provisioning.
- Số message replay, tỷ lệ replay thành công và số message tiếp tục thất bại.

Log nên có event ID, source topic, consumer group, partition/offset và exception class nếu metadata được cung cấp. Không dùng event ID làm metric label có cardinality cao. Có thể tạo metric theo binding, group, loại exception và DLQ topic.

Đặt cảnh báo khi DLQ tăng nhanh, có message quá tuổi, hoặc producer không thể ghi vào DLQ. Một DLQ không được giám sát có thể trở thành nơi lưu lỗi vô thời hạn và khiến sự cố nghiệp vụ bị bỏ quên.

## 19. Quy trình cấu hình DLQ

Khi triển khai Kafka consumer có dead-letter handling:

1. Xác định function và input binding cần bảo vệ.
2. Đặt `destination` là topic nguồn.
3. Đặt `group` ổn định cho consumer logic; dùng chung group giữa các replica của cùng ứng dụng.
4. Chọn `max-attempts` và backoff theo loại lỗi và SLA.
5. Bật `enable-dlq: true` trong Kafka consumer binding.
6. Chọn `dlq-name` tường minh nếu tên topic là một phần của hạ tầng được quản lý.
7. Provision topic DLQ, partition, retention, replication và ACL.
8. Kiểm thử lỗi handler, retry exhaustion và việc publish sang DLQ.
9. Xây dựng quy trình điều tra, sửa dữ liệu và replay có audit.
10. Theo dõi backlog, tuổi message, lỗi publish DLQ và kết quả replay.

## 20. Tự kiểm tra

- [ ] Giải thích được vai trò của `enable-dlq`.
- [ ] Biết `dlq-name` chỉ định Kafka topic nhận message lỗi.
- [ ] Giải thích được vì sao Kafka Binder yêu cầu consumer group khi bật DLQ.
- [ ] Phân biệt `destination`, `group` và DLQ topic.
- [ ] Hiểu tên DLQ mặc định được xây dựng từ destination và group theo quy ước binder.
- [ ] Cấu hình được `max-attempts` và backoff trước khi chuyển DLQ.
- [ ] Biết DLQ topic cần provisioning, partition và ACL phù hợp.
- [ ] Hiểu hai consumer group độc lập có thể cần DLQ riêng.
- [ ] Phân biệt retry tại chỗ, retry topic, broker redelivery và DLQ.
- [ ] Thiết kế được quy trình đọc, điều tra và replay message có kiểm soát.
- [ ] Kiểm thử được thiếu group, DLQ name tùy chỉnh, retry exhaustion và lỗi publish DLQ.

## Kết luận

Kafka Binder dùng `enable-dlq` để bật dead-letter handling và `dlq-name` để chọn topic nhận message lỗi. Cơ chế này yêu cầu consumer group ổn định; `destination` xác định topic nguồn, `group` xác định consumer logic và DLQ là topic riêng để lưu record thất bại. Message chỉ nên được chuyển sang DLQ sau chính sách retry đã định, còn topic DLQ phải được provision, cấp quyền, giám sát và có quy trình replay rõ ràng. Tách DLQ theo consumer group giúp các ứng dụng độc lập xử lý lỗi mà không ảnh hưởng lẫn nhau.
