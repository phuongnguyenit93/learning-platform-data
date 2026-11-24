# Binding đầu vào, binding đầu ra và tài nguyên vật lý trên broker

Trong Spring Cloud Stream, hàm xử lý của ứng dụng kết nối với hệ thống truyền tin thông qua các **binding**. Binding là điểm nối logic ở phía ứng dụng; binder là thành phần tích hợp với broker; còn topic, exchange, queue hoặc subscription là những tài nguyên mà broker thực sự quản lý. Phân biệt ba lớp này giúp cấu hình đúng luồng dữ liệu và tránh nhầm tên binding với tên tài nguyên trên broker.

Module `SPRING_CLOUD_STREAM` sử dụng mô hình hàm `Supplier`/`Function`/`Consumer` và hỗ trợ các broker như Kafka, RabbitMQ hoặc Pulsar. Cùng một hàm Java có thể giữ nguyên khi đổi binder, nhưng cách một binding được ánh xạ thành tài nguyên vật lý phụ thuộc vào broker. Bài thuộc chương **Kiến trúc**, tập trung vào binding đầu vào, binding đầu ra, destination, consumer group và topology tài nguyên tương ứng.

## 1. Ba lớp cần phân biệt

Một luồng message thường đi qua ba lớp:

```text
+------------------------ Ứng dụng Spring -------------------------+
|                                                                  |
|  Supplier / Function / Consumer                                  |
|             |                                                    |
|             v                                                    |
|       Binding đầu ra hoặc đầu vào                                |
+-------------|----------------------------------------------------+
              |
              v
        Binder của broker
              |
              v
   Tài nguyên vật lý trên broker
   Kafka: topic / partition
   RabbitMQ: exchange / queue / binding
   Pulsar: topic / partition / subscription
```

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Hàm ứng dụng | Thực hiện logic nghiệp vụ với payload hoặc message | `validateOrder`, `inventoryProjection` |
| Binding | Điểm kết nối logic giữa hàm và luồng message | `validateOrder-in-0`, `validateOrder-out-0` |
| Binder | Chuyển thao tác gửi/nhận của binding thành thao tác phù hợp với broker | Kafka binder, Rabbit binder, Pulsar binder |
| Destination | Tên đích logic mà cấu hình binding tham chiếu | `orders.placed`, `orders.validated` |
| Tài nguyên vật lý | Đối tượng được broker lưu trữ, định tuyến hoặc theo dõi | Topic, exchange, queue, subscription |

Binding không phải là một topic hay queue. Nó là hợp đồng kết nối ở phía ứng dụng. Destination là tên được cấu hình cho binding; binder diễn giải tên này theo mô hình của broker. Vì vậy, cùng một giá trị `destination: orders.placed` có thể ánh xạ thành topic Kafka, exchange RabbitMQ hoặc topic Pulsar.

## 2. Binding đầu vào và binding đầu ra

Hướng của binding được xác định theo góc nhìn của ứng dụng:

- **Binding đầu vào (input binding):** nhận message từ broker và chuyển message vào hàm xử lý.
- **Binding đầu ra (output binding):** nhận kết quả do hàm tạo ra và gửi message đến broker.

Mô hình hàm Spring Cloud Stream quy ước tên binding dựa trên tên bean hàm và vị trí input/output:

| Kiểu hàm | Hướng message | Tên binding mặc định |
|---|---|---|
| `Supplier<T>` | Tạo message để gửi ra broker | `<functionName>-out-0` |
| `Function<T, R>` | Nhận message rồi phát kết quả | `<functionName>-in-0` và `<functionName>-out-0` |
| `Consumer<T>` | Nhận message để xử lý | `<functionName>-in-0` |

Ví dụ, hàm `validateOrder` nhận sự kiện đơn hàng và tạo sự kiện đã kiểm tra. Binding đầu vào là `validateOrder-in-0`; binding đầu ra là `validateOrder-out-0`. Hậu tố `0` là chỉ số của đối số đầu vào hoặc đầu ra. Với hàm có nhiều đầu vào hoặc nhiều đầu ra, các chỉ số tiếp theo phân biệt từng binding.

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, long total) {}

record OrderValidated(String orderId, long total) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderPlaced, OrderValidated> validateOrder() {
        return event -> {
            if (event.orderId() == null || event.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (event.total() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }
            return new OrderValidated(event.orderId(), event.total());
        };
    }
}
```

Hàm có thể được chọn bằng `spring.cloud.function.definition`. Cấu hình binding đặt destination riêng cho đầu vào và đầu ra:

```yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.placed
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
```

Trong ví dụ này, `validateOrder-in-0` đọc từ destination `orders.placed`; `validateOrder-out-0` ghi đến `orders.validated`. `group` được đặt trên binding đầu vào vì nó xác định nhóm consumer. Binding đầu ra không cần consumer group.

Nếu dùng một `Consumer<OrderValidated>` tên `inventoryProjection`, ứng dụng chỉ có binding `inventoryProjection-in-0`. Nếu dùng một `Supplier<Heartbeat>` tên `heartbeat`, ứng dụng có binding `heartbeat-out-0`. Với supplier, framework thường gọi hàm theo cơ chế polling; lịch phát và khả năng tạo message rỗng cần được cân nhắc theo mục tiêu ứng dụng.

## 3. Destination và tên binding có mục đích khác nhau

Tên binding được sinh từ tên hàm và hướng xử lý. Nó là tên cấu hình mà ứng dụng dùng để điều chỉnh một điểm kết nối. Destination chỉ định luồng hoặc tài nguyên đích mà binding kết nối tới.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: company.sales.order-created.v1
          group: order-validation
        validateOrder-out-0:
          destination: company.sales.order-validated.v1
```

Ở đây tên binding vẫn là `validateOrder-in-0` và `validateOrder-out-0`; tên destination phản ánh quy ước đặt tên topic hoặc exchange của tổ chức. Có thể đổi destination theo môi trường hoặc theo cách tổ chức luồng mà không phải đổi tên bean Java, miễn là cấu hình binding vẫn tham chiếu đúng.

Nên đặt destination theo một quy ước nhất quán, thể hiện miền nghiệp vụ, loại sự kiện và phiên bản hợp đồng khi cần. Tránh dùng tên quá chung như `input`, `output` hoặc `data`, vì chúng khó truy vết khi broker có nhiều luồng. Một destination có thể được nhiều ứng dụng cùng sử dụng nếu hợp đồng message và chính sách truy cập cho phép.

## 4. Binding đầu ra ánh xạ thành tài nguyên nào?

Với binding đầu ra, hàm ứng dụng tạo message và binder chuyển message tới destination. Tài nguyên vật lý phụ thuộc vào binder:

| Binder | Destination đầu ra thường ánh xạ tới | Đường đi của message |
|---|---|---|
| Kafka | Topic, có thể gồm nhiều partition | Producer gửi record đến topic; key và partitioner quyết định partition |
| RabbitMQ | Exchange | Producer publish message đến exchange; exchange định tuyến message đến queue theo binding và routing key |
| Pulsar | Topic, có thể là topic phân vùng | Producer gửi message đến topic; key và cấu hình producer ảnh hưởng định tuyến hoặc thứ tự theo key |

### Kafka

Một output binding với `destination: orders.validated` gửi record đến topic `orders.validated`. Topic có thể gồm nhiều partition để lưu dữ liệu và chia tải. Nếu producer gắn key như `orderId`, các message cùng key thường được định tuyến vào cùng partition theo partitioner đang sử dụng; đây là cơ sở để duy trì thứ tự trong phạm vi partition.

```text
validateOrder-out-0
        |
        v
   Kafka binder
        |
        v
  topic: orders.validated
      |       |       |
   part-0  part-1  part-2
```

### RabbitMQ

Một output binding với destination `orders.validated` thường publish đến exchange tương ứng. Exchange không phải queue; nó áp dụng loại exchange, routing key và các queue binding để quyết định message được chuyển đến đâu.

```text
validateOrder-out-0
        |
        v
   Rabbit binder
        |
        v
 exchange: orders.validated
        |                 |
   routing key       routing key
        |                 |
        v                 v
 queue inventory     queue analytics
```

Nếu không có queue nào được bind phù hợp, message có thể không đến consumer nào, tùy cấu hình exchange và publisher. Do đó, cần thiết kế exchange, routing key và queue binding cùng nhau, đồng thời kiểm tra chính sách xử lý message không được định tuyến.

### Pulsar

Một output binding với destination `orders.validated` gửi message đến topic Pulsar tương ứng. Topic có thể được phân vùng để tăng khả năng xử lý song song. Consumer subscription được tạo ở phía nhận; producer chỉ cần gửi đến topic và áp dụng key hoặc thuộc tính message theo yêu cầu định tuyến.

## 5. Binding đầu vào ánh xạ thành tài nguyên nào?

Binding đầu vào đọc message từ destination. Thuộc tính `group` rất quan trọng vì nó xác định cách nhiều instance của ứng dụng phối hợp nhận message và cách các nhóm độc lập nhận bản sao luồng dữ liệu.

| Binder | Destination đầu vào | Vai trò của `group` |
|---|---|---|
| Kafka | Topic | Là consumer group ID; các instance cùng group chia partition và phối hợp offset. Group khác có thể đọc topic độc lập |
| RabbitMQ | Exchange được binder kết nối thông qua queue | Thường xác định queue dành cho nhóm consumer; các instance cùng group cùng tiêu thụ queue, group khác có queue riêng được bind vào exchange |
| Pulsar | Topic | Được binder dùng để xác định subscription; các consumer trong cùng subscription phối hợp theo subscription type |

### Kafka: topic và consumer group

Khi cấu hình:

```yaml
spring:
  cloud:
    stream:
      bindings:
        inventoryProjection-in-0:
          destination: orders.validated
          group: inventory-projection
```

Kafka binder tạo consumer đọc topic `orders.validated` với group ID `inventory-projection`. Kafka quản lý offset theo topic, partition và consumer group. Nhiều instance có cùng group ID sẽ chia nhau các partition được gán; một partition trong group chỉ được gán cho một consumer tại một thời điểm. Một group khác, chẳng hạn `analytics-projection`, có offset riêng và có thể đọc lại cùng topic độc lập.

```text
                 topic: orders.validated
                    /    |    \
                   /     |     \
                p0      p1      p2
                 \      |      /
                  \     |     /
             group: inventory-projection
                 instance A / B

             group: analytics-projection
                 instance C
```

Consumer group Kafka là định danh phối hợp và lưu offset; nó không phải topic hay queue mà quản trị viên phải tạo trước như một tài nguyên dữ liệu độc lập. Nếu không khai báo group, binder thường tạo định danh nhóm ẩn danh riêng cho consumer binding. Hành vi lưu offset và khả năng đọc lại cần được cân nhắc khi ứng dụng khởi động lại.

### RabbitMQ: exchange, queue và group

Rabbit binder sử dụng exchange làm destination và queue làm điểm nhận của consumer. Khi có group, binder thường khai báo queue gắn với exchange theo cấu hình của binding. Nhiều instance cùng group đọc chung queue, nhờ đó message được chia cho các instance. Một group khác có queue riêng được bind vào cùng exchange và có thể nhận một bản sao của luồng message.

```text
                exchange: orders.validated
                      |
              +-------+-------+
              |               |
              v               v
       queue inventory   queue analytics
          group A           group B
          /    \               |
       app 1  app 2          app 3
```

Trong RabbitMQ, group có ý nghĩa gắn với queue nhận. Nếu không khai báo group, binder có thể sử dụng queue ẩn danh với vòng đời và độ bền khác queue có tên ổn định. Cần xem xét cấu hình durable, exclusive, auto-delete, routing key và quyền khai báo tài nguyên khi triển khai.

### Pulsar: topic và subscription

Pulsar tách topic khỏi subscription. Topic lưu luồng message; subscription giữ trạng thái tiêu thụ như vị trí đọc và cách phân phối cho consumer. Binder dùng group để xác định subscription cho binding đầu vào. Các instance dùng cùng subscription tham gia một luồng tiêu thụ chung; subscription khác có thể đọc cùng topic độc lập.

Subscription type ảnh hưởng đến cách phân phối:

| Subscription type | Cách phối hợp tổng quát | Trường hợp thường cân nhắc |
|---|---|---|
| Exclusive | Một consumer hoạt động trên subscription | Một luồng nhận đơn giản, cần một consumer |
| Failover | Một consumer hoạt động, consumer khác chờ tiếp quản | Cần một consumer chính và khả năng chuyển đổi khi lỗi |
| Shared | Nhiều consumer cùng nhận message để chia tải | Throughput cao, không yêu cầu thứ tự tổng thể |
| Key_Shared | Nhiều consumer chia tải theo key | Muốn xử lý song song giữa các key và giữ affinity/thứ tự theo key theo cấu hình tương thích |

Tên subscription, loại subscription và key ordering phải được cấu hình nhất quán giữa producer, binder và consumer. Chọn `Shared` chỉ để tăng throughput có thể không phù hợp nếu nghiệp vụ đòi hỏi thứ tự theo từng đơn hàng.

## 6. Một destination có thể có nhiều consumer độc lập

Một luồng sự kiện thường phục vụ nhiều mục đích. Sau khi đơn hàng được xác nhận, hệ thống kho cập nhật tồn, hệ thống phân tích cập nhật số liệu và dịch vụ thông báo gửi email. Các ứng dụng này không nhất thiết phải gọi trực tiếp lẫn nhau; chúng có thể nhận cùng một luồng sự kiện qua những group hoặc subscription riêng.

```text
Producer: Order Service
          |
          v
    orders.placed
          |
   +------+------+----------------+
   |             |                |
   v             v                v
Inventory     Analytics       Notification
group         group           group
   |             |                |
   v             v                v
Update stock  Update metrics  Send message
```

Trong Kafka, mỗi group có offset độc lập. Trong RabbitMQ, mỗi group consumer thường có queue riêng được bind vào exchange. Trong Pulsar, mỗi group tương ứng với subscription độc lập. Cách biểu diễn khác nhau nhưng mục tiêu kiến trúc tương tự: nhiều ứng dụng có thể phản ứng độc lập với cùng một sự kiện.

Ngược lại, nhiều instance thuộc cùng một group thường chia tải để cùng thực hiện một vai trò xử lý. Nếu muốn cả hai ứng dụng đều nhận mọi message, không nên đặt chúng vào cùng một nhóm tiêu thụ dùng chung.

## 7. Cấu hình binding theo từng môi trường

Tên destination thường khác nhau giữa local, staging và production. Có thể tách cấu hình theo profile hoặc biến môi trường để cùng một hàm Java kết nối tới tài nguyên phù hợp:

```yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: ${ORDERS_INPUT_DESTINATION:orders.placed}
          group: ${ORDERS_CONSUMER_GROUP:order-validation}
          content-type: application/json
        validateOrder-out-0:
          destination: ${ORDERS_OUTPUT_DESTINATION:orders.validated}
          content-type: application/json
```

Các biến môi trường cho phép thay destination và group mà không sửa code. Với nhiều binder, binding có thể chỉ định binder cần dùng theo cấu hình Spring Cloud Stream; khi đó cần bảo đảm dependency binder tương ứng đã có trong ứng dụng và cấu hình kết nối broker phù hợp.

Không nên đặt địa chỉ broker, mật khẩu hoặc token trực tiếp trong file cấu hình được commit. Dùng biến môi trường, secret manager hoặc cơ chế quản lý bí mật của nền tảng triển khai. Destination và group không phải thông tin xác thực, nhưng vẫn nên tuân theo quy ước đặt tên để tránh kết nối nhầm môi trường.

## 8. Provisioning và vòng đời tài nguyên

Binder có thể hỗ trợ khai báo hoặc tạo tài nguyên vật lý khi ứng dụng khởi động. Tuy nhiên, khả năng tự tạo phụ thuộc vào binder, phiên bản, cấu hình và quyền của tài khoản kết nối. Một số môi trường broker cũng tắt tự tạo topic hoặc giới hạn quyền khai báo exchange/queue.

Trước khi triển khai, cần xác định ai chịu trách nhiệm tạo và quản lý tài nguyên:

- **Tạo tự động bởi binder:** thuận tiện khi phát triển local hoặc môi trường thử nghiệm. Cần hiểu rõ tên, thuộc tính mặc định và quyền cần thiết.
- **Provisioning bên ngoài:** quản trị viên hoặc pipeline hạ tầng tạo topic, partition, exchange, queue, subscription, retention và policy trước khi ứng dụng chạy. Cách này giúp review thay đổi tài nguyên và giới hạn quyền runtime.
- **Kết hợp:** nền tảng tạo tài nguyên cốt lõi; binder chỉ khai báo những thành phần được phép hoặc xác thực cấu hình khi kết nối.

Một checklist cho mỗi destination:

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Tên và namespace | Có quy ước môi trường, miền nghiệp vụ và phiên bản không? |
| Quyền truy cập | Producer được publish ở đâu? Consumer được đọc hoặc khai báo tài nguyên nào? |
| Dung lượng và song song | Kafka/Pulsar cần bao nhiêu partition? RabbitMQ cần bao nhiêu queue hoặc consumer? |
| Lưu giữ | Message được giữ bao lâu? Có cần replay sau sự cố không? |
| Độ bền | Tài nguyên có durable/persistent theo yêu cầu không? |
| Lỗi | Retry, dead-letter exchange/topic/queue và chính sách phát lại được thiết lập thế nào? |
| Vòng đời | Ai tạo, thay đổi, giám sát và xóa tài nguyên? |

Không nên xóa topic, queue hoặc subscription chỉ vì một instance ứng dụng đã dừng. Các tài nguyên này có thể chứa dữ liệu chưa tiêu thụ hoặc offset cần cho lần khởi động tiếp theo. Việc thay đổi retention, partition hoặc xóa subscription cần theo quy trình vận hành đã thống nhất.

## 9. Những khác biệt cần giữ trong thiết kế đa broker

Spring Cloud Stream giúp ứng dụng dùng cùng mô hình hàm, nhưng abstraction không làm cho broker trở nên giống nhau hoàn toàn.

| Khía cạnh | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Đích đầu ra | Topic | Exchange | Topic |
| Điểm nhận đầu vào | Topic + consumer group | Queue được bind với exchange | Topic + subscription |
| Phân phối trong một nhóm | Chia partition cho consumer | Nhiều consumer đọc queue | Theo subscription type |
| Nhóm độc lập | Consumer group khác, offset riêng | Queue khác cùng bind exchange | Subscription khác |
| Thứ tự | Trong một partition | Queue có thứ tự giao cơ bản; nhiều consumer/requeue có thể làm khác thứ tự hoàn tất | Phụ thuộc partition, subscription type và key |
| Lưu vị trí tiêu thụ | Offset theo group và partition | Trạng thái message/ack của queue | Cursor của subscription |

Khi chuyển binder, cần kiểm tra lại ít nhất các điểm sau:

1. Destination có ánh xạ sang đúng loại tài nguyên không?
2. Group có mang đúng ngữ nghĩa chia tải hay nhận bản sao không?
3. Cơ chế định tuyến, partition key hoặc ordering key có được cấu hình lại không?
4. Cách xác nhận, retry, DLQ và replay có thay đổi không?
5. Tài nguyên có được tạo đúng quyền, độ bền và retention không?

Nếu nghiệp vụ phụ thuộc vào một tính năng riêng của broker, hãy thể hiện rõ phụ thuộc đó trong cấu hình và tài liệu vận hành. Đừng dựa vào giả định rằng đổi tên binder là đủ để chuyển toàn bộ topology.

## 10. Ví dụ một luồng từ đầu đến cuối

Giả sử dịch vụ đặt hàng nhận một yêu cầu tạo đơn và phát `OrderPlaced`. Một hàm `validateOrder` đọc sự kiện, kiểm tra dữ liệu và phát `OrderValidated`. Hai consumer khác nhau nhận sự kiện đã xác thực: một consumer cập nhật tồn kho, consumer còn lại cập nhật phân tích.

```text
Order API
   |
   v
orders.placed
   |
   v
validateOrder-in-0
   |
   v
Function validateOrder
   |
   v
validateOrder-out-0
   |
   v
orders.validated
   |                         |
   v                         v
inventory-projection      analytics-projection
   |                         |
   v                         v
Update inventory          Update metrics
```

Trong cấu hình Kafka, `orders.placed` và `orders.validated` là topic; `inventory-projection` và `analytics-projection` là hai consumer group có offset độc lập. Trong RabbitMQ, hai group thường có hai queue riêng được bind vào exchange `orders.validated`. Trong Pulsar, hai group tạo hai subscription riêng trên topic. Cùng một sơ đồ logic được triển khai bằng topology vật lý khác nhau.

Điểm cần kiểm tra khi vận hành là producer đã publish vào đúng destination, binder đã kết nối đúng broker, consumer binding đã subscribe đúng destination và các nhóm consumer đã được tạo theo ý định. Khi chỉ một consumer không nhận được message, cần kiểm tra queue/subscription/group của chính consumer đó, không chỉ kiểm tra producer có gửi thành công hay chưa.

## 11. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Hàm không có binding như mong đợi | Tên hàm không nằm trong `spring.cloud.function.definition` hoặc tên binding bị gõ sai | Kiểm tra bean function và binding name được suy ra |
| Producer gửi nhưng consumer không nhận | Destination đầu ra và đầu vào không trùng, hoặc topology RabbitMQ không có queue/routing binding phù hợp | Kiểm tra destination, exchange, queue, routing key và quyền publish/consume |
| Chỉ một trong hai ứng dụng nhận message | Hai consumer vô tình dùng chung group/queue/subscription nên chia tải | Xác định có cần group độc lập cho mỗi ứng dụng hay không |
| Nhiều instance cùng ứng dụng đều nhận mọi message | Mỗi instance dùng group ẩn danh riêng hoặc cấu hình group không nhất quán | Kiểm tra group ID, queue hoặc subscription name |
| Kafka consumer không xử lý song song như kỳ vọng | Số partition ít hơn số consumer hoặc phân phối partition không cân bằng | Kiểm tra partition count và consumer group assignment |
| RabbitMQ có exchange nhưng consumer không có message | Queue chưa được khai báo hoặc chưa bind đúng routing key | Kiểm tra queue, binding, exchange type và routing key |
| Pulsar subscription không đúng trạng thái mong đợi | Tên subscription hoặc subscription type khác giữa các cấu hình | Kiểm tra subscription trên topic và cấu hình binder |
| Ứng dụng khởi động nhưng không tạo được tài nguyên | Broker cấm auto-provisioning hoặc tài khoản thiếu quyền | Kiểm tra quyền, chính sách broker và provisioning ngoài |

Khi debug, hãy lần theo luồng từ hàm đến binding, từ binding đến binder, rồi đến tài nguyên vật lý. Log tên binding và destination giúp xác định cấu hình ứng dụng; công cụ quản trị broker giúp xác nhận topic, exchange, queue, partition hoặc subscription thực sự tồn tại.

## 12. Tự kiểm tra

- [ ] Phân biệt được hàm ứng dụng, binding, binder, destination và tài nguyên vật lý.
- [ ] Xác định đúng tên binding đầu vào/đầu ra của `Supplier`, `Function` và `Consumer`.
- [ ] Giải thích được vì sao tên binding không nhất thiết giống tên destination.
- [ ] Mô tả được output binding ánh xạ tới topic Kafka, exchange RabbitMQ hoặc topic Pulsar.
- [ ] Mô tả được input binding kết hợp với consumer group, queue hoặc subscription.
- [ ] Phân biệt nhóm consumer cùng chia tải với các nhóm độc lập cùng nhận một luồng sự kiện.
- [ ] Biết các tài nguyên vật lý cần provisioning và giám sát trước khi triển khai production.
- [ ] Biết cần kiểm tra lại ngữ nghĩa broker khi chuyển binder.

## Kết luận

Binding là điểm kết nối logic giữa hàm ứng dụng và luồng message; destination đặt tên cho đích mà binding sử dụng; binder ánh xạ kết nối đó sang tài nguyên của broker. Với Kafka, đầu ra là topic và đầu vào kết hợp topic với consumer group. Với RabbitMQ, producer publish vào exchange còn consumer nhận qua queue được bind vào exchange. Với Pulsar, producer gửi đến topic và consumer đọc qua subscription. Hiểu rõ ánh xạ này giúp cấu hình đúng luồng, chia tải đúng cách, tạo topology phù hợp và vận hành Spring Cloud Stream an toàn trên nhiều broker.
