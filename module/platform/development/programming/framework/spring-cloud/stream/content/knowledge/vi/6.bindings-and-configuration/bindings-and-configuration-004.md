# Cấu hình destination, group, binder và contentType

Trong Spring Cloud Stream, binding là điểm kết nối giữa hàm ứng dụng và hệ thống truyền tin. Để một function gửi hoặc nhận đúng thông điệp, binding cần biết destination nào được sử dụng, consumer thuộc group nào, binder nào chịu trách nhiệm kết nối và payload được mã hóa theo content type nào.

Bốn thuộc tính này giải quyết những câu hỏi khác nhau. Destination xác định luồng dữ liệu; group xác định phạm vi subscription của consumer; binder chọn công nghệ broker và cấu hình kết nối; contentType mô tả định dạng payload để framework chuyển đổi dữ liệu. Cấu hình đúng các thuộc tính này giúp ứng dụng hoạt động nhất quán khi triển khai với Kafka, RabbitMQ hoặc Pulsar.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Cấu hình destination cho input và output binding.
- Chọn group ổn định cho consumer và giải thích cách group được ánh xạ trên từng broker.
- Chọn binder mặc định hoặc chỉ định binder riêng cho từng binding.
- Cấu hình nhiều binder trong cùng một ứng dụng khi có nhu cầu tích hợp nhiều broker.
- Chọn content type phù hợp với payload và hiểu vai trò của message converter.
- Đối chiếu cấu hình chung với các thuộc tính chuyên biệt của binder.
- Phát hiện lỗi thường gặp do sai destination, group, binder hoặc content type.

## 1. Bốn thuộc tính cấu hình cốt lõi

Một binding có thể được cấu hình bằng các thuộc tính chung trong `spring.cloud.stream.bindings`. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          binder: kafka
          contentType: application/json
~~~

Trong ví dụ này:

| Thuộc tính | Giá trị | Ý nghĩa |
|---|---|---|
| Binding name | `inventory-in-0` | Input binding của function `inventory` |
| `destination` | `orders` | Luồng thông điệp mà consumer đăng ký nhận |
| `group` | `inventory` | Subscription có tên, giữ tiến độ tiêu thụ theo cơ chế broker |
| `binder` | `kafka` | Binder được chọn để kết nối binding |
| `contentType` | `application/json` | Định dạng payload mà message converter sử dụng |

Không nên xem bốn thuộc tính là các tên khác nhau cho cùng một thứ. Một destination có thể được nhiều group đọc độc lập; nhiều binding có thể dùng cùng binder; một binder có thể kết nối nhiều destination; và các binding khác nhau có thể dùng content type khác nhau.

### Binding name

Tên binding được Spring Cloud Stream suy ra từ tên function bean và hướng dữ liệu. Ví dụ:

- `Supplier<OrderCreated>` tên `orderSource` tạo output binding `orderSource-out-0`.
- `Function<OrderCreated, EnrichedOrder>` tên `enrichOrder` tạo `enrichOrder-in-0` và `enrichOrder-out-0`.
- `Consumer<OrderCreated>` tên `inventory` tạo input binding `inventory-in-0`.

Tên binding là khóa cấu hình. Nếu dùng tên không khớp, cấu hình có thể không được áp dụng cho function mong muốn.

## 2. Cấu hình destination

Destination là tên logic của luồng dữ liệu mà binding gửi tới hoặc nhận từ. Tên này được binder ánh xạ thành tài nguyên tương ứng của broker.

Ví dụ, publisher và consumer cùng trao đổi sự kiện `OrderCreated` qua destination `orders`:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Output binding `orders-out-0` phát thông điệp tới destination `orders`, chẳng hạn khi publisher gửi bằng `StreamBridge`. Input binding `inventory-in-0` đăng ký nhận cùng destination. Nếu producer và consumer nằm ở các ứng dụng khác nhau, chúng vẫn cần thống nhất tên destination và định dạng message.

### Destination được ánh xạ trên các broker

| Broker | Destination thường tương ứng | Ví dụ cần kiểm tra |
|---|---|---|
| Kafka | Topic | Topic `orders`, partition và replication |
| RabbitMQ | Exchange | Exchange `orders`, queue được liên kết và routing key |
| Pulsar | Topic | Topic đầy đủ gồm tenant, namespace và tên topic |

Tên destination trong cấu hình Spring Cloud Stream không nhất thiết là tên hiển thị đầy đủ của tài nguyên broker. Ví dụ, Pulsar có thể thêm tenant và namespace; RabbitMQ có thể tạo queue theo group và prefix; Kafka có thể áp dụng quy tắc đặt tên topic theo môi trường.

Nếu không khai báo destination tường minh, framework có thể dùng tên binding làm tên đích mặc định theo quy tắc của phiên bản đang sử dụng. Với ứng dụng cần hợp đồng tích hợp rõ ràng, nên khai báo destination để tránh việc đổi tên function vô tình làm đổi tên luồng trên broker.

Một destination có thể được nhiều binding sử dụng. Điều này cho phép nhiều consumer độc lập đăng ký cùng luồng sự kiện, hoặc một function nhận từ một destination rồi phát kết quả tới destination khác.

## 3. Cấu hình consumer group

Group xác định một nhóm consumer cùng chia sẻ tiến độ tiêu thụ. Đây là thuộc tính của input binding; output binding không cần group.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
        billing-in-0:
          destination: orders
          group: billing
~~~

Hai input binding trên cùng đọc destination `orders`, nhưng thuộc hai group riêng. Mỗi group có subscription hoặc vị trí đọc độc lập, vì vậy cả nhóm kho và nhóm thanh toán đều có thể nhận cùng một sự kiện.

Nếu chạy nhiều instance của function `inventory`, các instance nên dùng cùng group `inventory` để chia tải. Việc tăng số instance không tạo ra một bản sao riêng của mỗi message cho từng instance trong cùng group.

### Group được ánh xạ theo broker

| Broker | Group thường được biểu diễn bằng | Tiến độ hoặc trạng thái cần quan sát |
|---|---|---|
| Kafka | Consumer group | Offset theo topic và partition |
| RabbitMQ | Queue được tạo/liên kết cho group | Message ready, unacknowledged và consumer |
| Pulsar | Subscription name | Cursor và backlog của subscription |

Một group có tên ổn định giúp consumer tiếp tục từ trạng thái phù hợp sau khi khởi động lại, theo chính sách của broker. Nếu không cấu hình group, binder có thể tạo subscription ẩn danh hoặc queue tạm thời. Tên, vòng đời và khả năng đọc lại của subscription ẩn danh khác nhau giữa các broker; không nên dựa vào chúng cho consumer production cần duy trì tiến độ.

Tên group nên phản ánh vai trò nghiệp vụ thay vì tên instance, ví dụ `inventory`, `billing` hoặc `notification`. Nếu mỗi replica dùng một group khác nhau, mỗi replica có thể nhận toàn bộ luồng sự kiện và tạo ra xử lý trùng ngoài dự kiến.

### Khi nào nên tạo group mới?

Tạo group mới khi một thành phần nghiệp vụ cần nhận luồng sự kiện độc lập, có tiến độ tiêu thụ riêng hoặc cần một chính sách xử lý riêng. Dùng chung group khi các instance chỉ là những bản sao mở rộng của cùng một consumer logic.

Không nên thay tên group trong mỗi lần triển khai. Thay đổi group có thể khiến broker xem đó là một subscription mới; tùy chính sách offset, retention hoặc cursor, consumer có thể đọc lại dữ liệu cũ hoặc bắt đầu từ vị trí khác.

## 4. Chọn binder

Binder là lớp tích hợp giữa binding của Spring Cloud Stream và broker cụ thể. Ứng dụng khai báo function và binding theo mô hình chung, còn binder quản lý việc kết nối, chuyển đổi, gửi, nhận và ánh xạ cấu hình sang Kafka, RabbitMQ hoặc Pulsar.

Nếu classpath chỉ có một binder phù hợp, Spring Cloud Stream có thể tự chọn binder đó. Khi ứng dụng có nhiều binder hoặc cần chọn rõ công nghệ, có thể cấu hình binder mặc định bằng `spring.cloud.stream.defaultBinder`, hoặc chỉ định binder ngay trên từng binding.

Ví dụ chọn Kafka làm binder mặc định:

~~~yaml
spring:
  cloud:
    stream:
      defaultBinder: kafka
      bindings:
        orderSource-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Thuộc tính `defaultBinder` xác định binder được dùng mặc định cho những binding không chỉ định `binder`. Tên binder phải khớp với binder mà ứng dụng đã cấu hình hoặc được tự động đăng ký.

### Chỉ định binder riêng cho một binding

Có thể chọn binder ngay trong cấu hình binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderSource-out-0:
          binder: kafka
          destination: orders
          contentType: application/json
        audit-in-0:
          binder: rabbit
          destination: audit-events
          group: audit
          contentType: application/json
~~~

Cấu hình này cho thấy hai binding được gán cho hai binder khác nhau. Nó không tự động sao chép một message từ Kafka sang RabbitMQ. Muốn chuyển dữ liệu giữa hai broker, ứng dụng phải có luồng xử lý rõ ràng, chẳng hạn một function nhận từ binding Kafka và phát kết quả ra binding RabbitMQ.

## 5. Cấu hình nhiều binder trong một ứng dụng

Một ứng dụng có thể cần kết nối nhiều cụm Kafka, hoặc kết nối Kafka và RabbitMQ cùng lúc. Khi đó, có thể khai báo các binder instance có tên riêng trong `spring.cloud.stream.binders`.

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-east:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: localhost:9092

        rabbit-archive:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: localhost
                port: 5672

      bindings:
        orders-out-0:
          binder: kafka-east
          destination: orders
          contentType: application/json

        archive-in-0:
          binder: rabbit-archive
          destination: order-archive
          group: archive
          contentType: application/json
~~~

Trong cấu hình này:

- `kafka-east` là tên binder instance, có `type: kafka`.
- `rabbit-archive` là tên binder instance, có `type: rabbit`.
- Mỗi binder có môi trường cấu hình riêng để kết nối tới broker tương ứng.
- `orders-out-0` chọn binder `kafka-east`.
- `archive-in-0` chọn binder `rabbit-archive`.

Tên binder instance là bí danh cấu hình trong ứng dụng; nó không nhất thiết phải trùng với hostname hoặc tên cluster. Trường `type` chỉ định loại binder cần được nạp, còn `environment` chứa cấu hình môi trường mà binder cần, chẳng hạn bootstrap servers hoặc địa chỉ RabbitMQ.

Không đưa username, password hoặc token thật vào file cấu hình được commit. Hãy truyền thông tin xác thực qua biến môi trường, secret store hoặc cơ chế cấu hình an toàn của nền tảng triển khai.

### Khi dùng nhiều binder cần kiểm tra gì?

1. Ứng dụng có dependency của tất cả binder cần dùng.
2. Mỗi binder instance có đúng `type` và cấu hình kết nối.
3. Mỗi binding được gán đúng binder.
4. Tên binder trong thuộc tính `binder` khớp tên đã khai báo.
5. Tài khoản ứng dụng có quyền truy cập broker tương ứng.
6. Không vô tình dùng binder mặc định cho một binding cần đi tới broker khác.

Nếu có nhiều binder cùng loại nhưng thuộc các cluster khác nhau, khai báo instance riêng với tên riêng để binding có thể chọn chính xác cluster. Cấu hình riêng giúp tách môi trường và tránh việc producer gửi nhầm vào cluster.

## 6. Cấu hình contentType và chuyển đổi message

Content type mô tả định dạng dữ liệu của payload. Spring Cloud Stream dùng thông tin này để chọn message converter khi chuyển đổi giữa object Java và dữ liệu truyền qua broker.

Ví dụ, ứng dụng gửi một object `OrderCreated` dưới dạng JSON:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total
) {}
~~~

Cấu hình output và input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          contentType: application/json
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Khi publisher gửi object, converter phù hợp có thể tuần tự hóa object thành JSON. Ở phía consumer, converter đọc payload và tạo object Java theo kiểu đầu vào của function.

Content type phổ biến:

| Content type | Dữ liệu thường dùng | Ghi chú |
|---|---|---|
| `application/json` | Object Java, record, JSON document | Thường dùng cho DTO và sự kiện nghiệp vụ |
| `text/plain` | Chuỗi văn bản | Phù hợp với thông điệp text đơn giản |
| `application/octet-stream` | Mảng byte hoặc dữ liệu nhị phân | Ứng dụng chịu trách nhiệm diễn giải byte |
| `application/avro` | Dữ liệu Avro | Cần serializer/converter và schema strategy phù hợp |

Content type cần tương thích giữa producer và consumer. Nếu publisher gửi JSON nhưng consumer diễn giải payload như plain text hoặc một định dạng nhị phân khác, quá trình chuyển đổi có thể thất bại hoặc tạo ra dữ liệu không đúng mong đợi.

### Content type ở cấp binding và message header

Có thể đặt content type riêng cho từng binding qua thuộc tính `contentType`. Metadata của message cũng có thể mang thông tin content type. Khi làm việc với `Message<T>`, cần hiểu header có thể tham gia vào quá trình thương lượng định dạng; không nên tự gắn header mâu thuẫn với payload hoặc cấu hình binding.

Ví dụ tạo message với header tùy chỉnh:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> message =
    MessageBuilder.withPayload(event)
        .setHeader("eventType", "OrderCreated")
        .build();
~~~

Header `eventType` ở trên là metadata nghiệp vụ do ứng dụng tự định nghĩa. Nó không thay thế content type. Content type mô tả cách diễn giải byte payload, còn `eventType` cho biết loại sự kiện mà ứng dụng muốn công bố.

### Chọn content type theo hợp đồng dữ liệu

Hãy thống nhất content type giữa producer và consumer cùng với schema của payload. Với JSON, cần quản lý tên field, kiểu dữ liệu, field bắt buộc và cách thêm field mới. Với Avro hoặc định dạng có schema, cần thống nhất schema version và cơ chế phân phối schema. Content type đúng không tự bảo đảm schema tương thích; nó chỉ cho converter biết loại dữ liệu cần xử lý.

Nếu cần truyền byte đã được serialize bởi client broker hoặc serializer chuyên biệt, có thể cân nhắc native encoding/decoding của binder. Trong trường hợp này, producer và consumer phải thống nhất serializer/deserializer; không nên giả định message converter mặc định sẽ tiếp tục xử lý payload theo cách cũ.

## 7. Phân biệt cấu hình chung và cấu hình riêng của binder

Spring Cloud Stream có hai lớp cấu hình:

- **Cấu hình chung** dưới `spring.cloud.stream.bindings`: destination, group, binder, contentType và các tùy chọn producer/consumer chung.
- **Cấu hình riêng của binder** dưới namespace tương ứng, ví dụ `spring.cloud.stream.kafka.bindings` hoặc `spring.cloud.stream.rabbit.bindings`: những thuộc tính chỉ có ý nghĩa với broker cụ thể.

Ví dụ, các thuộc tính về Kafka consumer hoặc RabbitMQ queue có thể khác nhau. Không nên đặt một thuộc tính đặc thù Kafka rồi mong RabbitMQ binder hiểu nó.

Cấu hình chung:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
          contentType: application/json
~~~

Cấu hình chuyên biệt có thể được thêm bên dưới namespace binder tương ứng theo phiên bản đang dùng. Ví dụ minh họa:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          inventory-in-0:
            consumer:
              startOffset: earliest
~~~

Thuộc tính chuyên biệt và tên trường có thể thay đổi theo binder và phiên bản. Trước khi sử dụng, cần kiểm tra tài liệu đúng phiên bản của binder đã cài đặt. Không sao chép tùy chọn từ một broker sang broker khác chỉ vì chúng có tên gần giống nhau.

## 8. Một cấu hình hoàn chỉnh cho sự kiện đơn hàng

Giả sử hệ thống dùng Kafka để phát sự kiện đơn hàng và consumer kho để xử lý. Function bean:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryFunctions {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            System.out.println(
                "Cập nhật tồn kho cho đơn hàng " + event.orderId()
            );
        };
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      defaultBinder: kafka
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory-service
          contentType: application/json
~~~

Cấu hình kết nối Kafka có thể đặt qua Spring Kafka properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Trong ví dụ này, function `inventory` nhận payload JSON từ topic `orders`, tham gia consumer group `inventory-service` và dùng Kafka binder. Nếu chuyển sang RabbitMQ hoặc Pulsar, logic Consumer có thể giữ nguyên; cấu hình binder, kết nối và một số tùy chọn chuyên biệt cần thay đổi theo broker.

Nếu producer và consumer thuộc hai ứng dụng riêng, cả hai ứng dụng cần thống nhất destination, content type và hợp đồng payload. Group chỉ cần cấu hình ở phía consumer và nên đặt theo vai trò tiêu thụ.

## 9. Quản lý cấu hình theo môi trường

Không nên hard-code hostname hoặc thông tin xác thực của broker vào logic function. Spring Boot hỗ trợ externalized configuration qua file profile, biến môi trường, tham số dòng lệnh hoặc secret store của nền tảng triển khai.

Ví dụ có thể thay địa chỉ broker bằng biến môi trường:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
~~~

Với RabbitMQ, có thể dùng các biến môi trường tương ứng cho host, port và credentials. Khi dùng nhiều binder, mỗi binder có thể có một nhóm cấu hình môi trường riêng. Hãy đặt tên biến có ý nghĩa theo môi trường và broker để tránh dùng nhầm cluster.

Cần phân biệt cấu hình triển khai với cấu hình hợp đồng:

- Destination và content type thường là một phần của hợp đồng tích hợp giữa producer và consumer.
- Group thuộc về cách tổ chức subscription của consumer.
- Broker endpoint và thông tin xác thực phụ thuộc môi trường.
- Các tùy chọn chuyên biệt như partition, acknowledgement, prefetch hoặc native encoding phụ thuộc binder và mục tiêu vận hành.

Nếu đổi destination hoặc content type giữa môi trường mà không cập nhật producer/consumer đồng bộ, message có thể được gửi tới luồng khác hoặc không thể giải mã.

## 10. Kiểm thử và xác minh cấu hình

Sau khi cấu hình, không chỉ kiểm tra ứng dụng có khởi động thành công. Hãy xác minh cả binding và tài nguyên broker.

Quy trình gợi ý:

1. Khởi tạo Spring Application Context và xác nhận function bean được đăng ký.
2. Kiểm tra log để xác nhận binding được tạo với tên dự kiến.
3. Xác nhận binder kết nối đúng broker và đúng cluster.
4. Kiểm tra destination trên broker đã tồn tại hoặc được provision theo cấu hình.
5. Kiểm tra group/queue/subscription có tên đúng.
6. Gửi một message mẫu và xác nhận payload được chuyển đổi đúng.
7. Kiểm tra consumer nhận đúng kiểu dữ liệu và xử lý thành công.
8. Khởi động lại consumer và xác minh group giữ tiến độ theo chính sách broker.

Nên có unit test cho logic function, binding test với test binder và broker integration test cho cấu hình thật. Test binder hữu ích để kiểm tra luồng message ở cấp ứng dụng, nhưng không thay thế kiểm thử mapping destination/group và message conversion trên Kafka, RabbitMQ hoặc Pulsar thật.

## 11. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Function không nhận message | Sai input binding name hoặc function chưa được kích hoạt | Kiểm tra function definition và tên bean |
| Producer và consumer không gặp nhau | Destination khác nhau hoặc binder trỏ tới cluster khác | Đối chiếu destination và binder ở cả hai ứng dụng |
| Mỗi replica nhận toàn bộ message | Mỗi replica dùng group khác nhau | Dùng chung group cho các replica của cùng consumer |
| Consumer không giữ tiến độ sau restart | Group ẩn danh hoặc group name thay đổi | Đặt group ổn định |
| Binding dùng nhầm broker | Thiếu hoặc sai thuộc tính binder/defaultBinder | Kiểm tra binder name và cấu hình instance |
| Không kết nối được broker | Endpoint, credentials, TLS hoặc quyền truy cập sai | Kiểm tra cấu hình môi trường và log binder |
| Payload không deserialize được | Content type hoặc schema không tương thích | Đồng bộ content type và hợp đồng dữ liệu |
| Dữ liệu bị hiểu thành chuỗi/byte | Converter không phù hợp hoặc native decoding đang bật | Kiểm tra content type và serializer/deserializer |
| Một thuộc tính không có tác dụng | Dùng sai namespace hoặc cấu hình đặc thù của binder khác | Đặt thuộc tính đúng namespace và kiểm tra tài liệu phiên bản |
| Message xuất hiện ở destination không mong muốn | Cấu hình profile hoặc biến môi trường ghi đè | Kiểm tra cấu hình có hiệu lực khi chạy |

Khi chẩn đoán, hãy kiểm tra từ ngoài vào trong: endpoint broker, binder, destination, group, binding name, content type và cuối cùng là logic function. Cách làm này giúp xác định lỗi thuộc cấu hình kết nối, định tuyến, subscription hay chuyển đổi dữ liệu.

## 12. Bài thực hành

Tạo một publisher và một consumer cho sự kiện `OrderCreated`:

1. Khai báo function bean consumer `inventory`.
2. Cấu hình input binding `inventory-in-0` với destination `orders`.
3. Đặt group `inventory-service` và content type `application/json`.
4. Cấu hình binder Kafka và địa chỉ broker trong môi trường thử nghiệm.
5. Phát một payload JSON có `eventId`, `orderId` và `total`.
6. Xác nhận consumer nhận đúng object Java.
7. Khởi động thêm một instance consumer với cùng group và quan sát cách broker chia tải.
8. Tạo một consumer độc lập với group `billing-service`, cùng destination `orders`, rồi xác nhận cả hai group đều nhận luồng sự kiện.
9. Trong môi trường thử nghiệm riêng, đổi binding sang RabbitMQ hoặc Pulsar và xác minh tài nguyên broker tương ứng.
10. Thử đổi content type ở một phía để quan sát lỗi chuyển đổi, sau đó đồng bộ lại cấu hình và xác nhận message được giải mã đúng.

Khi hoàn thành, bạn cần giải thích được destination xác định luồng nào, group xác định subscription nào, binder quyết định broker nào và content type quyết định payload được chuyển đổi ra sao.

## Kết luận

Cấu hình binding là nơi Spring Cloud Stream kết nối logic function với hạ tầng truyền tin. Destination xác định luồng dữ liệu, group xác định phạm vi tiêu thụ của consumer, binder chọn công nghệ broker và contentType hướng dẫn chuyển đổi payload.

Hãy đặt tên destination và group ổn định, chỉ định binder rõ ràng khi có nhiều broker, đồng bộ content type giữa producer và consumer, đồng thời kiểm tra tài nguyên và message trên broker thật. Khi giữ các hợp đồng này rõ ràng, ứng dụng có thể thay đổi hạ tầng Kafka, RabbitMQ hoặc Pulsar mà vẫn giữ phần lớn logic nghiệp vụ trong các function bean.

