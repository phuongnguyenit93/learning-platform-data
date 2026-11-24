# Exchange type, binding routing key và routingKeyExpression

Trong RabbitMQ, producer gửi message đến exchange; exchange chọn queue nhận message dựa trên loại exchange và các binding đã khai báo. Với Spring Cloud Stream RabbitMQ Binder, thuộc tính exchangeType quyết định cách exchange định tuyến, bindingRoutingKey cấu hình khóa dùng khi gắn queue vào exchange, còn routingKeyExpression tính routing key cho từng message do producer phát ra.

Ba cấu hình này nằm ở hai phía khác nhau của luồng. Consumer tạo queue binding và chọn mẫu khóa mà queue muốn nhận. Producer tạo routing key thực tế cho message. Hai phía phải thống nhất: producer phát khóa nào thì binding của queue phải khớp khóa đó theo quy tắc của exchange.

## 1. Exchange, queue, binding và routing key

Trong AMQP 0-9-1, producer không gửi message trực tiếp đến queue. Producer publish message đến một exchange. Exchange dùng các binding để quyết định message được chuyển tới queue, stream hoặc exchange khác.

| Thành phần | Vai trò |
|---|---|
| Exchange | Nhận message từ producer và áp dụng quy tắc định tuyến |
| Queue | Lưu message để consumer nhận và xử lý |
| Binding | Liên kết exchange với queue, kèm routing key hoặc arguments nếu loại exchange cần |
| Routing key | Giá trị producer gắn với lần publish; exchange dùng nó để định tuyến tùy loại |
| Binding key | Khóa hoặc mẫu khóa được lưu trong binding của queue |

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    P["Producer"] -->|"routing key"| E["Exchange"]
    E -->|"binding key / arguments"| Q1[("Queue A")]
    E -->|"binding key / arguments"| Q2[("Queue B")]
    Q1 --> C1["Consumer A"]
    Q2 --> C2["Consumer B"]
~~~

Một exchange có thể có nhiều queue được bind. Một message có thể được định tuyến tới một queue, nhiều queue hoặc không queue nào, tùy exchange type và binding.

## 2. RabbitMQ Binder ánh xạ destination như thế nào?

Theo mặc định, Spring Cloud Stream Rabbit binder ánh xạ mỗi destination thành một TopicExchange. Khi có consumer group, binder tạo queue theo dạng:

~~~text
<prefix><destination>.<group>
~~~

Queue được bind vào exchange với routing key mặc định # cho destination không partition. Nếu không khai báo group, binder tạo một queue anonymous có tên ngẫu nhiên và tự xóa theo vòng đời consumer.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-service
~~~

Topology mặc định có dạng:

~~~text
Exchange: orders.events (topic)
Queue:    orders.events.order-service
Binding:  orders.events -> orders.events.order-service, key #
~~~

Với topic exchange, binding key # khớp mọi routing key. Vì vậy, queue mặc định nhận mọi message được publish đến exchange orders.events.

Các thuộc tính Rabbit binder liên quan đến định tuyến:

| Thuộc tính | Phía cấu hình | Chức năng |
|---|---|---|
| exchangeType | Consumer hoặc producer | Chọn loại exchange được khai báo cho destination |
| bindingRoutingKey | Consumer; hoặc producer khi tạo required groups | Chọn routing key/binding key dùng khi bind queue |
| bindingRoutingKeyDelimiter | Consumer hoặc producer | Tách nhiều binding key từ một chuỗi |
| routingKeyExpression | Producer | Tính routing key thực tế cho từng message |
| routingKey | Producer | Dùng một routing key cố định |
| queueBindingArguments | Consumer | Cung cấp arguments cho binding, thường dùng với headers exchange |

Các thuộc tính Rabbit-specific nằm dưới spring.cloud.stream.rabbit.bindings.<binding-name>.<consumer|producer>. Thuộc tính destination và group nằm dưới spring.cloud.stream.bindings.<binding-name>.

## 3. Bốn exchange type thường dùng

RabbitMQ cung cấp bốn exchange type cơ bản: direct, topic, fanout và headers. Rabbit binder hỗ trợ cả bốn cho destination không partition; với destination partitioned, binder hỗ trợ direct, topic và headers.

### 3.1. Direct exchange: khớp chính xác

Direct exchange định tuyến message tới queue có binding key trùng chính xác với routing key của message. Không có wildcard.

Ví dụ:

| Queue | Binding key | Routing key của message | Nhận message? |
|---|---|---|---|
| orders.created | order.created | order.created | Có |
| orders.updated | order.updated | order.created | Không |
| orders.audit | order.created | order.created | Có |

Một routing key có thể khớp nhiều binding giống nhau, nên direct exchange không nhất thiết chỉ chuyển tới một queue. Nếu hai queue cùng bind bằng order.created, cả hai đều nhận message.

Sơ đồ:

~~~mermaid
flowchart LR
    P["Producer<br/>key = order.created"] --> E["Direct exchange"]
    E -->|"order.created"| A[("Queue created")]
    E -. "order.updated: không khớp" .-> B[("Queue updated")]
~~~

Ví dụ cấu hình consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        createdOrders-in-0:
          destination: orders.events
          group: created-orders
      rabbit:
        bindings:
          createdOrders-in-0:
            consumer:
              exchangeType: direct
              bindingRoutingKey: order.created
~~~

Producer phải publish vào cùng destination với routing key order.created:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: direct
              routingKey: order.created
~~~

Nếu producer phát order.updated, queue created-orders không nhận message vì binding chỉ chấp nhận khóa order.created.

### 3.2. Topic exchange: khớp mẫu theo các đoạn

Topic exchange chia routing key thành các đoạn phân tách bằng dấu chấm (.). Binding key có thể dùng hai wildcard:

- * khớp chính xác một đoạn.
- # khớp không hoặc nhiều đoạn.

Ví dụ:

| Binding key | Routing key | Khớp? | Lý do |
|---|---|---|---|
| orders.* | orders.created | Có | * khớp một đoạn created |
| orders.* | orders.eu.created | Không | Có hai đoạn sau orders |
| orders.# | orders.eu.created | Có | # khớp nhiều đoạn |
| orders.# | orders | Có | # có thể khớp không đoạn nào |
| *.created | orders.created | Có | * khớp orders |
| *.created | orders.eu.created | Không | * chỉ khớp một đoạn |

Ví dụ định tuyến:

~~~mermaid
flowchart LR
    P["Producer<br/>orders.eu.created"] --> E["Topic exchange"]
    E -->|"orders.* không khớp"| A[("Queue orders-one-level")]
    E -->|"orders.# khớp"| B[("Queue all-orders")]
    E -->|"orders.eu.* khớp"| C[("Queue eu-orders")]
~~~

Topic exchange phù hợp khi cần phân phối sự kiện theo cây phân loại như khu vực, loại sự kiện hoặc domain. Ví dụ routing key orders.eu.created, orders.us.cancelled, payments.eu.completed.

Cấu hình queue chỉ nhận sự kiện đơn hàng ở khu vực EU:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euOrders-in-0:
          destination: business.events
          group: eu-orders
      rabbit:
        bindings:
          euOrders-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: orders.eu.#
~~~

Queue business.events.eu-orders nhận các khóa như orders.eu.created, orders.eu.cancelled hoặc orders.eu.refunded, nhưng không nhận orders.us.created.

### 3.3. Fanout exchange: phát tới mọi queue đã bind

Fanout exchange gửi một bản sao message đến mọi queue được bind vào exchange. Nó bỏ qua routing key và binding key.

Ví dụ:

~~~mermaid
flowchart LR
    P["Producer"] --> E["Fanout exchange"]
    E --> Q1[("Queue email")]
    E --> Q2[("Queue analytics")]
    E --> Q3[("Queue audit")]
~~~

Fanout phù hợp cho thông báo cần broadcast tới nhiều dịch vụ độc lập, chẳng hạn một sự kiện cấu hình mới cần được cache, audit và analytics cùng nhận.

Cấu hình consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvents-in-0:
          destination: system.notifications
          group: audit-service
      rabbit:
        bindings:
          auditEvents-in-0:
            consumer:
              exchangeType: fanout
~~~

Mọi queue được bind vào exchange system.notifications đều nhận message. bindingRoutingKey và routingKeyExpression không quyết định việc phân phối trong fanout exchange vì loại exchange này bỏ qua routing key.

### 3.4. Headers exchange: định tuyến theo header

Headers exchange so sánh message headers với các arguments trong binding. Routing key không được dùng để định tuyến.

Binding có thể yêu cầu:

- x-match: all: mọi header được khai báo phải khớp.
- x-match: any: chỉ cần một header trong số được khai báo khớp.

Ví dụ queue chỉ nhận message có region=eu và eventType=order-created:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euOrderCreated-in-0:
          destination: business.events
          group: eu-order-created
      rabbit:
        bindings:
          euOrderCreated-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: all
                region: eu
                eventType: order-created
~~~

Producer gửi message có các header tương ứng:

~~~java
Message<OrderEvent> message = MessageBuilder
    .withPayload(orderEvent)
    .setHeader("region", "eu")
    .setHeader("eventType", "order-created")
    .build();
~~~

Nếu dùng x-match: all, message cần có cả hai header với giá trị đúng. Nếu dùng x-match: any, chỉ cần một điều kiện trong số đó khớp. Headers exchange phù hợp khi điều kiện định tuyến dựa trên nhiều thuộc tính message thay vì một chuỗi routing key phân cấp.

## 4. Phân biệt bindingRoutingKey và routingKeyExpression

Hai thuộc tính có tên gần giống nhưng hoạt động ở hai thời điểm khác nhau:

| Thuộc tính | Ai cấu hình? | Áp dụng lúc nào? | Ví dụ |
|---|---|---|---|
| bindingRoutingKey | Consumer | Khi binder bind queue vào exchange | orders.eu.# |
| routingKeyExpression | Producer | Mỗi lần producer gửi message | payload.region + '.' + payload.eventType |

bindingRoutingKey là quy tắc nhận của queue. routingKeyExpression tạo routing key thực tế trên message gửi đi. Với topic exchange, binding key thường chứa wildcard, còn routing key của message là một giá trị cụ thể.

Ví dụ:

- Consumer bind queue bằng orders.eu.#.
- Producer phát routing key orders.eu.created.
- Topic exchange so khớp và chuyển message đến queue.

Nếu producer tạo orders.us.created, queue EU không nhận message. Việc đặt đúng expression phía producer là chưa đủ; queue phải có binding key khớp.

## 5. Dùng routingKeyExpression để định tuyến theo payload

routingKeyExpression là biểu thức SpEL được đánh giá khi publish message. Biểu thức có thể lấy dữ liệu từ payload hoặc header để tạo routing key động.

Giả sử payload:

~~~java
public record OrderEvent(
    String orderId,
    String region,
    String eventType
) {}
~~~

Producer dùng khu vực và loại sự kiện để tạo khóa:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: business.events
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: topic
              routingKeyExpression: "payload.region + '.' + payload.eventType"
~~~

Với payload region=eu, eventType=created, producer phát routing key eu.created. Một consumer có binding key eu.* sẽ nhận message đó.

Có thể đọc giá trị từ message header:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKeyExpression: "headers['region'] + '.' + headers['eventType']"
~~~

Nếu message có header region=eu và eventType=created, khóa được tạo là eu.created. Hãy bảo đảm header luôn tồn tại và có giá trị hợp lệ; expression không xử lý được header thiếu có thể làm quá trình publish thất bại.

### 5.1. Dùng routing key cố định

Nếu mọi message đều cần cùng một routing key, dùng routingKey thay cho biểu thức:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKey: orders.created
~~~

routingKeyExpression phù hợp khi routing key phụ thuộc từng message. routingKey dễ đọc hơn khi khóa là hằng số. Không cần dùng một expression phức tạp chỉ để trả về một chuỗi cố định.

Nếu dùng biểu thức SpEL để trả về chuỗi literal, YAML cần escape dấu nháy theo cú pháp của SpEL. Tài liệu binder minh họa dạng routingKeyExpression: '''my.routingKey'''; dùng thuộc tính routingKey sẽ đơn giản hơn trong trường hợp cố định.

### 5.2. Giá trị mặc định

Nếu không cấu hình routingKey hoặc routingKeyExpression, Rabbit producer binder dùng destination làm routing key mặc định. Với partitioned destination, khóa mặc định có dạng destination-<partition>.

Đối với consumer binding, bindingRoutingKey mặc định là #. Vì binder mặc định tạo topic exchange, queue group nhận mọi routing key của destination. Khi chuyển exchange sang direct, cần cấu hình binding key khớp chính xác với routing key mà producer phát.

## 6. Cấu hình nhiều binding key cho một queue

Một queue có thể cần nhận nhiều nhóm routing key. Rabbit binder hỗ trợ danh sách bindingRoutingKey qua bindingRoutingKeyDelimiter.

Ví dụ queue nhận cả sự kiện tạo và cập nhật đơn hàng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderChanges-in-0:
          destination: orders.events
          group: order-changes
      rabbit:
        bindings:
          orderChanges-in-0:
            consumer:
              exchangeType: direct
              bindingRoutingKey: "order.created,order.updated"
              bindingRoutingKeyDelimiter: ","
~~~

Binder tạo hai binding key riêng cho queue:

- order.created
- order.updated

Với topic exchange, có thể kết hợp nhiều mẫu như orders.eu.#,payments.eu.#. Hãy chọn delimiter không xuất hiện trong chính routing key để tránh tách sai.

Thuộc tính producer bindingRoutingKey cũng có thể áp dụng cho các group được khai báo trong requiredGroups. Nó chỉ có hiệu lực khi binder tạo queue và binding cho các group đó. Nếu queue được quản lý thủ công hoặc bindQueue=false, cần tạo routing binding ở broker theo topology đã định.

## 7. Cấu hình exchange type và binding nhất quán

Producer và consumer thường cùng tham chiếu một destination, do đó chúng cần thống nhất loại exchange. Ví dụ producer khai báo direct nhưng consumer lại khai báo topic cho cùng exchange name sẽ tạo topology không tương thích.

Ví dụ ứng dụng có một Supplier phát sự kiện và một Consumer nhận các sự kiện phù hợp:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String region, String eventType) {}

@Configuration
class OrderRoutingFunctions {

    @Bean
    Supplier<OrderEvent> publishOrder() {
        return () -> new OrderEvent("order-1001", "eu", "created");
    }

    @Bean
    Consumer<OrderEvent> consumeEuOrders() {
        return event -> System.out.println("EU order: " + event.orderId());
    }
}
~~~

Mẫu cấu hình đầy đủ cho topic exchange:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder;consumeEuOrders
    stream:
      bindings:
        publishOrder-out-0:
          destination: business.events
        consumeEuOrders-in-0:
          destination: business.events
          group: eu-orders
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: topic
              routingKeyExpression: "payload.region + '.' + payload.eventType"
          consumeEuOrders-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: eu.#
~~~

Trong ví dụ, producer và consumer cùng dùng exchange business.events loại topic. Producer tạo routing key theo payload; queue của group eu-orders chỉ nhận khóa bắt đầu bằng eu.

Nếu exchange đã được tạo sẵn, binder không thể thay đổi loại exchange chỉ bằng cách khai báo một exchangeType khác. RabbitMQ yêu cầu các lần declare cùng tên phải có thuộc tính tương thích. Nếu loại exchange không khớp, broker có thể trả lỗi PRECONDITION_FAILED - inequivalent arg type. Hãy thống nhất topology trước khi triển khai.

## 8. Khi dùng headers exchange

Headers exchange không đọc routing key. Producer phải gửi các header mà consumer binding mong đợi; queue binding phải khai báo arguments phù hợp.

Ví dụ hai queue phân luồng theo vùng và loại sự kiện:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euPayments-in-0:
          destination: business.events
          group: eu-payments
        urgentEvents-in-0:
          destination: business.events
          group: urgent-events
      rabbit:
        bindings:
          euPayments-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: all
                region: eu
                domain: payment
          urgentEvents-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: any
                priority: urgent
                requiresAttention: true
~~~

Queue eu-payments yêu cầu cả region=eu và domain=payment. Queue urgent-events nhận message khi một trong hai header priority=urgent hoặc requiresAttention=true khớp.

Không dùng wildcard * hoặc # cho giá trị header. Headers exchange so sánh giá trị header với binding arguments; nó không áp dụng cú pháp wildcard của topic exchange.

## 9. Dùng fanout exchange cho broadcast

Nếu mọi consumer group đều phải nhận mọi message, fanout exchange thường đơn giản hơn topic exchange với binding key #.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishSystemEvent-out-0:
          destination: system.events
        auditSystemEvent-in-0:
          destination: system.events
          group: audit
        metricsSystemEvent-in-0:
          destination: system.events
          group: metrics
      rabbit:
        bindings:
          publishSystemEvent-out-0:
            producer:
              exchangeType: fanout
          auditSystemEvent-in-0:
            consumer:
              exchangeType: fanout
          metricsSystemEvent-in-0:
            consumer:
              exchangeType: fanout
~~~

Mỗi group có queue riêng. Fanout exchange gửi một bản sao tới từng queue được bind, nên cả audit và metrics đều nhận message. Giá trị routing key do producer đặt không ảnh hưởng kết quả.

## 10. Quản lý topology đã tồn tại

Rabbit binder mặc định có thể khai báo exchange, queue và binding. Nếu đội nền tảng đã tạo topology trước, cần quyết định binder sẽ tự khai báo những thành phần nào.

Để dùng exchange và queue đã tồn tại, tài liệu binder minh họa:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consumeExisting-in-0:
          destination: myExchange
          group: myQueue
      rabbit:
        bindings:
          consumeExisting-in-0:
            consumer:
              bindQueue: false
              declareExchange: false
              queueNameGroupOnly: true
~~~

Với cấu hình này:

- destination là tên exchange có sẵn.
- group là tên queue có sẵn.
- bindQueue=false yêu cầu binder không tự bind queue vào exchange.
- declareExchange=false yêu cầu binder không tự khai báo exchange.
- queueNameGroupOnly=true dùng tên group làm queue name, thay vì ghép destination và group.

Queue cần được bind sẵn vào exchange với routing key đúng. Khi binder không tạo binding, thay đổi bindingRoutingKey trong ứng dụng không thể sửa topology đã quản lý thủ công.

## 11. Những lỗi định tuyến thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Consumer không nhận message | Producer key không khớp binding key | Xem exchange type, routing key và binding trên queue |
| Direct exchange không nhận message | Dùng binding key # nhưng producer gửi khóa khác # | Đặt bindingRoutingKey trùng routing key thực tế |
| Topic exchange nhận quá nhiều message | Binding key mặc định # | Thu hẹp binding key như orders.eu.# |
| Topic exchange không nhận message | Dùng sai số đoạn hoặc wildcard | Kiểm tra * chỉ khớp một đoạn, # khớp không hoặc nhiều đoạn |
| Fanout không phân phối | Queue chưa được bind vào exchange | Kiểm tra queue bindings; routing key không có tác dụng với fanout |
| Headers exchange không nhận message | Header thiếu/sai kiểu hoặc x-match không đúng | Kiểm tra message headers và queueBindingArguments |
| PRECONDITION_FAILED khi khởi động | Exchange cùng tên nhưng type hoặc thuộc tính declaration không khớp | So sánh topology broker với exchangeType, durability và auto-delete |
| Publish thành công nhưng không thấy queue nhận | Không có binding khớp hoặc queue không tồn tại | Kiểm tra publisher returns/alternate exchange và topology |
| Expression phát sinh lỗi | Payload/header null hoặc biểu thức SpEL sai | Ghi log metadata an toàn và kiểm tra input message |

Khi định tuyến không đúng, hãy kiểm tra theo thứ tự: destination/exchange, exchange type, queue, binding key hoặc binding arguments, routing key thực tế và message headers. Không chỉ thay routingKeyExpression mà bỏ qua binding của queue.

## 12. Kiểm thử routing trong ứng dụng

Nên kiểm tra cả cấu hình topology và hành vi message thực tế.

### 12.1. Kiểm thử biểu thức producer

Tạo các message với payload hoặc headers khác nhau và xác minh routing key được tạo đúng. Ví dụ:

| Payload | Routing key mong đợi |
|---|---|
| region=eu, eventType=created | eu.created |
| region=us, eventType=cancelled | us.cancelled |
| region=apac, eventType=updated | apac.updated |

Nếu expression sử dụng header, test cả trường hợp thiếu header để bảo đảm lỗi được phát hiện sớm.

### 12.2. Integration test với RabbitMQ

Chạy RabbitMQ bằng Testcontainers hoặc môi trường test riêng, sau đó:

1. Khởi động ứng dụng với Rabbit binder.
2. Xác minh exchange được tạo với đúng type.
3. Xác minh queue và binding key được tạo đúng.
4. Publish message với routing key khớp và không khớp.
5. Xác minh queue nhận đúng tập message dự kiến.
6. Với headers exchange, kiểm tra cả x-match=all và x-match=any.
7. Kiểm tra publisher returns hoặc alternate exchange khi message không được route.

Test Binder của Spring Cloud Stream có thể kiểm tra luồng function và binding ở mức ứng dụng, nhưng không thay thế integration test với RabbitMQ thật để xác minh thuật toán exchange, wildcard và queue binding.

## 13. Nguyên tắc lựa chọn exchange và routing

| Yêu cầu nghiệp vụ | Exchange type phù hợp | Cách định tuyến |
|---|---|---|
| Chỉ nhận đúng một loại sự kiện hoặc khóa cụ thể | direct | routingKey cố định và bindingRoutingKey trùng chính xác |
| Phân loại theo vùng, domain hoặc loại sự kiện phân cấp | topic | routingKeyExpression tạo key theo payload; binding dùng * và # |
| Broadcast đến mọi queue đăng ký | fanout | Tạo queue binding; routing key không quan trọng |
| Chọn queue dựa trên nhiều thuộc tính header | headers | queueBindingArguments và x-match |

Quy trình cấu hình:

1. Xác định message cần tới một queue hay nhiều queue.
2. Chọn exchange type theo quy tắc phân phối.
3. Chọn cấu trúc routing key nếu dùng direct hoặc topic.
4. Cấu hình routingKey cho khóa cố định hoặc routingKeyExpression cho khóa động.
5. Cấu hình bindingRoutingKey cho từng queue consumer.
6. Với headers exchange, định nghĩa header và queueBindingArguments ở hai phía.
7. Bảo đảm producer và consumer cùng thống nhất exchange type.
8. Kiểm tra queue/binding do binder tạo hoặc do đội nền tảng quản lý.
9. Chạy integration test để xác minh cả trường hợp khớp và không khớp.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): mô hình exchange, queue, group và cấu hình binder.
- [RabbitMQ Binder - Consumer Properties](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): exchangeType, bindingRoutingKey, bindingRoutingKeyDelimiter và queueBindingArguments.
- [RabbitMQ Binder - Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html): routingKeyExpression, routingKey và các thuộc tính producer.
- [RabbitMQ - Exchanges](https://www.rabbitmq.com/docs/exchanges): hành vi direct, topic, fanout, binding và exchange durability.
- [RabbitMQ - AMQP 0-9-1 Concepts](https://www.rabbitmq.com/tutorials/amqp-concepts): exchange types, headers exchange và cơ chế định tuyến.
