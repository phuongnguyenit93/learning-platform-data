# Binder environment, ngữ cảnh riêng và kế thừa cấu hình

Spring Cloud Stream cho phép một ứng dụng dùng nhiều binder để kết nối nhiều message broker. Một ứng dụng có thể đọc đơn hàng từ Kafka, phát thông báo sang RabbitMQ, hoặc kết nối đồng thời hai cụm Kafka khác nhau. Khi đó, mỗi binder cần biết loại broker, địa chỉ, thông tin xác thực và các cấu hình riêng của nó.

Spring Cloud Stream quản lý binder trong các application context riêng. Cấu hình spring.cloud.stream.binders.<name> tạo một binder configuration có tên; phần environment cung cấp thuộc tính Spring Boot cho binder đó; inheritEnvironment quyết định binder có kế thừa environment của ứng dụng hay không; defaultCandidate quyết định cấu hình có được xét làm binder mặc định hay chỉ dùng khi binding chỉ rõ tên.

Hiểu các ranh giới này giúp tránh tình trạng hai binder cùng đọc một cấu hình kết nối toàn cục, bean tùy chỉnh không xuất hiện trong binder context, hoặc một binding vô tình chọn nhầm broker.

## 1. Binder là lớp kết nối với broker

Binder là thành phần triển khai Spring Cloud Stream Binder SPI. Nó ánh xạ khái niệm binding của ứng dụng sang middleware cụ thể:

| Binder | Middleware thường dùng | Ví dụ destination |
|---|---|---|
| Kafka binder | Apache Kafka | Topic orders.submitted |
| Rabbit binder | RabbitMQ | Exchange orders.events |
| Pulsar binder | Apache Pulsar | Topic persistent://tenant/ns/orders |

Ứng dụng làm việc với function và binding. Binder đảm nhiệm việc kết nối broker, tạo consumer/producer, ánh xạ destination, chuyển đổi message và áp dụng các tùy chọn riêng của middleware.

Ví dụ function chuyển tiếp đơn hàng:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Order(String orderId, String customerId, int amount) {}

@Configuration
class OrderForwardingConfiguration {

    @Bean
    Function<Order, Order> forwardOrder() {
        return order -> order;
    }
}
~~~

Với function này, Spring Cloud Stream tạo hai binding:

- forwardOrder-in-0: đầu vào của function.
- forwardOrder-out-0: đầu ra của function.

Function không cần biết input đến từ Kafka hay RabbitMQ. Binding configuration chọn binder cụ thể cho mỗi đầu vào và đầu ra.

## 2. Binder được phát hiện trên classpath

Mỗi binder implementation cung cấp metadata trong META-INF/spring.binders. Metadata này ánh xạ tên binder, chẳng hạn kafka hoặc rabbit, tới lớp cấu hình cần khởi tạo binder.

Quy tắc phát hiện phổ biến:

- Nếu chỉ có một binder implementation trên classpath, Spring Cloud Stream có thể tự dùng binder đó.
- Nếu có nhiều loại binder, ứng dụng cần chọn binder cho từng binding hoặc đặt binder mặc định.
- Nếu cần kết nối nhiều broker cùng loại, khai báo nhiều binder configuration có tên riêng, cùng type nhưng khác environment.

Ví dụ khi classpath có Kafka và Rabbit binder:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consumeOrders-in-0:
          destination: orders.submitted
          group: order-processor
          binder: kafka
        publishAlerts-out-0:
          destination: operations.alerts
          binder: rabbit
~~~

Ở đây kafka và rabbit là tên loại binder được phát hiện từ metadata. Mỗi binding chọn binder độc lập. Nếu không khai báo binder trên một binding, Spring Cloud Stream dùng binder mặc định nếu đã xác định được.

Có thể đặt binder mặc định bằng spring.cloud.stream.defaultBinder. Cách này hữu ích khi phần lớn binding dùng chung một binder và chỉ một vài binding cần chỉ định riêng. Trong ứng dụng có nhiều cấu hình binder cùng loại, hãy dùng tên cấu hình chính xác trên từng binding hoặc xác định rõ một cấu hình mặc định; tránh dựa vào lựa chọn ngầm khi có nhiều ứng viên.

## 3. Phân biệt binder type và binder configuration name

Hai khái niệm này có vai trò khác nhau:

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| type | kafka | Loại binder implementation cần khởi tạo |
| Configuration name | kafka-east | Tên một cấu hình binder cụ thể trong ứng dụng |
| bindings.<binding>.binder | kafka-east | Chọn cấu hình binder mà binding sử dụng |

Một ứng dụng có thể khai báo hai cấu hình cùng loại:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-east:
          type: kafka
        kafka-west:
          type: kafka
~~~

kafka-east và kafka-west là hai configuration name. Cả hai đều sử dụng binder type kafka, nhưng có thể kết nối tới hai cụm broker khác nhau.

Đừng đặt bindings.<binding>.binder thành kafka nếu binding cần dùng cấu hình có tên kafka-east. Khi đã khai báo nhiều cấu hình cùng loại, binding cần tham chiếu đúng configuration name để xác định environment tương ứng.

## 4. Kết nối hai broker cùng loại bằng hai environment

Đây là trường hợp thường gặp khi một dịch vụ đọc dữ liệu từ cụm Kafka nội bộ rồi ghi bản sao sang cụm Kafka lưu trữ, hoặc khi kết nối hai RabbitMQ cluster của hai miền nghiệp vụ.

Ví dụ một function đọc đơn hàng từ Kafka ở khu vực east và ghi sang Kafka ở khu vực west:

~~~yaml
spring:
  cloud:
    function:
      definition: forwardOrder
    stream:
      bindings:
        forwardOrder-in-0:
          destination: orders.raw
          group: order-forwarder
          binder: kafka-east
        forwardOrder-out-0:
          destination: orders.archive
          binder: kafka-west
      binders:
        kafka-east:
          type: kafka
          defaultCandidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: east-kafka.internal:9092
        kafka-west:
          type: kafka
          defaultCandidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: west-kafka.internal:9092
~~~

Trong cấu hình:

- kafka-east và kafka-west có cùng type: kafka.
- Mỗi binder có một địa chỉ broker riêng trong environment.
- Input binding chọn kafka-east.
- Output binding chọn kafka-west.
- defaultCandidate: false đánh dấu các cấu hình này chỉ được chọn khi tham chiếu tường minh.

Với cấu hình tường minh như trên, hãy khai báo binder cho mọi binding cần dùng. Việc tạo binder configuration riêng không tự động chuyển tất cả binding sang broker đó.

## 5. Mỗi binder có một environment riêng

environment là gốc của các thuộc tính Spring Boot được dùng để tùy chỉnh binder. Các thuộc tính được đặt dưới tên cấu hình:

~~~text
spring.cloud.stream.binders.<configurationName>.environment
~~~

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbit-notifications:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit-alerts.internal
                port: 5672
                username: ${RABBIT_ALERTS_USERNAME}
                password: ${RABBIT_ALERTS_PASSWORD}
~~~

Các thuộc tính dưới environment được áp dụng cho binder rabbit-notifications. Chúng không phải cấu hình binding và cũng không thay đổi destination hoặc consumer group.

environment có thể chứa thuộc tính Spring Boot khác ngoài địa chỉ broker. Tài liệu Spring Cloud Stream minh họa việc thêm cấu hình riêng qua spring.main.sources và kích hoạt profile riêng qua spring.profiles.active.

Ví dụ thêm một lớp cấu hình chỉ dành cho binder:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-secure:
          type: kafka
          environment:
            spring:
              main:
                sources: com.example.messaging.KafkaSecureBinderConfiguration
              profiles:
                active: kafka-secure
~~~

Lớp KafkaSecureBinderConfiguration được nạp trong môi trường binder tương ứng. Hãy đặt lớp cấu hình này trong ứng dụng và bảo đảm các dependency cần thiết có trên classpath.

## 6. inheritEnvironment: kế thừa environment của ứng dụng

inheritEnvironment điều khiển việc binder configuration có kế thừa environment của ứng dụng hay không.

| Giá trị | Hành vi |
|---|---|
| true | Kế thừa environment của ứng dụng; đây là mặc định |
| false | Không kế thừa environment của ứng dụng; binder cần có đủ thuộc tính riêng trong environment của nó |

Mặc định:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-east:
          type: kafka
          inheritEnvironment: true
~~~

Khi để true, binder có thể sử dụng các thuộc tính chung của môi trường ứng dụng nếu chúng phù hợp. Điều này tiện lợi khi nhiều binder dùng chung một số cấu hình như profile, logging hoặc thuộc tính nền tảng.

Khi đặt false, binder không dựa vào environment của ứng dụng. Cần khai báo đầy đủ các thuộc tính binder cần dùng trong environment hoặc cung cấp chúng bằng nguồn cấu hình riêng tương ứng.

Ví dụ binder được cô lập khỏi environment ứng dụng:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-archive:
          type: kafka
          inheritEnvironment: false
          defaultCandidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: archive-kafka.internal:9092
                      autoCreateTopics: false
~~~

Với cấu hình này, không nên giả định các thuộc tính đặt ở cấp spring.kafka.* hoặc các property source chỉ có trong application environment sẽ tự xuất hiện trong binder. Hãy khai báo các thuộc tính kết nối, bảo mật và cấu hình cần thiết trong đúng environment.

## 7. Binder context và application context

Spring Cloud Stream quản lý binder trong application context riêng. Trong ứng dụng có nhiều binder, mỗi binder có thể có các bean và cấu hình kết nối riêng. Điều này cho phép hai Kafka binder dùng hai KafkaAdmin, producer factory hoặc consumer factory khác nhau mà không buộc chúng dùng chung một cấu hình kết nối.

Có hai phạm vi cần phân biệt:

| Phạm vi | Chứa những gì? | Ví dụ |
|---|---|---|
| Application context | Function, service, controller và cấu hình nghiệp vụ của ứng dụng | OrderForwardingConfiguration |
| Binder context | Binder implementation và các thành phần kết nối broker của binder | Kafka binder, Rabbit binder, client factory |

Khi thuộc tính environment được khai báo cho binder, Spring Cloud Stream tạo binder context không phải context con của application context. Cơ chế này cho phép tách thành phần binder khỏi bean nghiệp vụ của ứng dụng.

inheritEnvironment và environment liên quan nhưng không thay thế nhau:

- inheritEnvironment quyết định binder có nhận environment của ứng dụng hay không.
- environment cung cấp property set dành riêng cho binder.
- Việc có binder context riêng không có nghĩa function hoặc service nghiệp vụ được tự động tạo lại trong context đó.

Không nên đặt business service trong cấu hình chỉ dành cho binder rồi mong function context có thể sử dụng bean đó như bean ứng dụng. Hãy giữ logic nghiệp vụ ở application context; dùng binder context cho client và cấu hình middleware.

## 8. Kế thừa cấu hình khác với chia sẻ bean

Kế thừa environment là việc binder nhận các property source và cấu hình môi trường theo chính sách đã chọn. Nó không đồng nghĩa mọi bean trong application context đều được chia sẻ vào binder context.

Ví dụ, application context có bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderBusinessConfiguration {

    @Bean
    OrderValidator orderValidator() {
        return new OrderValidator();
    }
}
~~~

Không nên giả định binder context riêng sẽ có thể tự động inject OrderValidator. Bean này phục vụ logic nghiệp vụ và nên được inject vào Function hoặc service ở application context.

Ngược lại, một cấu hình Kafka client hoặc một bean tùy chỉnh chuyên dùng cho Kafka binder có thể được nạp trong binder context bằng environment.spring.main.sources, nếu binder cần bean đó.

Khi cần tùy chỉnh binder theo chương trình, có cơ chế BinderCustomizer dành cho ứng dụng nhiều binder. Spring Cloud Stream áp dụng customizer trước khi ứng dụng bắt đầu sử dụng binder. Customizer có thể kiểm tra binder type và binder name để chỉ thay đổi đúng instance cần thiết.

Ví dụ khung:

~~~java
import org.springframework.cloud.stream.binder.BinderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class BinderCustomizationConfiguration {

    @Bean
    BinderCustomizer binderCustomizer() {
        return (binder, binderName) -> {
            if ("kafka-east".equals(binderName)) {
                // Áp dụng tùy chỉnh dành riêng cho binder kafka-east.
            }
        };
    }
}
~~~

Nếu có nhiều binder cùng type, binderName giúp phân biệt instance. Chỉ kiểm tra instanceof KafkaMessageChannelBinder là chưa đủ nếu chỉ muốn thay đổi một trong hai Kafka cluster.

## 9. defaultCandidate: binder có được xét làm mặc định?

defaultCandidate quyết định một binder configuration có được tham gia quá trình chọn binder mặc định hay chỉ dùng khi binding tham chiếu rõ tên.

| Giá trị | Ý nghĩa |
|---|---|
| true | Có thể được xem là ứng viên mặc định |
| false | Chỉ dùng khi được chọn tường minh bằng tên cấu hình |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-primary:
          type: kafka
          defaultCandidate: true
        kafka-secondary:
          type: kafka
          defaultCandidate: false
~~~

Binding cần dùng cụm phụ phải khai báo:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        archive-out-0:
          destination: orders.archive
          binder: kafka-secondary
~~~

defaultCandidate: false hữu ích khi framework hoặc thư viện tạo một binder configuration bổ sung để tham chiếu riêng. Cấu hình đó không nên làm thay đổi quá trình chọn default binder của ứng dụng.

Giá trị mặc định của thuộc tính là true. Nếu khai báo nhiều binder configuration có thể trở thành ứng viên mặc định, hãy chỉ định rõ binder mặc định hoặc gắn binder name vào từng binding. Tránh để một binding phụ thuộc vào thứ tự khởi tạo hoặc lựa chọn ngầm.

## 10. Phân biệt ba loại cấu hình

Một ứng dụng nhiều binder có ít nhất ba phạm vi cấu hình:

| Phạm vi | Prefix | Mục đích |
|---|---|---|
| Binder configuration | spring.cloud.stream.binders.<name> | Chọn binder type, environment, kế thừa và default candidate |
| Binding | spring.cloud.stream.bindings.<bindingName> | Chọn binder, destination, group, content type và thuộc tính binding chung |
| Binder-specific binding properties | spring.cloud.stream.<binderType>.bindings.<bindingName> | Cấu hình producer/consumer mở rộng riêng cho loại binder |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-east:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: east-kafka.internal:9092
      bindings:
        orders-in-0:
          binder: kafka-east
          destination: orders.raw
          group: order-service
          consumer:
            concurrency: 3
      kafka:
        bindings:
          orders-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Ở đây:

- binders.kafka-east.environment cấu hình broker của binder.
- bindings.orders-in-0.binder chọn binder configuration.
- bindings.orders-in-0.destination và group cấu hình binding.
- kafka.bindings.orders-in-0.consumer chứa tùy chọn mở rộng riêng của Kafka binder.

Không đặt destination hoặc group vào binders.<name>.environment để thay thế binding properties. Binder environment cấu hình binder instance; binding properties xác định cách một binding cụ thể sử dụng binder.

## 11. Binding-level binder selection và defaultBinder

Có hai cách chọn binder:

**Chọn trực tiếp trên từng binding**

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input-in-0:
          binder: kafka
        output-out-0:
          binder: rabbit
~~~

Cách này rõ ràng khi ứng dụng có nhiều middleware hoặc nhiều broker.

**Chọn binder mặc định cho các binding chưa khai báo**

~~~yaml
spring:
  cloud:
    stream:
      defaultBinder: kafka
      bindings:
        orders-in-0:
          destination: orders
        alerts-out-0:
          destination: alerts
          binder: rabbit
~~~

Ở đây binding orders-in-0 dùng default binder, còn alerts-out-0 ghi đè lựa chọn bằng binder riêng.

Với cấu hình nhiều binder cùng loại, hãy xác định tên configuration phù hợp và tham chiếu rõ ràng. Nếu đã bật explicit binder configurations, tất cả binder cần sử dụng phải có trong danh sách cấu hình; không giả định cơ chế phát hiện mặc định sẽ tự bổ sung một binder còn thiếu.

## 12. Cấu hình nhiều loại broker trong cùng ứng dụng

Một ứng dụng có thể dùng Kafka để nhận sự kiện nghiệp vụ và RabbitMQ để phát cảnh báo:

~~~yaml
spring:
  cloud:
    function:
      definition: notifyOrder
    stream:
      bindings:
        notifyOrder-in-0:
          destination: orders.accepted
          group: notification-service
          binder: kafka-events
        notifyOrder-out-0:
          destination: order.notifications
          binder: rabbit-alerts
      binders:
        kafka-events:
          type: kafka
          defaultCandidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka.internal:9092
        rabbit-alerts:
          type: rabbit
          defaultCandidate: false
          environment:
            spring:
              rabbitmq:
                host: rabbit.internal
                port: 5672
                username: ${RABBIT_USERNAME}
                password: ${RABBIT_PASSWORD}
~~~

Function có thể chuyển đổi dữ liệu đầu vào thành thông báo đầu ra:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderAccepted(String orderId, String customerId) {}

record OrderNotification(
    String orderId,
    String customerId,
    String message
) {}

@Configuration
class NotificationConfiguration {

    @Bean
    Function<OrderAccepted, OrderNotification> notifyOrder() {
        return event -> new OrderNotification(
            event.orderId(),
            event.customerId(),
            "Đơn hàng đã được chấp nhận"
        );
    }
}
~~~

Input và output được ánh xạ sang hai binder khác nhau. Binder Kafka chịu trách nhiệm đọc topic orders.accepted; Rabbit binder chịu trách nhiệm gửi đến exchange order.notifications.

Một Function dùng hai binder không tạo ra transaction phân tán giữa Kafka và RabbitMQ. Nếu input offset đã được commit nhưng publish sang RabbitMQ thất bại, hoặc publish đã thành công nhưng input bị giao lại, ứng dụng cần xử lý idempotency và retry phù hợp. Không suy ra rằng hai binder cùng nằm trong một Spring Boot application thì có thể commit nguyên tử.

## 13. Tách profile và cấu hình theo môi trường triển khai

Một binder có thể dùng profile riêng:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbit-staging:
          type: rabbit
          environment:
            spring:
              profiles:
                active: staging-rabbit
~~~

Profile được kích hoạt trong binder environment. Cấu hình profile đó có thể chứa các thuộc tính dành riêng cho broker hoặc bean cấu hình binder.

Tách profile giúp ứng dụng kết nối broker staging và production theo các môi trường khác nhau, nhưng cần kiểm soát nơi nạp cấu hình. Không nên kích hoạt profile production toàn cục nếu chỉ một binder cần cấu hình production.

Nếu cần nạp thêm class cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-special:
          type: kafka
          environment:
            spring:
              main:
                sources: com.example.kafka.SpecialKafkaBinderConfiguration
~~~

Đảm bảo class được nạp có các bean hoặc property cần thiết cho binder đó và không vô tình khai báo bean nghiệp vụ trùng với application context.

## 14. Quản lý thông tin xác thực và property source

Mỗi binder có thể kết nối tới một broker với tài khoản riêng. Đặt thông tin kết nối trong đúng binder environment giúp phân biệt credential theo broker:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafka-payments:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: payments-kafka.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: ${PAYMENTS_KAFKA_JAAS}
        kafka-analytics:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: analytics-kafka.internal:9093
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: SCRAM-SHA-512
                        sasl.jaas.config: ${ANALYTICS_KAFKA_JAAS}
~~~

Ví dụ dùng tên biến cấu hình để minh họa nguồn cấp giá trị nhạy cảm từ môi trường triển khai hoặc secret manager. Không commit username, password, SASL JAAS string, private key hay token thật vào repository.

Khi inheritEnvironment là false, hãy xác minh nguồn cấp placeholder và các property source có thể truy cập từ binder environment theo cách triển khai đang dùng. Không giả định binder cô lập sẽ đọc được mọi biến cấu hình chỉ được nạp vào application context.

Không dùng một property toàn cục như spring.kafka.bootstrap-servers để biểu diễn hai broker khác nhau. Mỗi binder cần địa chỉ và thông tin xác thực riêng trong environment của chính nó.

## 15. BinderCustomizer khi cần cấu hình bằng Java

Một số tùy chỉnh không thể biểu diễn đầy đủ bằng YAML. Spring Cloud Stream cung cấp BinderCustomizer để thay đổi binder instance sau khi được tạo và trước khi ứng dụng bắt đầu sử dụng binder.

Customizer nhận hai thông tin:

- Binder instance đang được cấu hình.
- Tên binder configuration tương ứng.

Ví dụ khung dùng tên để giới hạn phạm vi:

~~~java
import org.springframework.cloud.stream.binder.BinderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class BinderCustomizationConfiguration {

    @Bean
    BinderCustomizer binderCustomizer() {
        return (binder, binderName) -> {
            if ("kafka-payments".equals(binderName)) {
                // Gọi API tùy chỉnh phù hợp của Kafka binder tại đây.
            }
        };
    }
}
~~~

Nếu có hai Kafka binder, hãy kiểm tra cả type và name trước khi ép kiểu hoặc gọi API riêng của Kafka. Cùng một loại binder có thể có nhiều instance, nên chỉ kiểm tra instanceof có thể khiến tùy chỉnh áp dụng nhầm cho tất cả.

## 16. Lỗi thường gặp khi cấu hình environment

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Binding không tìm thấy binder | Tên trong binding.binder không khớp configuration name | So sánh tên binder được khai báo và tên được tham chiếu |
| Nhiều binder cùng loại nhưng kết nối cùng broker | Hai binder đang kế thừa cùng cấu hình toàn cục | Đặt địa chỉ broker riêng trong từng environment |
| Binder không nhận property cần thiết | inheritEnvironment: false nhưng thiếu property trong environment riêng | Bổ sung thuộc tính cần thiết vào đúng binder |
| Ứng dụng báo không xác định được default binder | Có nhiều ứng viên hoặc không có binder mặc định phù hợp | Đặt defaultBinder, defaultCandidate hoặc binder theo từng binding |
| Một binder configuration không được chọn | defaultCandidate: false nhưng binding không tham chiếu tên của nó | Gắn binder theo đúng configuration name |
| Bean tùy chỉnh không xuất hiện trong binder | Bean chỉ tồn tại ở application context riêng | Nạp cấu hình bằng environment.spring.main.sources hoặc dùng BinderCustomizer phù hợp |
| Profile không áp dụng cho binder | Profile được kích hoạt ở application environment thay vì binder environment | Đặt spring.profiles.active trong binder environment |
| Thông tin xác thực của hai broker bị dùng lẫn | Dùng property toàn cục cho nhiều broker cùng loại | Tách credential trong từng binder environment |
| Binding khởi tạo được nhưng publish sang broker khác thất bại | Output binder có credential, ACL hoặc topology riêng chưa đúng | Kiểm tra quyền và cấu hình broker của binder output |
| Một binding dùng nhầm binder mặc định | Không khai báo binder tường minh khi có nhiều ứng viên | Khai báo binder trực tiếp trên binding |

Khi chẩn đoán, kiểm tra lần lượt:

1. Binder implementation cần thiết có trên classpath không?
2. Binder type có đúng với metadata binder không?
3. Configuration name có trùng với giá trị binding.binder không?
4. environment có đúng prefix và đúng thuộc tính client không?
5. inheritEnvironment có phù hợp với cách nạp cấu hình không?
6. defaultCandidate và defaultBinder có tạo ra lựa chọn rõ ràng không?
7. Broker có thể truy cập và credential có đủ quyền không?

## 17. Kiểm thử nhiều binder

Nên kiểm tra cấu hình binder ở cả mức khởi tạo ứng dụng và mức message thực tế.

### 17.1. Kiểm thử cấu hình và context

Một integration test với Spring Boot có thể xác minh:

- ApplicationContext khởi động được khi có nhiều binder configuration.
- Binding được gắn đúng configuration name.
- Hai binder cùng type có địa chỉ broker khác nhau.
- inheritEnvironment và profile riêng được áp dụng như dự kiến.
- BinderCustomizer chỉ thay đổi instance được chọn.
- Binder không được tham chiếu không trở thành lựa chọn mặc định ngoài ý muốn.

### 17.2. Kiểm thử luồng message

Với hai broker thật hoặc môi trường test:

1. Publish một record vào input broker.
2. Xác minh Function nhận đúng record.
3. Xác minh output xuất hiện trên broker đích.
4. Xác minh output không xuất hiện nhầm trên broker còn lại.
5. Tạm dừng hoặc làm sai credential của output broker để kiểm tra retry và lỗi.
6. Gửi lại input để kiểm tra idempotency hoặc duplicate handling.
7. Kiểm tra log cho biết binding và broker nào gặp lỗi.

Topology test hoặc Test Binder có thể kiểm tra logic function, nhưng không xác minh đầy đủ việc hai binder kết nối hai broker thật. Hãy dùng integration test khi cần kiểm tra network, authentication, topic/exchange provisioning và quyền broker.

## 18. Nguyên tắc thiết kế environment nhiều binder

1. Dùng binder type để xác định implementation và configuration name để phân biệt từng instance.
2. Đặt địa chỉ broker, credential và thuộc tính client trong environment của binder tương ứng.
3. Chỉ bật inheritEnvironment: false khi đã xác định đầy đủ các property source mà binder cần.
4. Dùng defaultCandidate: false cho binder chỉ được chọn tường minh.
5. Gắn binder name trực tiếp vào binding khi có nhiều lựa chọn.
6. Dùng defaultBinder khi thực sự có một binder mặc định rõ ràng.
7. Giữ business bean trong application context; đặt cấu hình client trong binder context.
8. Dùng BinderCustomizer khi cần tùy chỉnh binder instance bằng Java.
9. Tách secrets theo broker và cấp từ secret manager hoặc môi trường triển khai.
10. Kiểm thử riêng từng broker và cả luồng message xuyên binder.
11. Thiết kế retry, idempotency và recovery vì hai binder không tự tạo transaction phân tán chung.
12. Đối chiếu thuộc tính và API với đúng phiên bản Spring Cloud Stream trong BOM của ứng dụng.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html): phát hiện binder, chọn binder mặc định và chọn binder theo binding.
- [Spring Cloud Stream - Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html): nhiều broker cùng loại, binder environment, profile và custom configuration sources.
- [Spring Cloud Stream - Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html): type, inheritEnvironment, environment và defaultCandidate.
- [Spring Cloud Stream - Customizing Binders in Multi Binder Applications](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-customizer.html): sử dụng BinderCustomizer và phân biệt binder bằng tên.
- [Spring Cloud Stream - Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): thuộc tính binder, destination, group và cấu hình mặc định cho binding.
