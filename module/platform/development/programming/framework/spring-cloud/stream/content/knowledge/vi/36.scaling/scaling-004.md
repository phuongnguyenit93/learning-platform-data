# Tùy biến binder trong ứng dụng nhiều binder

Spring Cloud Stream cho phép một ứng dụng dùng đồng thời nhiều middleware: nhận sự kiện từ Kafka, xử lý bằng `Function`, rồi phát sang RabbitMQ hoặc Pulsar; hoặc đọc từ hai Kafka cluster khác nhau mà không phải viết lại tầng kết nối broker. Một cấu hình như vậy được gọi là **ứng dụng nhiều binder (multi-binder application)**.

Khi chỉ có một binder, Spring Cloud Stream thường tự tìm binder trên classpath và nhiều bean tùy biến trong application context có thể được binder sử dụng trực tiếp. Khi có **nhiều binder**, đặc biệt là nhiều instance của cùng loại binder nhưng kết nối các cluster khác nhau, phải làm rõ:

- Binding nào gắn với binder nào?
- Binder đó dùng connection, credential và cấu hình broker nào?
- Bean tùy biến dùng cho tất cả binder hay chỉ một instance?
- Vì sao một bean ở application context chính không tự xuất hiện trong context riêng của binder?
- Việc chuyển event từ broker A sang broker B có bảo đảm giao nhận ra sao?
- Làm thế nào chứng minh rằng không có binding nào vô tình dùng sai broker?

Bài học tập trung vào ba cơ chế: **chọn binder theo binding**, **khai báo named binder với environment riêng**, và **dùng `BinderCustomizer` để can thiệp vào binder trước khi nó được sử dụng**. Ví dụ dùng mô hình hàm `Supplier`/`Function`/`Consumer` của Spring Cloud Stream, Kafka, RabbitMQ và Pulsar; đồng thời chỉ ra ngoại lệ của Kafka Streams binder. Kiến thức áp dụng khi mở rộng hệ thống thành nhiều luồng và nhiều broker, không chỉ khi tăng số replica.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Function bean | Logic nghiệp vụ biến đổi dữ liệu | `bridgeOrder` |
| Binding | Cổng vào/ra của function | `bridgeOrder-in-0`, `bridgeOrder-out-0` |
| Destination | Topic/exchange/topic URI trên broker | `orders.created`, `orders.enriched` |
| Binder type | Implementation kết nối một loại middleware | `kafka`, `rabbit`, `pulsar` |
| Named binder configuration | Một cấu hình binder được đặt tên | `ordersKafka`, `notificationsRabbit` |
| Binder instance | Binder thực tế mà framework tạo và sử dụng | KafkaMessageChannelBinder kết nối cluster A |
| BinderCustomizer | Callback Java tùy biến instance binder trước khi binding sử dụng | Gắn Kafka rebalance listener cho `ordersKafka` |

Tên **binder configuration** có thể khác **binder type**. Ví dụ `ordersKafka` và `auditKafka` cùng có `type: kafka` nhưng trỏ tới hai Kafka cluster khác nhau. Lúc đó tên configuration giúp phân biệt hai instance.

Một ứng dụng có thể gồm nhiều binding nhưng chỉ dùng một binder; ví dụ hai input Kafka và một output Kafka vẫn là một binder type và có thể là một binder instance. Ngược lại, chỉ một `Function` có hai binding vào/ra cũng đủ trở thành multi-binder nếu input dùng Kafka và output dùng RabbitMQ.

## 2. Sơ đồ: một function bắc cầu qua hai broker

~~~text
            Spring Boot / Spring Cloud Stream
  +----------------------------------------------------+
  |                                                    |
  | Kafka binder: ordersKafka                          |
  |   binding: bridgeOrder-in-0                         |
  |               |                                    |
  |               v                                    |
  |        Function<OrderCreated, OrderForwarded>      |
  |               |                                    |
  |               v                                    |
  | Rabbit binder: notificationsRabbit                  |
  |   binding: bridgeOrder-out-0                        |
  |                                                    |
  +-----------------^-----------------+----------------+
                    |                 |
                    |                 v
               Kafka cluster     RabbitMQ broker
               orders.created    orders.forwarded
~~~

Đường đi này chỉ là pipeline logic. Không có transaction phân tán tự động bảo đảm commit Kafka offset và publish RabbitMQ cùng lúc. Khi chọn topology multi-binder, cần thiết kế idempotency, retry và các tình huống broker đích lỗi, không chỉ khai báo hai binder rồi coi như xử lý exactly-once.

## 3. Thêm đúng dependency cho các binder sử dụng

Ví dụ Maven cho ứng dụng cần Kafka và RabbitMQ:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-rabbit</artifactId>
  </dependency>
</dependencies>
~~~

Nếu cần Pulsar binder:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-pulsar</artifactId>
</dependency>
~~~

Nếu topology xử lý KStream/KTable, dependency Kafka Streams binder được chọn riêng:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Dùng BOM Spring Cloud tương thích với Spring Boot của dự án để quản lý phiên bản. Không tự trộn phiên bản binder không tương thích chỉ vì các artifact đều có tên `spring-cloud-stream`.

Có nhiều implementation trên classpath nghĩa là ứng dụng phải chọn binder rõ ràng ở mỗi binding hoặc đặt `defaultBinder` thích hợp. Thêm dependency không tự quyết định input Kafka và output RabbitMQ theo đúng ý định nghiệp vụ.

## 4. Ví dụ Function chuyển sự kiện Kafka sang RabbitMQ

Một function thuần có thể giữ nguyên bất kể binder được chọn:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderBridgeFunctions {

    public record OrderCreated(
        String eventId,
        String orderId,
        long amount
    ) {}

    public record OrderForwarded(
        String eventId,
        String orderId,
        String status
    ) {}

    @Bean
    Function<OrderCreated, OrderForwarded> bridgeOrder() {
        return event -> new OrderForwarded(
            event.eventId(),
            event.orderId(),
            "RECEIVED"
        );
    }
}
~~~

Spring Cloud Stream tạo tên binding mặc định:

~~~text
bridgeOrder-in-0    -- input của Function
bridgeOrder-out-0   -- output của Function
~~~

Function ở trên không cần gọi KafkaConsumer, RabbitTemplate hay PulsarClient. Framework tạo input/output adapter và xử lý message conversion theo content type được cấu hình.

Cấu hình cơ bản khi chỉ có một Kafka binder và một Rabbit binder trên classpath:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: kafka
          content-type: application/json
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: rabbit
          content-type: application/json
~~~

`binder` là thuộc tính **của binding**, còn `destination` là resource trên broker. Lệnh `binder: rabbit` không biến `orders.forwarded` thành tên queue; với RabbitMQ binder, destination thường là exchange và group quyết định queue nhận. Cần tra mapping của binder cụ thể.

Cách dùng tên binder type trực tiếp phù hợp khi chỉ có một instance cho mỗi loại và các thuộc tính connection được cấu hình ở phạm vi ứng dụng. Với nhiều cluster hoặc cần cô lập cấu hình, chuyển sang named binder.

## 5. Global defaultBinder so với binder theo binding

Có hai cách chọn implementation:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
~~~

`defaultBinder` được dùng cho binding không đặt `binder` riêng. Cấu hình một binding có thể ghi đè:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-out-0:
          binder: rabbit
~~~

Quy tắc:

1. Binding có `binder` riêng dùng binder ấy.
2. Binding không có `binder` dùng default binder nếu được thiết lập hoặc xác định rõ.
3. Nếu có nhiều binder mà không chọn được duy nhất, ứng dụng có thể không tạo binding đúng yêu cầu và phải báo cấu hình mơ hồ.
4. Không để default binder vô tình quyết định đường đi của event quan trọng.

Trong production, với kiến trúc có input và output ở những middleware khác nhau, nên viết `binder` **tường minh cho mọi binding** để cấu hình dễ review, đặc biệt khi thêm dependency binder mới.

`default-binder` là cách viết kebab-case của `spring.cloud.stream.defaultBinder` trong cấu hình Spring Boot. Tài liệu có thể dùng camelCase; tùy bộ property binding, hãy dùng tên mà phiên bản đang triển khai hỗ trợ.

## 6. Đặt tên riêng cho các binder configuration

Để định nghĩa binder tường minh, dùng:

~~~text
spring.cloud.stream.binders.<configuration-name>
~~~

Một binder configuration có các field chính:

| Field | Tác dụng |
|---|---|
| `type` | Binder type được đăng ký qua metadata `META-INF/spring.binders` |
| `environment` | Các property dùng trong context riêng khi tạo binder |
| `inheritEnvironment` | Có kế thừa environment của application chính không; mặc định true |
| `defaultCandidate` | Có tham gia lựa chọn default binder không; mặc định true |

Ví dụ đơn giản:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          binder: ordersKafka
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: notificationsRabbit

      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders:9092
        notificationsRabbit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit-notifications
                port: 5672
                virtual-host: orders
~~~

Quan hệ tên:

~~~text
bridgeOrder-in-0.binder   = ordersKafka
binders.ordersKafka.type  = kafka

bridgeOrder-out-0.binder  = notificationsRabbit
binders.notificationsRabbit.type = rabbit
~~~

Khi khai báo `spring.cloud.stream.binders` tường minh, Spring Cloud Stream **tắt cơ chế cấu hình binder mặc định tự động**. Do đó tất cả binder mà ứng dụng sẽ sử dụng phải được khai báo trong `binders`. Không vừa khai báo riêng một binder rồi trông chờ binder thứ hai luôn tự xuất hiện qua classpath detection.

## 7. Environment riêng cho mỗi broker

Mỗi binder có thể dùng một `environment` chứa các property Spring Boot và Spring Cloud Stream liên quan.

Ví dụ đầy đủ hơn:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder

    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: ordersKafka
          content-type: application/json
        bridgeOrder-out-0:
          destination: orders.forwarded
          binder: notificationsRabbit
          content-type: application/json

      binders:
        ordersKafka:
          type: kafka
          inherit-environment: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_ORDERS_BROKERS:localhost:9092}
                      auto-create-topics: false

        notificationsRabbit:
          type: rabbit
          inherit-environment: false
          environment:
            spring:
              rabbitmq:
                host: ${RABBIT_HOST:localhost}
                port: ${RABBIT_PORT:5672}
                virtual-host: ${RABBIT_VHOST:orders}
                username: ${RABBIT_USER}
                password: ${RABBIT_PASSWORD}
~~~

Giải thích:

- `type` chọn implementation, không phải địa chỉ broker.
- `environment.spring.cloud.stream.kafka.binder.brokers` cấu hình broker cho Kafka binder được đặt tên.
- `environment.spring.rabbitmq.*` cấu hình kết nối RabbitMQ trong binder context.
- `inherit-environment: false` ngăn binder kế thừa cấu hình environment chung không mong muốn; lúc đó phải cung cấp đủ các thuộc tính cần thiết, kể cả kết nối và bảo mật.
- Biến môi trường chỉ minh họa cách externalize secret/host; production nên dùng secret manager và phân quyền phù hợp.

Một số bản triển khai dùng `inheritEnvironment` thay cho `inherit-environment`; cả hai đều biểu thị cùng BinderProperties. Trước khi rollout, kiểm tra property đã bind và endpoint cấu hình/metadata theo phiên bản dự án.

**Lưu ý bảo mật:** `inheritEnvironment=false` giúp phân tách property, nhưng không phải sandbox bảo mật tuyệt đối. Các binder vẫn chạy trong cùng JVM/process, dùng tài nguyên CPU/RAM và các thành phần do ứng dụng quản lý. Nó không thay cho IAM và network isolation.

## 8. Hai Kafka cluster với cùng binder type

Trường hợp phổ biến: một ứng dụng đọc từ cluster production A nhưng ghi sang cluster analytics B.

~~~text
Kafka A                              Kafka B
orders.created --- input Function --- orders.enriched
    |                                      |
    +-- ordersKafka                        +-- analyticsKafka
        type=kafka                             type=kafka
        brokers=kafka-a                        brokers=kafka-b
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder

    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: order-enricher-v1
          binder: ordersKafka
        enrichOrder-out-0:
          destination: orders.enriched
          binder: analyticsKafka

      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-a:9092

        analyticsKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-b:9092
~~~

Hai named binder khác nhau dù cả hai `type: kafka`. Đây là lý do `BinderCustomizer` nhận cả `binder` và `binderName`: tùy biến dựa vào class `KafkaMessageChannelBinder` thôi chưa đủ để phân biệt A và B.

Chuyển record qua hai Kafka cluster không tự tạo transaction nguyên tử xuyên cluster. Khi đầu ra đã gửi nhưng offset ở nguồn chưa commit, record có thể được nhận lại. Thiết kế downstream idempotent hoặc phương án bridge bảo đảm giao nhận thích hợp.

## 9. defaultCandidate: binder có được xét làm mặc định không?

Với cấu hình tùy chọn:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        auditKafka:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-audit:9092
~~~

`default-candidate: false` có nghĩa binder này **chỉ được dùng khi được tham chiếu tường minh**, không tham gia quá trình chọn default binder. Nó hữu ích khi framework thêm một binder phụ để quan sát hoặc dùng động nhưng không muốn thay đổi default binder của ứng dụng.

Điều này không làm binder bị vô hiệu hóa: binding có `binder: auditKafka` vẫn có thể sử dụng. Nếu ứng dụng dùng toàn bộ binder ở chế độ non-default, mọi binding cần chọn tên rõ ràng.

Không dùng `defaultCandidate=false` để cô lập credential hoặc bảo đảm broker không được kết nối. Nó chỉ tác động lựa chọn binder.

## 10. Bảng cấu hình ba tầng

Thứ tự suy nghĩ về config:

| Tầng | Prefix | Phạm vi |
|---|---|---|
| Function/Binding | `spring.cloud.stream.bindings.<name>` | Đặt destination/group/binder cho một binding |
| Binder instance | `spring.cloud.stream.binders.<name>` | Chọn type, environment, isolation và defaultCandidate |
| Binder-specific | Trong binder environment hoặc `spring.cloud.stream.<type>.bindings.<name>` | Cấu hình Kafka/Rabbit/Pulsar thuộc tính mở rộng |

Ví dụ với Kafka:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-bridge-v1
          binder: ordersKafka
          consumer:
            concurrency: 2

      kafka:
        bindings:
          bridgeOrder-in-0:
            consumer:
              ack-mode: RECORD
~~~

Ở đây `concurrency` là generic binding property, còn `ack-mode` là Kafka extended consumer property. Thuộc tính `ack-mode` không có cùng ý nghĩa với RabbitMQ hoặc Pulsar và không được khai báo tại `spring.cloud.stream.bindings.*.consumer` như generic field.

Với ứng dụng có nhiều instance của **cùng binder type**, đừng tùy ý giả định một extended-property được đặt ở application context chính luôn độc lập theo cluster. Kiểm tra precedence và khả năng áp dụng của binder version. Thuộc tính kết nối và cấu hình chung khác nhau giữa các cluster nên được đặt rõ ràng vào `binders.<name>.environment`; tùy biến đối tượng Binder cần lọc bằng `binderName`.

## 11. Vì sao bean tùy biến có thể không đến được binder?

Trong single-binder application, binder thường có thể thấy các bean tùy biến ở context chính. Nhưng ở multi-binder application, Spring Cloud Stream có thể tạo mỗi binder trong **application context riêng**. Một bean như Kafka rebalance listener, Rabbit listener-container customizer hay cấu hình riêng không nhất thiết được tự tìm thấy bên trong từng binder context.

~~~text
Main application context
  |
  +-- @Bean Function
  +-- @Bean BinderCustomizer
  +-- @Bean MyKafkaRebalanceListener
  |
  +--> Binder context: ordersKafka
  |       +-- KafkaMessageChannelBinder
  |
  +--> Binder context: analyticsKafka
  |       +-- KafkaMessageChannelBinder
  |
  +--> Binder context: notificationsRabbit
          +-- RabbitMessageChannelBinder
~~~

`BinderCustomizer` giải quyết việc này bằng callback do Spring Cloud Stream gọi **trước khi binder được sử dụng**. Callback nhận instance Binder và tên configuration, cho phép kiểm tra type/name rồi đăng ký tùy biến tương ứng.

Đừng nhầm với `@Configuration` thông thường: đặt bean ở main context không tự động đồng nghĩa tất cả binder context riêng biệt đều dùng bean đó.

## 12. Dùng BinderCustomizer cho nhiều binder

Spring Cloud Stream cung cấp interface `org.springframework.cloud.stream.binder.BinderCustomizer`:

~~~java
void customize(
    Binder<?, ? extends ConsumerProperties, ? extends ProducerProperties> binder,
    String binderName
);
~~~

Khi đăng ký bean, có thể dùng lambda:

~~~java
import org.springframework.cloud.stream.binder.BinderCustomizer;
import org.springframework.cloud.stream.binder.kafka.KafkaMessageChannelBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiBinderCustomization {

    @Bean
    BinderCustomizer binderCustomizer(
            OrdersRebalanceListener ordersListener) {

        return (binder, binderName) -> {

            if ("ordersKafka".equals(binderName)
                    && binder instanceof KafkaMessageChannelBinder kafka) {
                kafka.setRebalanceListener(ordersListener);
            }

            // analyticsKafka cũng là KafkaMessageChannelBinder
            // nhưng KHÔNG nhận listener chỉ dành cho ordersKafka.
        };
    }
}
~~~

`OrdersRebalanceListener` ở đây là một class do ứng dụng định nghĩa và triển khai interface `KafkaBindingRebalanceListener`. Phần tiếp theo minh họa implementation.

Quy tắc:

- **Kiểm tra type** trước khi ép kiểu hoặc gọi API cụ thể.
- **Kiểm tra name** nếu có nhiều instance cùng type.
- Chỉ gọi API cần thiết, không thay đổi binder khác ngoài phạm vi.
- Callback được gọi lúc cấu hình binder; không dùng nó làm nơi xử lý message nghiệp vụ.
- Tránh thao tác chậm, gọi HTTP tùy tiện hoặc lấy secret động trong callback khởi động.
- Không giả định có thể chạy lại `BinderCustomizer` để đổi connection khi binder đang xử lý; muốn đổi config runtime thường cần restart/rebind phù hợp.

## 13. Ví dụ KafkaBindingRebalanceListener được chọn theo binderName

Ví dụ listener chỉ ghi nhận partition assignment, không tự ý seek offset:

~~~java
import java.util.Collection;

import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.clients.consumer.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.stream.binder.kafka.KafkaBindingRebalanceListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersRebalanceListener
        implements KafkaBindingRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersRebalanceListener.class);

    @Override
    public void onPartitionsAssigned(
            String bindingName,
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions,
            boolean initial) {

        log.info(
            "binding={} initial={} partitions={}",
            bindingName,
            initial,
            partitions
        );
    }
}
~~~

Kết hợp class này với `BinderCustomizer` phần trước giúp `ordersKafka` nhận listener chỉ định, trong khi `analyticsKafka` không bị áp dụng cùng logic.

**Cảnh báo về seek/reset:** Tài liệu Kafka binder không cho dùng `resetOffsets=true` đồng thời với rebalance listener. Nếu listener thực hiện seek để replay, phải kiểm soát số lần seek và group/partition, tránh đọc lại lịch sử mỗi lần rebalance.

Nếu một bean listener đã được binder tự tìm thấy qua context inheritance, không gắn listener hai lần theo hai cơ chế mà không xác minh hành vi. Khi multi-binder, nên có một điểm đăng ký rõ ràng và kiểm tra bằng integration test.

## 14. BinderCustomizer không phải ListenerContainerCustomizer

Hai cơ chế có phạm vi khác nhau:

| Cơ chế | Đối tượng tác động | Dùng khi |
|---|---|---|
| `BinderCustomizer` | Binder instance được chọn theo type/name | Cần truyền cấu hình Java tới binder trong multi-binder context |
| `ListenerContainerCustomizer` | Message listener container cụ thể | Cần chỉnh container cho destination/group |
| Kafka consumer/producer config customizer | Kafka client config map | Cần override property client theo binding/topic |
| `spring.cloud.stream.bindings.*` | Binding properties | Đổi destination/group/concurrency/content type |
| `binders.<name>.environment` | Binder environment/context | Phân tách broker, host và credential |

Nếu có property khai báo sẵn, **ưu tiên YAML**. Nếu cần tùy biến listener container theo destination/group, dùng extension point của binder tương ứng. Trong multi-binder, bean ấy có thể cần được đưa vào binder context hoặc gắn theo API mà `BinderCustomizer` hỗ trợ. Không cố dùng `BinderCustomizer` như một router cho mọi event.

Với ứng dụng Kafka + RabbitMQ, không ép `RabbitMessageChannelBinder` thành `KafkaMessageChannelBinder`. Những API như rebalance listener chỉ có ý nghĩa với Kafka consumer.

## 15. Khi cần cấu hình class riêng trong binder environment

Ngoài callback `BinderCustomizer`, mỗi binder environment có thể khai báo nguồn cấu hình riêng bằng `spring.main.sources`:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              main:
                sources: com.example.stream.config.OrdersBinderOnlyConfig
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: kafka-orders:9092
~~~

Đây là một extension point để thêm bean/configuration vào binder context theo tên. Nhưng phải rất cẩn thận:

- Class `OrdersBinderOnlyConfig` phải tồn tại trong classpath.
- Tránh để class được component scan tự động của main application context rồi đăng ký trùng.
- Không tạo bean chung tên với cấu hình framework mà không có chủ đích.
- Kiểm tra vòng đời, phạm vi context và phụ thuộc bean.
- Với nhu cầu đơn giản, một `BinderCustomizer` ở main context thường dễ hiểu hơn.

`spring.profiles.active` có thể được đặt trong environment binder để kích hoạt profile riêng. Tuy nhiên, nếu các profile thay đổi connection/auth khác nhau, cần thử khởi động thực tế để tránh cấu hình của binder này rò sang binder khác.

## 16. StreamBridge trong ứng dụng nhiều binder

`StreamBridge` dùng khi ứng dụng cần phát message từ HTTP handler, scheduler hoặc callback không trực tiếp là output của function.

Ví dụ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class AuditPublisher {

    private final StreamBridge streamBridge;

    public AuditPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String json) {
        return streamBridge.send(
            "audit-out-0",
            "auditKafka",
            json
        );
    }
}
~~~

Overload có tham số thứ hai `binderName` cho phép chọn binder khi tạo **dynamic binding**. Đây là điểm khác với `send(bindingName, data)`, vốn cần có default binder hoặc binding đã được cấu hình phù hợp.

Tuy nhiên, tài liệu Spring Cloud Stream lưu ý: **nếu output binding đã tồn tại hoặc đã được tạo qua `spring.cloud.stream.output-bindings`, tham số `binderName` của lần send mới không thay đổi binder của binding ấy**. Do đó, với output có tên cố định, cách rõ ràng nhất là cấu hình binder và destination ngay trong YAML:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        audit-out-0:
          destination: audit.events
          binder: auditKafka
          content-type: application/json
~~~

Đừng gửi `audit-out-0` sang broker A ở một request và mong cùng binding ấy tự đổi sang broker B ở request sau. Muốn hai đích, tạo hai binding/destination riêng, có thể dùng hai lần `StreamBridge.send` với tên binding khác nhau.

## 17. Ví dụ: Supplier và Consumer dùng binder khác nhau

Không chỉ Function mới có nhiều binder; một ứng dụng có thể có các function bean độc lập:

~~~java
import java.time.Instant;
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OperationsFunctions {

    @Bean
    Supplier<String> heartbeat() {
        return () -> "alive-" + Instant.now();
    }

    @Bean
    Consumer<String> auditEvent() {
        return message -> {
            // Ghi audit log hoặc gọi dịch vụ nghiệp vụ.
        };
    }
}
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat;auditEvent

    stream:
      bindings:
        heartbeat-out-0:
          destination: system.heartbeat
          binder: auditKafka
        auditEvent-in-0:
          destination: persistent://acme/audit/events
          group: audit-reader-v1
          binder: auditPulsar
~~~

Ví dụ trên giả định `auditKafka` và `auditPulsar` đã được khai báo trong `binders` với đúng type và broker environment. `heartbeat` là pollable Supplier; lịch phát do poller/scheduling của Spring Cloud Stream quyết định, không tự suy ra từ số instance.

Khi function độc lập dùng nhiều binder, chúng không tự nối với nhau. Một Consumer không có output binding và một Supplier không có input binding. Việc đặt chúng cùng process không tạo ra transaction hoặc retry chung.

## 18. Pulsar binder: property ở cấp binder và binding

Pulsar binder dùng Spring for Apache Pulsar, nên có cấu hình Spring Boot chung như:

~~~text
spring.pulsar.client.service-url
spring.pulsar.consumer.*
spring.pulsar.producer.*
~~~

Ngoài ra Pulsar binder cung cấp:

~~~text
spring.cloud.stream.pulsar.binder.consumer.*
spring.cloud.stream.pulsar.binder.producer.*

spring.cloud.stream.pulsar.bindings.<input>.consumer.*
spring.cloud.stream.pulsar.bindings.<output>.producer.*
~~~

Tài liệu Pulsar binder mô tả thứ tự ưu tiên:

~~~text
Extended binding properties
    > Pulsar binder properties
    > Spring Boot Pulsar properties
~~~

Ví dụ chỉ định subscription type cho input cụ thể:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvent-in-0:
          destination: persistent://acme/audit/events
          group: audit-reader-v1
          binder: auditPulsar

      pulsar:
        bindings:
          auditEvent-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

Khi ứng dụng có nhiều function Pulsar, khai báo extended binding để tránh áp dụng cùng subscription setting cho mọi consumer ngoài ý muốn.

Nếu có **nhiều Pulsar cluster** và named binders, đưa service URL và thông tin kết nối thích hợp vào environment của từng named binder; không dùng một URL toàn cục và mong cả hai cluster được tách.

## 19. Kafka Streams binder là một trường hợp riêng

Regular Kafka binder dùng `KafkaMessageChannelBinder` cho message channel, còn Kafka Streams binder dành cho `KStream`, `KTable`, `GlobalKTable` và topology có state.

Do đó, khi multi-binder chứa cả Kafka Streams và regular Kafka:

- Không ép Kafka Streams binder thành regular Kafka binder.
- Không áp dụng rebalance listener của regular Kafka binder cho Kafka Streams topology.
- Tách application ID và cluster config cho từng topology.
- Đọc đúng loại binder được đăng ký trong `META-INF/spring.binders`, nhất là khi có `kstream`, `ktable`, `globalktable` trong kịch bản nhiều binder phức tạp.
- State store, internal changelog/repartition topics và lifecycle của Kafka Streams có ràng buộc riêng.

Ví dụ minh họa một Kafka Streams function:

~~~java
@Bean
Function<KStream<String, String>, KStream<String, String>> normalize() {
    return input -> input.mapValues(String::trim);
}
~~~

Khi các binder type Kafka Streams cùng coexist với regular Kafka binder, cần chọn `binder` cho đúng từng binding theo mapping do binder family của phiên bản sử dụng công bố. Không lấy ví dụ `type: kafka` của regular binder rồi áp dụng cho KStream input.

Đổi broker hoặc application ID của Kafka Streams có thể tạo namespace state/changelog và consumer group mới, gây replay input. Không xem đó chỉ là thao tác thay địa chỉ broker.

## 20. Dùng nhiều binder không đồng nghĩa có distributed transaction

Xét các mốc:

~~~text
1. Consumer Kafka nhận OrderCreated.
2. Function tạo OrderForwarded.
3. Rabbit publisher gửi message thành công.
4. Kafka consumer commit offset.
~~~

Nếu JVM crash **sau bước 3 nhưng trước bước 4**, Kafka có thể giao lại OrderCreated sau restart và Rabbit nhận OrderForwarded trùng. Nếu ứng dụng ack Kafka quá sớm trước khi Rabbit publish được xác nhận, có nguy cơ mất event đầu ra.

Một số bảo đảm cần phân biệt:

| Tính chất | Ý nghĩa |
|---|---|
| Kafka consumer group offset | Vị trí tiếp tục đọc của nhóm consumer |
| Rabbit publisher confirm | Xác nhận broker nhận publish theo mức bảo đảm được cấu hình |
| Pulsar producer send acknowledgment | Xác nhận publish theo client/broker |
| Function invocation | Logic Java được chạy; không chứng minh tất cả side effect đã commit |
| Cross-broker atomicity | Không được Spring Cloud Stream tự cung cấp chỉ từ hai `binder` |

Không hứa exactly-once end-to-end xuyên Kafka → RabbitMQ → PostgreSQL chỉ bằng cấu hình `binder` hoặc `transactional.id` của một Kafka client.

Các lựa chọn:

- **Idempotent consumer:** nhận message trùng nhưng side effect chỉ áp dụng một lần theo event ID.
- **Transactional outbox:** commit state cùng bản ghi outbox trong database transaction, sau đó publisher riêng đẩy message đi.
- **Inbox/deduplication:** lưu message ID đã xử lý theo consumer group/domain.
- **Saga/compensation:** xử lý chuỗi bước có trạng thái và cơ chế bù.
- **Retry + DLQ:** phục hồi lỗi tạm thời, cách ly record độc khi hết retry.

Chọn một strategy và kiểm tra bằng failure injection; đây là một phần thiết kế multi-binder chứ không phải tối ưu phụ.

## 21. Conversion và schema giữa hai middleware

Spring Cloud Stream cung cấp content-type conversion, nhưng các broker hỗ trợ header, key và serializer khác nhau.

Ví dụ với Function từ Kafka sang RabbitMQ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          content-type: application/json
          binder: ordersKafka
        bridgeOrder-out-0:
          content-type: application/json
          binder: notificationsRabbit
~~~

Đây chỉ là mức contract chung. Cần xác minh:

1. Input Kafka record serializer/deserializer, key và header mapping.
2. Function nhận DTO hoặc `Message<DTO>` đúng kiểu.
3. Output Rabbit serializer/header mapping tương thích consumer downstream.
4. Trường `eventId`, `schemaVersion`, `correlationId` có được giữ nguyên hoặc tạo mới hợp lệ không.
5. Tombstone, null payload, schema evolution, timestamp và ordering có được xử lý đúng không.

Nếu dùng `useNativeDecoding`/`useNativeEncoding`, binder có thể không thực hiện conversion giống kịch bản content-type thông thường. Phải cung cấp serializer/serde thích hợp tại binder và kiểm thử payload thật ở broker đích.

Không suy luận rằng việc cùng dùng JSON sẽ giữ nguyên mọi header Kafka sang RabbitMQ hoặc Pulsar. Header mapper và cách broker mã hóa metadata có thể khác nhau.

## 22. Consumer group và subscription khi đổi binder

Ý nghĩa của `group` phụ thuộc binder:

| Binder | `group` thường ánh xạ đến |
|---|---|
| Kafka | Kafka consumer group ID |
| RabbitMQ | Queue do binder tạo/bind theo destination + group |
| Pulsar | Subscription identity |
| Kafka Streams | application.id quản lý group và state, có quy tắc riêng |

Ví dụ `group: order-bridge-v1` ở Kafka không phải shared group với Rabbit hay Pulsar. Hai middleware có cơ chế checkpoint/backlog riêng.

Nếu chuyển một input binding từ Kafka sang RabbitMQ nhưng giữ cùng group string, không có cơ chế tự dịch offset Kafka thành Rabbit queue ack state. Chuyển migration cần:

- Xác định cutover point.
- Quyết định dual-write, replay hoặc backfill.
- Kiểm tra duplicate/idempotency.
- Cô lập output tránh phát đôi.
- Đo backlog và thông tin xác nhận ở cả hai broker.
- Có kế hoạch rollback/cleanup resource cũ.

## 23. Bảo mật và cấp quyền riêng cho mỗi binder

Một process chứa nhiều binder có nhiều connection và nhiều credential. Nếu có thể, tách service identity theo broker:

~~~text
ordersKafka         -> Kafka principal: orders-bridge-consumer
notificationsRabbit -> Rabbit user:    orders-bridge-publisher
auditPulsar         -> Pulsar role:    audit-publisher
~~~

Kafka identity chỉ có Read trên input topic và group. Rabbit user chỉ có Write trên output exchange nếu không provision; Pulsar publisher chỉ có Produce vào topic/namespace cần thiết.

Đừng đặt một superuser credential cho mọi binder context. Đặc biệt, việc auto-provision topic/queue/exchange có thể yêu cầu quyền Create/Configure. Production thường nên provision resource bằng pipeline quản trị rồi chạy workload với quyền runtime tối thiểu.

Nếu binder context có `inheritEnvironment=true`, đánh giá nguy cơ property kết nối/credential toàn cục bị áp dụng ngoài ý muốn. Với broker khác nhau, ưu tiên khai báo secret rõ theo named binder và kiểm tra trong integration test.

Không mở actuator binding/config endpoints công khai: chúng có thể lộ host, thông tin kết nối hoặc tham số security nếu không sanitize.

## 24. Scale từng binding khác với scale cả application

Một Spring Boot process có thể đồng thời chứa:

- Kafka consumer input.
- Rabbit producer output.
- Pulsar consumer input thứ hai.
- Kafka Streams topology riêng.

Khi tăng replica của process, **mọi binding đều được nhân bản**. Có thể làm tăng số Kafka consumer, Rabbit producer connection và Pulsar subscription consumer cùng lúc, kể cả khi chỉ một nhánh đang cần thêm năng lực.

Ví dụ Kafka input có 6 partition, Rabbit output chịu mức tải cố định và Pulsar Key_Shared yêu cầu ordering theo key. Tăng pod từ 2 lên 8 không tự tăng throughput ở từng nhánh; cũng có thể tăng client connection hoặc làm các consumer Kafka dư partition.

Trước khi scale multi-binder application:

1. Đo lag/backlog theo từng binding/broker.
2. Xác định bottleneck ở function nào, partition nào, downstream nào.
3. Kiểm tra concurrency/instanceCount và số partition, queue, subscription type.
4. Ước lượng số connection và memory nếu toàn bộ process được scale.
5. Cân nhắc tách thành hai application khi các nhánh có SLO hoặc nhịp scale khác nhau.
6. Test failover và rebalance khi tăng/giảm replica.

Tùy biến binder giúp tổ chức cấu hình, nhưng không thay thế thiết kế scale độc lập.

## 25. Quan sát trạng thái binding và broker

Trong production, nên bật Actuator và Micrometer, đồng thời thu metrics riêng từng broker.

Ví dụ expose binding endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings,metrics
~~~

Yêu cầu có dependency Spring Boot Actuator và Web/WebFlux. Endpoint:

~~~text
GET /actuator/bindings
GET /actuator/bindings/{bindingName}
~~~

Có thể kiểm tra:

- `bridgeOrder-in-0` đã binding tới `ordersKafka` chưa?
- `bridgeOrder-out-0` đã binding tới `notificationsRabbit` chưa?
- Các input có running không?
- Kafka lag theo group/partition, rebalance và retry thế nào?
- Rabbit publish confirm, queue backlog, nack, connection/channel ra sao?
- Pulsar subscription backlog, unacked và redelivery ra sao?

Đừng chỉ nhìn app health `UP`: một broker có thể lỗi trong khi function khác vẫn xử lý. Health indicator của mỗi binder và broker metrics cần được đối chiếu theo đường đi nghiệp vụ. Binding endpoint có thể không thể hiện mọi chi tiết credential/type; kiểm chứng bằng broker-side tools là bằng chứng quan trọng hơn.

## 26. Kiểm thử bằng test binder và broker thật

Dùng `spring-cloud-stream-test-binder` để kiểm thử function transformation và wiring cơ bản trong JVM. Đây là lựa chọn tốt cho logic `OrderCreated -> OrderForwarded`, nhưng **không chứng minh** message thực sự đi từ Kafka cluster A đến Rabbit broker B.

Phân tầng test:

| Cấp | Mục tiêu |
|---|---|
| Unit test function | DTO mapping, validation, schema rules |
| Test binder | Input/output function binding trong JVM |
| Integration test 2 broker | Kafka input thật, Rabbit output thật, credentials và routing |
| Integration test 2 Kafka cluster | Binder `ordersKafka` vs `analyticsKafka` không bị nhầm |
| Failure injection | Kafka down, Rabbit down, publish succeed/offset commit fail |
| Scale test | Replicas, group assignment và backlog của từng broker |

Một integration test cho Kafka → Rabbit:

1. Khởi động một Kafka Testcontainer và một RabbitMQ Testcontainer.
2. Cấp hostname/port động cho `ordersKafka` và `notificationsRabbit` (ví dụ qua Spring test properties).
3. Cấp chính xác resource ACL/vhost cần thiết; tạo topic/exchange/queue trước nếu muốn kiểm tra no-provisioning.
4. Khởi động ứng dụng với đúng function và named binders.
5. Publish `OrderCreated(eventId=evt-101)` vào Kafka `orders.created`.
6. Consume từ Rabbit queue được bind với `orders.forwarded`.
7. Kiểm tra `eventId`, `orderId`, `status`, content type và header.
8. Khởi động lại consumer; xác nhận group/offset và không phát thêm event ngoài semantics mong muốn.
9. Chặn Rabbit tạm thời, kiểm tra retry/failure và khôi phục.
10. Xác minh message sai broker **không** tạo output vào resource khác.

Khi cấu hình explicit binder, test class phải cấp đủ định nghĩa named binder. Không dựa vào test binder in-memory để chứng minh `BinderCustomizer` đã gắn đúng Kafka listener cho broker A.

## 27. Kiểm thử BinderCustomizer riêng biệt

Vì BinderCustomizer nhận binder instance và binder name, có thể unit test logic lọc tên/type mà không cần broker thật.

Các kịch bản:

| Input cho callback | Kỳ vọng |
|---|---|
| `ordersKafka` + KafkaMessageChannelBinder | Gắn OrdersRebalanceListener |
| `analyticsKafka` + KafkaMessageChannelBinder | Không gắn listener dành cho orders |
| `notificationsRabbit` + Rabbit binder | Không ép kiểu Kafka và không gắn listener |
| Binder type mới được thêm | Không bị tác động ngoài ý muốn |

Ngoài unit test, integration test nên kiểm tra listener thực sự được gọi khi Kafka group nhận partition. Nếu chỉ assert `@Bean BinderCustomizer` tồn tại, chưa chứng minh callback được invoked với instance/named configuration mong muốn.

Giữ callback đơn giản, deterministic và không side effect lên network. Khi tên binder thay đổi trong YAML, test nên thất bại rõ thay vì âm thầm bỏ qua customization quan trọng.

## 28. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/khắc phục |
|---|---|---|
| Input đọc sai cluster | Thiếu `bindings.<input>.binder` | Ghi binder tường minh, test trên cả hai broker |
| Output đi sai broker | Default binder được chọn ngoài ý muốn | Kiểm tra `defaultBinder`, binding config |
| Binder configuration không được tạo | `type` sai hoặc dependency thiếu | Kiểm tra `META-INF/spring.binders` và classpath |
| Thêm binder thứ hai thì binder đầu biến mất | Explicit `binders` tắt cấu hình mặc định | Liệt kê đủ mọi binder sử dụng |
| Hai Kafka cluster cùng config | Chỉ dùng một `spring.kafka.*` chung | Dùng named binder và environment riêng |
| Customizer không chạy | Bean không được đăng ký hoặc binder không được dùng | Kiểm tra tạo binding và callback log |
| Listener áp dụng nhầm cả hai Kafka | Chỉ kiểm tra instance type | Lọc thêm `binderName` |
| Listener không thấy bean | Binder ở context riêng | Gắn qua BinderCustomizer hoặc binder-specific sources |
| StreamBridge vẫn gửi broker cũ | Binding đã tạo với binder trước đó | Dùng binding name khác, cấu hình binder tường minh |
| Kafka consumer xử lý trùng sau crash | Cross-broker publish/offset không nguyên tử | Event ID, inbox/outbox, idempotency |
| Pulsar binding thiếu đúng subscription | Group/subscription name/type sai | Kiểm tra broker subscription và config |
| RabbitMQ publish vào exchange nhưng queue không nhận | Routing/exchange-binding sai | Kiểm tra binding, routing key, permissions |
| Kafka Streams state bị replay | Đổi application ID/cluster ngoài ý muốn | Lập kế hoạch state/offset migration |
| Scale cả pod gây tốn connection | Mọi binder cùng scale | Cân nhắc tách service theo nhánh |
| Test in-memory PASS nhưng production FAIL | Không test broker thật | Integration test với đúng broker/credential |

## 29. Checklist trước khi rollout

| Chủ đề | Câu hỏi cần xác minh |
|---|---|
| Dependency | Đúng binder artifact và Spring Cloud BOM chưa? |
| Function | `spring.cloud.function.definition` có đúng bean không? |
| Binding | Mọi `<function>-in/out-*` đều có destination/group/binder đúng chưa? |
| Explicit binders | Có khai báo đầy đủ named binder khi bật `binders` không? |
| Binder type | Tên `type` tương ứng implementation trên classpath không? |
| Environment | Broker host/port và security có tách theo tên không? |
| Inheritance | `inheritEnvironment` có đúng ý đồ không? |
| Default | `defaultBinder`/`defaultCandidate` có nguy cơ chọn nhầm không? |
| Customizer | Lọc theo type/name, chạy trước binder use và có integration test không? |
| Schema | Content type/Serde/header có tương thích giữa hai broker không? |
| Delivery | Có phương án xử lý crash giữa publish và offset commit không? |
| Idempotency | Có event ID, inbox/outbox hoặc deduplication không? |
| Security | Runtime identities có least privilege không? |
| Ops | Có metrics/health/backlog riêng theo broker không? |
| Scaling | Tăng replica có khiến mọi binding cùng scale ngoài ý muốn không? |
| Testing | Đã chạy test broker thật và failure injection chưa? |
| Rollback | Có thể trả binding về broker cũ mà không mất/trùng dữ liệu không? |

## 30. Bài thực hành: Kafka → RabbitMQ và hai Kafka cluster

### Phần A — Function bridge

1. Tạo `bridgeOrder` nhận `OrderCreated`, trả `OrderForwarded`.
2. Thêm Kafka và RabbitMQ binder dependency.
3. Định nghĩa `ordersKafka` (`type: kafka`) và `notificationsRabbit` (`type: rabbit`).
4. Chọn `bridgeOrder-in-0.binder=ordersKafka`.
5. Chọn `bridgeOrder-out-0.binder=notificationsRabbit`.
6. Cấu hình destination, group, content type và connection môi trường.
7. Gửi message thật vào Kafka, xác nhận Rabbit nhận cùng `eventId`.
8. Giả lập Rabbit down và mô tả tình huống Kafka redelivery.

### Phần B — Hai Kafka cluster

1. Thêm `analyticsKafka` cũng có `type: kafka` nhưng `brokers` khác.
2. Chuyển output của một function độc lập sang `analyticsKafka`.
3. Viết `BinderCustomizer` chỉ gắn rebalance listener vào `ordersKafka`.
4. Kiểm thử listener không gắn vào `analyticsKafka`.
5. Kiểm tra broker đích thật bằng công cụ Kafka.
6. Trình bày vì sao không được coi việc ghi chéo cluster là transaction nguyên tử.

### Phần C — Vận hành

1. Gắn Actuator/Micrometer.
2. Quan sát health, binding state và lag/backlog của từng broker.
3. Chạy nhiều replica; ghi nhận số consumer/connection tăng ở từng binder.
4. Thử cắt một broker khỏi mạng rồi khôi phục.
5. Đối soát input, output, retry, DLQ và duplicate.
6. Hoàn thiện production checklist và rollback plan.

**Tiêu chí hoàn thành:** giải thích được binder type khác binder configuration name; ánh xạ từng binding đúng broker; tách environment/credential; nêu đúng vai trò của BinderCustomizer trong multi-binder context; kiểm tra StreamBridge binding động; và thiết kế kiểm thử cùng cơ chế giao nhận cho bridge xuyên broker.

## 31. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html) — chọn binder theo binding và defaultBinder.
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html) — named binders, `environment` và nhiều cluster cùng type.
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html) — `type`, `inheritEnvironment`, `environment`, `defaultCandidate`.
- [Spring Cloud Stream — Customizing Binders in Multi Binder Applications](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-customizer.html) — BinderCustomizer và lọc binder type/name.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group, binder và extended properties.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function model và StreamBridge binderName.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — Kafka binder properties, consumer/producer extensions.
- [Spring Cloud Stream — KafkaBindingRebalanceListener](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/rebalance_listener.html) — rebalance callback và offset seek.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — binding-level producer/consumer properties và Spring Pulsar integration.
- [Spring Cloud Stream — Multi Binders with Kafka Streams](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html) — trường hợp KStream/KTable và regular Kafka cùng ứng dụng.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html) — Actuator binding state và lifecycle.

