# Khai báo tên cấu hình binder và gắn binder cho từng binding

Spring Cloud Stream dùng Binder để kết nối binding của ứng dụng với hệ thống messaging như Apache Kafka, RabbitMQ hoặc Apache Pulsar. Một ứng dụng có thể cần đọc từ Kafka và ghi sang RabbitMQ, gửi sự kiện đến hai Kafka cluster khác nhau, hoặc kết nối hai RabbitMQ broker độc lập. Khi đó, cần khai báo từng cấu hình binder có tên riêng và gắn đúng binder vào từng binding.

Có ba khái niệm tên cần phân biệt:

- **Binder type**: loại triển khai binder, ví dụ `kafka`, `rabbit` hoặc `pulsar`. Type được đăng ký bởi thư viện binder trên classpath.
- **Binder configuration name**: tên một cấu hình kết nối cụ thể do ứng dụng đặt, ví dụ `ordersKafka`, `auditKafka` hoặc `rabbitCommands`.
- **Binding name**: tên điểm vào/ra do Spring Cloud Stream tạo từ function, ví dụ `routeOrder-in-0` và `routeOrder-out-0`.

Một binder type có thể có nhiều cấu hình kết nối khác nhau. Ví dụ `ordersKafka` và `auditKafka` đều có `type: kafka`, nhưng mỗi cấu hình trỏ đến một Kafka cluster khác nhau. Thuộc tính `binder` trên binding nhận **configuration name**, không phải destination, tên topic hay tên type nếu cấu hình đã được đặt tên riêng.

## 1. Binder type và Binder configuration name

Mỗi thư viện binder cung cấp file `META-INF/spring.binders`. File này ánh xạ một khóa định danh type với lớp cấu hình tạo Binder. Ví dụ, thư viện RabbitMQ đăng ký type `rabbit`, thư viện Kafka đăng ký type `kafka`; binder tùy chỉnh cũng cần đăng ký type của nó.

Khi chỉ có một binder implementation trên classpath, Spring Cloud Stream có thể tự chọn binder đó. Khi có nhiều binder implementation, ứng dụng phải chỉ rõ binder nào phục vụ từng binding hoặc đặt một default binder.

Trong cấu hình nhiều broker, một type có thể được khai báo nhiều lần với configuration name khác nhau:

| Binder configuration name | Binder type | Broker |
|---|---|---|
| `ordersKafka` | `kafka` | Kafka cluster xử lý đơn hàng |
| `auditKafka` | `kafka` | Kafka cluster lưu audit |
| `commandsRabbit` | `rabbit` | RabbitMQ cluster gửi command |
| `eventsPulsar` | `pulsar` | Pulsar service cho event |

Configuration name là tên do ứng dụng quản lý. Type phải khớp với type mà binder implementation đăng ký. Nên khai báo `type` tường minh, đặc biệt khi tên cấu hình không giống type.

## 2. Chọn binder toàn cục bằng defaultBinder

Nếu phần lớn binding dùng chung một binder, có thể đặt binder mặc định:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
~~~

Khi đó, binding không khai báo thuộc tính `binder` sẽ dùng binder mặc định nếu binder đó được cấu hình và có thể được chọn làm default candidate.

Có thể ghi đè ở cấp binding:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        orders-in-0:
          destination: orders.created
        alerts-out-0:
          destination: operations.alerts
          binder: rabbit
~~~

Trong ví dụ, `orders-in-0` dùng default binder `kafka`; `alerts-out-0` dùng binder `rabbit`. Cách này phù hợp khi có một hệ thống messaging chính và chỉ một số luồng cần broker khác.

Nếu nhiều binder cùng có thể làm default và không có lựa chọn rõ ràng, việc khởi tạo binding có thể mơ hồ. Đừng dựa vào thứ tự dependency hoặc thứ tự tên trong YAML để chọn binder. Hãy đặt `default-binder` hoặc gắn binder cho từng binding.

## 3. Gắn binder riêng cho từng binding

Thuộc tính chung của binding có dạng:

~~~text
spring.cloud.stream.bindings.<bindingName>.binder
~~~

Ví dụ function đọc đơn hàng từ Kafka rồi phát command sang RabbitMQ:

~~~java
@Bean
Function<OrderCreated, ShippingCommand> routeOrder() {
    return event -> new ShippingCommand(
        event.orderId(),
        event.destination()
    );
}
~~~

Function có hai binding mặc định:

- `routeOrder-in-0`: input.
- `routeOrder-out-0`: output.

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrder
    stream:
      bindings:
        routeOrder-in-0:
          destination: orders.created
          group: shipping-service
          binder: kafka
        routeOrder-out-0:
          destination: shipping.commands
          binder: rabbit
~~~

Input binding đọc từ topic `orders.created` bằng Kafka binder. Output binding publish đến exchange/destination `shipping.commands` bằng Rabbit binder. Function không cần biết chi tiết broker; nó xử lý kiểu dữ liệu Java được framework chuyển đến.

Mỗi binding có một binder được chọn. Một consumer binding có thể đọc nhiều destination theo khả năng của binder, nhưng các destination của cùng binding vẫn thuộc một binder configuration. Nếu cần nhận dữ liệu từ nhiều hệ thống độc lập, hãy tạo các binding/processor phù hợp thay vì cố gán nhiều binder cho một binding.

## 4. Khai báo named binder trong YAML

Khi cần cấu hình riêng từng broker, dùng nhánh:

~~~text
spring.cloud.stream.binders.<configurationName>
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| `type` | Binder implementation type, ví dụ `kafka`, `rabbit`, `pulsar` | Bằng configuration name nếu bỏ qua |
| `environment` | Nhóm Spring Boot properties dành cho binder instance đó | Rỗng |
| `inherit-environment` | Có kế thừa environment của ứng dụng hay không | `true` |
| `default-candidate` | Cấu hình có được xem xét làm default binder hay chỉ dùng khi tham chiếu tường minh | `true` |

Ví dụ khai báo hai broker:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${ORDERS_KAFKA_BROKERS:localhost:9092}
        commandsRabbit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: ${COMMANDS_RABBIT_HOST:localhost}
                port: ${COMMANDS_RABBIT_PORT:5672}
                username: ${COMMANDS_RABBIT_USERNAME:guest}
                password: ${COMMANDS_RABBIT_PASSWORD:guest}
~~~

Trong ví dụ:

- `ordersKafka` là configuration name; `kafka` là type.
- `commandsRabbit` là configuration name; `rabbit` là type.
- `environment` chứa các thuộc tính Spring Boot mà binder instance sử dụng để kết nối.
- Các giá trị môi trường được truyền qua biến môi trường hoặc secret store khi triển khai.

Không dùng `ordersKafka` làm type chỉ vì đó là tên cấu hình. Nếu type không khớp binder implementation có trên classpath, framework không thể tạo binder tương ứng.

## 5. Gắn named binder vào binding

Sau khi khai báo named binder, gắn configuration name vào đúng binding:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrder
    stream:
      bindings:
        routeOrder-in-0:
          destination: orders.created
          group: shipping-service
          binder: ordersKafka
        routeOrder-out-0:
          destination: shipping.commands
          binder: commandsRabbit
      binders:
        ordersKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${ORDERS_KAFKA_BROKERS:localhost:9092}
        commandsRabbit:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: ${COMMANDS_RABBIT_HOST:localhost}
                port: ${COMMANDS_RABBIT_PORT:5672}
                username: ${COMMANDS_RABBIT_USERNAME:guest}
                password: ${COMMANDS_RABBIT_PASSWORD:guest}
~~~

Đây là ví dụ hoàn chỉnh cho một processor đọc từ Kafka và ghi sang RabbitMQ. Thuộc tính `binder` nhận `ordersKafka` và `commandsRabbit`, không nhận `kafka` hoặc `rabbit`, bởi ứng dụng đang tham chiếu hai cấu hình được đặt tên.

Nếu dùng nhiều function trong cùng ứng dụng, khai báo `spring.cloud.function.definition` với các function cần kích hoạt và đặt `binder` trên từng binding được tạo ra. Không đoán tên binding từ tên destination; hãy dùng tên function cộng hậu tố `-in-0`, `-out-0` hoặc chỉ số tương ứng.

## 6. Kết nối hai broker cùng loại

Named binder không chỉ dành cho hai loại middleware khác nhau. Nó còn cho phép ứng dụng kết nối nhiều broker cùng loại với các địa chỉ và thông tin xác thực riêng.

Ví dụ một function đọc audit từ Kafka cluster chính rồi ghi bản sao sang Kafka cluster lưu trữ:

~~~java
@Bean
Function<AuditEvent, AuditArchiveRecord> archiveAudit() {
    return event -> new AuditArchiveRecord(
        event.eventId(),
        event.occurredAt(),
        event.action()
    );
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: archiveAudit
    stream:
      bindings:
        archiveAudit-in-0:
          destination: audit.events
          group: audit-archiver
          binder: kafkaPrimary
        archiveAudit-out-0:
          destination: audit.archive
          binder: kafkaArchive
      binders:
        kafkaPrimary:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_PRIMARY_BROKERS}
        kafkaArchive:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_ARCHIVE_BROKERS}
~~~

Cả hai cấu hình có `type: kafka`, nhưng `kafkaPrimary` và `kafkaArchive` có environment riêng. Binding input dùng cluster chính; binding output dùng cluster lưu trữ. Cách này cũng áp dụng được cho hai RabbitMQ broker hoặc hai Pulsar service khi có các binder instance riêng.

Nếu dùng thuộc tính chung ở root như `spring.kafka.bootstrap-servers` cho nhiều binder instance, hãy kiểm tra xem chúng có vô tình dùng chung một địa chỉ hay không. Với named binder, đặt thuộc tính kết nối trong `environment` của từng binder để thể hiện rõ broker đích.

## 7. Cách ly environment bằng inheritEnvironment

Mặc định, binder configuration kế thừa environment của ứng dụng (`inherit-environment: true`). Khi cấu hình `environment`, binder nhận các thuộc tính riêng; nếu cần tách biệt hoàn toàn khỏi environment ứng dụng, đặt:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        isolatedKafka:
          type: kafka
          inherit-environment: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${ISOLATED_KAFKA_BROKERS}
~~~

Khi không kế thừa environment, binder context không nhận các thuộc tính cấu hình từ application context theo cách mặc định. Vì vậy, phải đưa đầy đủ các thuộc tính cần thiết vào `environment`, bao gồm cấu hình kết nối, bảo mật và các cấu hình Spring Boot phụ thuộc. Không bật cách ly nếu chưa xác định rõ những thuộc tính nào đang được kế thừa.

`environment` là một environment Spring Boot riêng cho binder; nó có thể chứa bất kỳ Spring Boot property hợp lệ nào, không chỉ thuộc tính kết nối broker. Có thể kích hoạt profile riêng bằng `spring.profiles.active` trong environment của binder:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        securedRabbit:
          type: rabbit
          environment:
            spring:
              profiles:
                active: rabbit-production
~~~

Profile được kích hoạt trong môi trường binder đó. Hãy bảo đảm file cấu hình profile và secret tương ứng có mặt trong runtime.

## 8. Phân biệt defaultCandidate và defaultBinder

Hai thuộc tính này giải quyết hai việc khác nhau:

- `default-binder` chỉ định binder mặc định mà các binding không khai báo binder sẽ dùng.
- `default-candidate` quyết định một binder configuration có được xem xét làm ứng viên default hay chỉ dùng khi binding tham chiếu trực tiếp.

Ví dụ một binder được tạo để chỉ dùng cho luồng audit:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        auditArchive:
          type: kafka
          default-candidate: false
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${AUDIT_ARCHIVE_BROKERS}
      bindings:
        audit-out-0:
          destination: audit.archive
          binder: auditArchive
~~~

`auditArchive` vẫn có thể được dùng vì binding tham chiếu trực tiếp tên đó, nhưng không được chọn làm default binder. Cách này hữu ích khi một framework hoặc một phần ứng dụng bổ sung binder configuration mà không muốn làm thay đổi lựa chọn mặc định của các binding khác.

Nếu một binding không có `binder` và không có default binder khả dụng, framework có thể không xác định được binder để tạo binding. Hãy bảo đảm mọi binding đều được gắn rõ hoặc có một default binder hợp lệ.

## 9. Cấu hình tường minh thay thế cơ chế binder mặc định

Khi khai báo các named binder configurations trong `spring.cloud.stream.binders`, Spring Cloud Stream chuyển sang cơ chế cấu hình binder tường minh và không thực hiện quy trình tạo default binder tự động như trước. Vì vậy, tất cả binder mà ứng dụng cần dùng phải được khai báo đầy đủ trong cấu hình.

Ví dụ nếu ứng dụng dùng Kafka và RabbitMQ qua named configuration, hãy khai báo cả hai:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaOrders:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_BROKERS}
        rabbitEvents:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: ${RABBIT_HOST}
      bindings:
        orders-in-0:
          destination: orders.created
          binder: kafkaOrders
        events-out-0:
          destination: domain.events
          binder: rabbitEvents
~~~

Không khai báo một named binder rồi giả định các binder khác trên classpath vẫn tự được tạo theo cơ chế mặc định. Nếu ứng dụng cần một binder cấu hình mặc định và các binder cấu hình chỉ được tham chiếu rõ, hãy thiết kế `defaultCandidate` và binding assignment tường minh, rồi kiểm tra danh sách binder thực tế lúc khởi động.

## 10. Cấu hình thuộc tính riêng của binder

Thuộc tính chung của binding nằm dưới:

~~~text
spring.cloud.stream.bindings.<bindingName>
~~~

Ví dụ `destination`, `group`, `content-type` và `binder` được đặt ở đây. Thuộc tính mở rộng của middleware nằm dưới prefix theo binder type:

| Binder type | Prefix thuộc tính mở rộng |
|---|---|
| Kafka | `spring.cloud.stream.kafka.bindings.<bindingName>` |
| RabbitMQ | `spring.cloud.stream.rabbit.bindings.<bindingName>` |
| Pulsar | `spring.cloud.stream.pulsar.bindings.<bindingName>` |

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-processor
          binder: ordersKafka
      kafka:
        bindings:
          orders-in-0:
            consumer:
              ack-mode: RECORD
~~~

Prefix mở rộng vẫn dựa trên binder implementation, còn `binder` ở binding chọn named configuration. Khi nhiều instance cùng type cần các thuộc tính mở rộng khác nhau, kiểm tra xem thuộc tính đó được hỗ trợ ở cấp binder environment hay cấp binding; không chuyển nhầm cấu hình của Kafka sang Rabbit hoặc Pulsar.

## 11. Một binding không tự tạo transaction xuyên broker

Ví dụ function đọc Kafka rồi publish RabbitMQ chỉ là một luồng xử lý nối hai broker. Việc mỗi binding dùng binder riêng không tạo ra transaction phân tán chung giữa Kafka và RabbitMQ.

Có thể xảy ra tình huống:

1. Consumer đọc record từ Kafka.
2. Function xử lý và publish message sang RabbitMQ.
3. RabbitMQ đã nhận message.
4. Ứng dụng lỗi trước khi offset Kafka được commit.
5. Kafka giao lại record và function có thể publish duplicate sang RabbitMQ.

Hoặc publish sang RabbitMQ thất bại sau khi Kafka consumer đã tiến offset nếu ứng dụng/ack strategy được cấu hình không phù hợp. Hãy thiết kế retry, publisher confirms, consumer acknowledgement, idempotency key, outbox hoặc quy trình đối soát theo yêu cầu nghiệp vụ. Không tuyên bố exactly-once chỉ vì mỗi binding đã được gắn đúng binder.

## 12. Ranh giới giữa regular Kafka Binder và Kafka Streams Binder

Ứng dụng có thể dùng regular Kafka Binder và Kafka Streams Binder trong cùng Spring Cloud Stream application nếu chúng phục vụ các function/processor riêng. Tuy nhiên, không trộn hai loại binder bên trong cùng một function hoặc consumer.

Kafka Streams binder family còn có các type riêng như `kstream`, `ktable` và `globalktable`. Trong một ứng dụng thực sự dùng nhiều processor trên nhiều Kafka cluster hoặc kết hợp regular Kafka Binder với Kafka Streams Binder, phải khai báo type phù hợp cho từng named binder và gắn từng binding vào đúng configuration name.

Ví dụ này là tình huống chuyên biệt:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        kafkaMessages:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${KAFKA_MESSAGES_BROKERS}
        kafkaTopology:
          type: kstream
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    streams:
                      binder:
                        brokers: ${KAFKA_STREAMS_BROKERS}
~~~

Chỉ dùng cấu hình `kstream` khi có Kafka Streams binder dependency và function có chữ ký Kafka Streams phù hợp. Đừng đặt type `kstream` cho function `Function<String, String>` thông thường.

## 13. Dependency và phát hiện binder

Khai báo binder configuration không tự thêm thư viện binder vào classpath. Ứng dụng phải có dependency tương ứng:

- Kafka Binder để dùng type `kafka`.
- RabbitMQ Binder để dùng type `rabbit`.
- Pulsar Binder để dùng type `pulsar`.
- Kafka Streams Binder để dùng type thuộc họ Kafka Streams như `kstream`.

Nếu binder type không được đăng ký trên classpath, framework không thể tạo binder chỉ từ YAML. Với binder tùy chỉnh, thư viện cần cung cấp metadata `META-INF/spring.binders` và cấu hình tạo bean Binder đúng theo Binder SPI.

Khi ứng dụng có nhiều binder dependency, hãy kiểm tra phiên bản tương thích của Spring Cloud Stream và từng binder. Dùng dependency management/BOM phù hợp để tránh trộn các phiên bản binder không tương thích.

## 14. Bảo mật cấu hình từng broker

Mỗi named binder có thể có thông tin xác thực, TLS và network endpoint riêng. Không commit password, token, private key hoặc JAAS secret vào YAML:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        securedKafka:
          type: kafka
          environment:
            spring:
              cloud:
                stream:
                  kafka:
                    binder:
                      brokers: ${SECURED_KAFKA_BROKERS}
                      configuration:
                        security.protocol: SASL_SSL
                        sasl.mechanism: PLAIN
                        sasl.jaas.config: ${SECURED_KAFKA_JAAS}
~~~

Ví dụ minh họa vị trí cấu hình Kafka client properties; giá trị thực tế phải theo cơ chế xác thực của cluster và được cấp qua secret manager hoặc biến môi trường được bảo vệ. Với RabbitMQ và Pulsar, đặt credential/TLS trong environment của named binder tương ứng.

Nếu dùng `inherit-environment: false`, hãy đưa tất cả thuộc tính cần thiết vào environment riêng của binder. Kiểm tra log khởi động để bảo đảm không in secret hoặc toàn bộ connection string chứa credential.

## 15. Kiểm thử cấu hình nhiều binder

Nên kiểm tra cả việc chọn binder và hành vi truyền message:

1. Khởi động ứng dụng với tất cả binder dependency cần dùng.
2. Xác nhận mỗi named binder có type hợp lệ và kết nối đúng broker.
3. Kiểm tra GET `/actuator/bindings` hoặc log binding để xác nhận binding name, destination và binder assignment.
4. Publish message vào input broker và xác nhận function nhận đúng payload.
5. Xác nhận output xuất hiện ở đúng broker/destination được gắn cho output binding.
6. Thử cùng binder type với hai broker khác nhau và xác nhận không gửi nhầm cluster.
7. Thử `default-binder` cùng binding-level override.
8. Thử `default-candidate: false` để bảo đảm binder chỉ được dùng khi tham chiếu rõ.
9. Thử `inherit-environment: false` và xác nhận binder vẫn có đủ cấu hình kết nối.
10. Kiểm tra lỗi khi thiếu binder dependency, sai type, sai configuration name hoặc thiếu broker endpoint.
11. Kiểm tra timeout, mất kết nối, retry và duplicate khi chuyển tiếp giữa hai broker.

Test Binder có thể kiểm tra logic function và message contract, nhưng không thay thế integration test với từng broker thật. Với ứng dụng kết nối Kafka và RabbitMQ, cần môi trường test có cả hai broker; với nhiều Kafka cluster, cần xác nhận từng binding dùng đúng cluster bằng dữ liệu thử riêng.

## 16. Lỗi thường gặp khi khai báo nhiều binder

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy binder type | Thiếu binder dependency hoặc type sai | Kiểm tra classpath và khóa trong `META-INF/spring.binders` |
| Không tìm thấy binder configuration | Binding dùng type thay vì configuration name | Đặt đúng tên dưới `spring.cloud.stream.binders` |
| Binding dùng nhầm broker | Thiếu `binder` hoặc default binder không đúng | Gắn configuration name rõ cho binding |
| Hai Kafka binding kết nối cùng cluster | Cả hai cùng kế thừa một cấu hình root hoặc environment không tách | Đặt broker riêng trong từng named binder environment |
| Ứng dụng không tạo default binder | Đã bật explicit binder config nhưng chưa khai báo tất cả binder cần dùng | Khai báo đầy đủ các binder trong `binders` |
| Default binder bị mơ hồ | Nhiều default candidates hoặc không đặt default | Đặt `default-binder` và điều chỉnh `default-candidate` |
| Binder không đọc được cấu hình profile | Profile đặt ở application context thay vì binder environment | Đặt `spring.profiles.active` trong environment của binder |
| Binder isolated thiếu credentials | `inherit-environment: false` nhưng chưa chuyển các thuộc tính cần thiết | Bổ sung endpoint, auth, TLS và property phụ thuộc |
| Output không đến broker đích | Binding name hoặc destination/binder assignment sai | Kiểm tra binding thực tế và log khởi tạo |
| Duplicate sau lỗi chuyển tiếp | Không có transaction chung giữa hai broker | Dùng idempotency, retry có kiểm soát và outbox/đối soát |

## 17. Checklist trước khi triển khai

- [ ] Đã phân biệt binder type, binder configuration name và binding name.
- [ ] Đã thêm dependency cho mọi binder type được sử dụng.
- [ ] Mỗi named binder có `type` đúng với binder implementation.
- [ ] Mỗi binding được gắn đúng configuration name hoặc có default binder rõ ràng.
- [ ] Các broker cùng type có named configuration và environment riêng.
- [ ] Đã hiểu `inherit-environment` và `default-candidate`.
- [ ] Khi dùng explicit binder configuration, đã khai báo đầy đủ mọi binder cần dùng.
- [ ] Binder-specific properties được đặt dưới đúng prefix của middleware.
- [ ] Endpoint và credentials được truyền qua environment/secret store.
- [ ] Đã kiểm thử từng binding với đúng broker và destination.
- [ ] Đã đánh giá retry, duplicate và tính nguyên tử khi chuyển tiếp giữa broker khác loại.
- [ ] Đã xác minh phiên bản binder tương thích với Spring Cloud Stream đang dùng.

Named binder configuration cho phép một ứng dụng kết nối nhiều middleware hoặc nhiều broker cùng loại. Khai báo một configuration name cho từng kết nối, đặt `type` theo binder implementation, cấu hình broker riêng trong `environment`, rồi gắn tên đó vào `spring.cloud.stream.bindings.<bindingName>.binder`. Dùng `default-binder` cho luồng mặc định và `default-candidate` để kiểm soát cấu hình nào có thể được chọn mặc định. Việc gắn binder đúng giúp định tuyến binding đến đúng broker; nó không tự tạo transaction xuyên broker, vì vậy cần thiết kế retry và idempotency cho luồng chuyển tiếp.

## Tài liệu tham khảo

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Binder Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binder-configuration-properties.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream Kafka Binder — Multi Binders with Kafka Streams and Regular Kafka Binder](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html#multi-binders-with-kafka-streams-based-binders-and-regular-kafka-binder)
