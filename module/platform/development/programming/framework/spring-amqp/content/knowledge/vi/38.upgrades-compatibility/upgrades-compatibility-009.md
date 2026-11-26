# Đánh giá module AMQP 1.0 mà không trộn cấu hình AMQP 0.9.1

Khi học tích hợp **RabbitMQ với Spring AMQP**, nhiều dự án bắt đầu bằng `RabbitTemplate`, `CachingConnectionFactory`, `@RabbitListener`, exchange, queue và binding theo giao thức **AMQP 0-9-1**. Sau đó nhóm phát triển nghe rằng RabbitMQ đã hỗ trợ **AMQP 1.0** và Spring có module mới. Một sai lầm dễ gặp là đổi dependency hoặc sửa vài property trong `application.yml` rồi mặc định rằng đây chỉ là phiên bản cao hơn của cùng giao thức.

Thực tế, **AMQP 1.0 không phải bản nâng cấp tương thích wire của AMQP 0-9-1**. Hai giao thức có mô hình kết nối, vận chuyển, điều tiết lưu lượng và xác nhận delivery khác nhau. RabbitMQ có thể làm cầu nối thông điệp giữa những client dùng hai giao thức, nhưng **API, cấu hình, kiểu connection factory, settlement và những tính năng được broker hỗ trợ không tự tương đương**.

Bài thuộc chương **Nâng cấp và tương thích** của module **SPRING_AMQP**. Mục tiêu là đánh giá khi nào cần thử AMQP 1.0, cách chọn đúng module Spring, thiết kế thử nghiệm không trộn cấu hình với AMQP 0-9-1, và bảo vệ chất lượng vận hành bằng publisher outcomes, consumer settlement, retry, dead-letter, idempotency và quan sát hệ thống.

> **Kết luận cốt lõi:** đánh giá **từng tổ hợp** `RabbitMQ server version × Spring Boot version × Spring AMQP version × Java client × queue type × nghiệp vụ`. Cùng cổng 5672, cùng annotation `@RabbitListener` hoặc cùng lớp `org.springframework.amqp.core.Message` **không có nghĩa** hai protocol stacks có thể hoán đổi cấu hình.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt căn bản giữa AMQP 1.0 và AMQP 0-9-1 ở **wire protocol**, mô hình gửi/nhận và xác nhận message.
2. Nhận diện các stack Java: `spring-rabbit` cho RabbitMQ AMQP 0-9-1, `spring-rabbitmq-client` cho RabbitMQ AMQP 1.0 và stack AMQP 1.0 **broker-agnostic** khi phiên bản Spring hỗ trợ.
3. Phân biệt `spring.rabbitmq.*`, `spring.amqp.rabbitmq.*` và `spring.amqp.*` theo đúng thế hệ Spring Boot/module.
4. Phân biệt `org.springframework.amqp.rabbit.connection.ConnectionFactory` với `org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory`, cùng các template/consumer tương ứng.
5. Hiểu địa chỉ AMQP 1.0 RabbitMQ **v2** cho exchange, routing key và queue; không lẫn với các mẫu địa chỉ v1 đã bị deprecate.
6. Đánh giá sự khác biệt giữa `basic.ack`/publisher confirms và AMQP 1.0 **settlement outcomes/flow control**.
7. Thiết lập thử nghiệm inter-protocol producer/consumer mà vẫn bảo vệ JSON contract, headers, ordering, DLQ và idempotency.
8. Xây compatibility matrix, quyết định migrate hay giữ nguyên, chiến lược canary/rollback và tiêu chí đo đạt trước production.

## 2. Hiểu đúng hai giao thức trước khi động vào dependency

### 2.1. AMQP 0-9-1 là gì?

Trong RabbitMQ AMQP 0-9-1 truyền thống:

- Producer gọi `basic.publish` tới một **exchange** với **routing key**.
- Exchange dùng **binding** để route message tới một hay nhiều **queue**.
- Consumer nhận `basic.deliver` và dùng `basic.ack`, `basic.nack`, `basic.reject` theo chính sách.
- `basic.qos`/prefetch giới hạn số delivery chưa ACK.
- `confirm.select`/publisher confirms cung cấp xác nhận phía broker đối với publish.
- Mỗi TCP connection có thể chứa nhiều **AMQP channels**.

Spring AMQP hiện thực luồng này bằng `RabbitTemplate`, `RabbitAdmin`, `CachingConnectionFactory` và `SimpleMessageListenerContainer`/`DirectMessageListenerContainer`.

### 2.2. AMQP 1.0 là gì?

AMQP 1.0 tiêu chuẩn hóa **mô hình truyền message giữa peers** bằng các thực thể như:

- **Connection**: kết nối protocol.
- **Session**: ngữ cảnh giao tiếp trên connection.
- **Link**: liên kết sender hoặc receiver gắn với source/target.
- **Source/target address**: địa chỉ nguồn/đích do broker triển khai cách diễn giải.
- **Flow/credit**: receiver cấp khả năng nhận delivery.
- **Transfer**: vận chuyển message.
- **Disposition/outcome/settlement**: trao đổi kết quả và hoàn tất delivery.

AMQP 1.0 không yêu cầu mọi broker thực thi cùng một mô hình exchange–queue–binding. **RabbitMQ vẫn có exchange, queue, binding** bên trong, và diễn giải các AMQP 1.0 addresses thành tài nguyên của RabbitMQ.

### 2.3. Không chỉ là khác tên method

| Hạng mục | AMQP 0-9-1 | AMQP 1.0 |
| --- | --- | --- |
| Wire protocol | AMQP 0-9-1 frames/methods | AMQP 1.0 frames/performatives |
| Khả năng nối trực tiếp | Cần client 0-9-1 | Cần client 1.0 |
| Mô hình gửi | `basic.publish(exchange,routingKey,properties,body)` | Sender link tới target/address, transfer message |
| Mô hình nhận | `basic.consume(queue)` qua channel | Receiver link từ source/address, credit |
| Xác nhận producer | Publisher confirms ACK/NACK; returns khi mandatory | Delivery outcome/settlement tương ứng; không dùng `basic.return` |
| Phản hồi consumer | ACK/NACK/REJECT trên channel | `accepted`/`rejected`/`released`/`modified` theo khả năng hỗ trợ |
| Điều tiết tải | Prefetch QoS, TCP backpressure | Link credit và flow control chi tiết |
| Metadata | Basic properties + headers | Header, properties, application-properties, annotations, body sections |
| Transaction protocol | 0-9-1 tx hạn chế | Đặc tả có transactions nhưng **RabbitMQ 1.0 hiện không hỗ trợ** |
| Quản lý topology | `queue.declare`/`exchange.declare`/`queue.bind` | RabbitMQ 1.0 management API hoặc provisioning độc lập |
| Spring phổ biến | `RabbitTemplate`, `RabbitAdmin` | `RabbitAmqpTemplate`, `RabbitAmqpAdmin` (module RabbitMQ-specific) |

**Ghi nhớ:** “đổi sang AMQP 1.0” không phải đổi `spring.rabbitmq.port` hay cast `RabbitTemplate` thành `RabbitAmqpTemplate`.

## 3. Kiểm tra phiên bản: broker, Java client, Spring AMQP và Boot

Khả năng chạy AMQP 1.0 phụ thuộc **cả bốn lớp**.

| Lớp | Điều kiện cần xác minh | Cảnh báo tương thích |
| --- | --- | --- |
| RabbitMQ broker | Phiên bản, feature flags, AMQP 1.0 support, auth, queue type | RabbitMQ **4.0+** tích hợp AMQP 1.0 **native**, không cần thêm plugin tương ứng |
| RabbitMQ 3.x cũ | Cơ chế hỗ trợ AMQP 1.0 qua plugin và giới hạn lịch sử | Không áp dụng mặc định địa chỉ, behavior và management của 4.x |
| RabbitMQ AMQP Java Client | `com.rabbitmq.client:amqp-client`, JDK, TLS/SASL, API | **Khác** `com.rabbitmq:amqp-client` truyền thống dùng cho 0-9-1 |
| Spring AMQP | Module và branch đang chạy | `spring-rabbitmq-client` xuất hiện từ **Spring AMQP 4.0** |
| Spring Boot | Dependency management và auto-configuration version | Boot 4.x có các AMQP styles/nhóm property riêng; Boot 3.x không tự có mọi auto-config mới |
| Hạ tầng | Cluster, vhost, auth, metrics, ingress/proxy | Cùng port không chứng minh proxy/healthcheck cho cả hai protocol |

RabbitMQ 4.x **vẫn hỗ trợ AMQP 0-9-1**. RabbitMQ khuyến nghị đánh giá AMQP 1.0 cho **ứng dụng mới**, nhưng đó không phải yêu cầu phải migrate tất cả producer/consumer 0-9-1 đang chạy tốt.

### 3.1. Vì sao không “thêm dependency 1.0” vào Spring Boot cũ rồi hy vọng tự chạy?

Giả sử ứng dụng đang dùng Spring Boot 3.x, Spring AMQP 3.x, `spring-boot-starter-amqp` và `RabbitTemplate`. Việc thêm một artifact AMQP 1.0 mới vào build **không tự tạo** `RabbitAmqpTemplate`, `RabbitAmqpListenerContainerFactory` và các bean/configuration mới nếu bộ Spring Boot hiện tại chưa hỗ trợ. Còn nếu ép nâng riêng Spring AMQP major version mà không nâng các thành phần tương thích, có thể gặp lỗi classpath/API hoặc auto-configuration.

Trước khi thử, xác minh **BOM/dependency tree** và bảng tương thích chính thức; chỉ chọn các version mà Spring Boot/Framework/JDK hỗ trợ cùng nhau. Không dùng một phiên bản được nêu trong tài liệu mới nhất như cách “copy nguyên” vào project cũ.

### 3.2. RabbitMQ 4.x có thể xử lý hai protocol trên cùng cổng

Trên RabbitMQ 4.0+, listener TCP mặc định thường ở **5672** có thể nhận cả hai protocol, tùy cấu hình. Sau TCP/TLS, client gửi **protocol header** để cho biết dùng AMQP 1.0 hay AMQP 0-9-1. Với AMQP 1.0, RabbitMQ yêu cầu SASL theo thiết kế của broker.

~~~mermaid
flowchart TD
    TCP["TCP/TLS đến RabbitMQ :5672"] --> H{"Protocol header"}
    H -->|"AMQP 0-9-1"| P0["0-9-1 Connection + Channel"]
    H -->|"AMQP 1.0 + SASL"| P1["1.0 Connection + Session + Links"]
    P0 --> R["RabbitMQ exchanges / queues / bindings"]
    P1 --> R
~~~

**Cùng host/port/credentials không có nghĩa cùng giao thức.** Cũng không phải cứ URI bắt đầu bằng `amqp://` thì hai client dùng chung một kiểu ConnectionFactory; phải kiểm tra **library thực thi**.

## 4. So sánh chính xác ba lựa chọn Spring khi đánh giá

Trong thế hệ Spring Boot 4.x có thể gặp **ba dòng tích hợp**:

| Lựa chọn | Trọng tâm | API/Dependency | Trường hợp phù hợp |
| --- | --- | --- | --- |
| RabbitMQ AMQP 0-9-1 | Tương thích hệ thống RabbitMQ hiện hữu | `spring-rabbit`, `RabbitTemplate`; Boot 4.x starter 0-9-1 riêng | Đã có nhiều listener, listener advice/retry, RabbitMQ plugin 0-9-1 |
| RabbitMQ AMQP 1.0 | Dùng RabbitMQ AMQP 1.0 native | `spring-rabbitmq-client`, `RabbitAmqpTemplate`, `RabbitAmqpListenerContainerFactory` | Thử tính năng 1.0 trên RabbitMQ, migration có kiểm soát |
| Generic AMQP 1.0 | Tích hợp broker hỗ trợ chuẩn AMQP 1.0 | `spring-amqp-client` dựa trên Qpid ProtonJ2, API `AmqpClient`/`@AmqpListener` theo branch hỗ trợ | Portability đa broker là yêu cầu chính |

**Không trộn lựa chọn thứ hai với thứ ba.** Cùng là AMQP 1.0 nhưng module RabbitMQ-specific dựa trên **RabbitMQ AMQP Java Client** và không cam kết chạy với broker AMQP 1.0 bất kỳ. Stack generic có API và đặc tính riêng, cần thử tính tương thích cho từng broker.

### 4.1. Phân biệt artifact theo tọa độ Maven

~~~xml
<!-- RabbitMQ AMQP 0-9-1 (Spring AMQP classic) -->
<dependency>
  <groupId>org.springframework.amqp</groupId>
  <artifactId>spring-rabbit</artifactId>
</dependency>

<!-- RabbitMQ AMQP 1.0: Spring AMQP 4.x -->
<dependency>
  <groupId>org.springframework.amqp</groupId>
  <artifactId>spring-rabbitmq-client</artifactId>
</dependency>

<!-- Generic AMQP 1.0: chỉ khi branch hỗ trợ -->
<dependency>
  <groupId>org.springframework.amqp</groupId>
  <artifactId>spring-amqp-client</artifactId>
</dependency>
~~~

Các snippet trên là **danh tính module**, không có nghĩa phải đưa cả ba dependency vào cùng ứng dụng. Phiên bản nên theo **BOM tương thích** thay vì hard-code đồng loạt khác branch. Một phần dependency `spring-rabbit` có thể xuất hiện transitively trong stack 1.0 để tái sử dụng API/annotation; **sự hiện diện trên classpath không chứng minh chương trình đang mở connection AMQP 0-9-1**.

### 4.2. Spring Boot starters thay đổi theo thế hệ

Theo tài liệu **Spring Boot 4.2**, lựa chọn starter được tách như sau:

~~~text
Generic AMQP 1.0      -> spring-boot-starter-amqp
RabbitMQ AMQP 1.0     -> spring-boot-starter-amqp-rabbitmq
RabbitMQ AMQP 0-9-1   -> spring-boot-starter-rabbitmq
~~~

Trong các ứng dụng **Spring Boot 3.x**, `spring-boot-starter-amqp` quen thuộc thường là **RabbitMQ AMQP 0-9-1**. Vì thế **tên starter giống nhau giữa hai major version có thể gây hiểu nhầm nghiêm trọng**.

> Kiểm tra chính xác Spring Boot version/BOM trong dự án trước khi áp dụng ví dụ starter. Đừng dùng tài liệu Boot 4.x để suy luận về bean/auto-config của Boot 3.x.

## 5. Cách đặt cấu hình: ba namespace không hoán đổi

Đây là một trong những bước kiểm tra quan trọng nhất trong bài.

### 5.1. RabbitMQ AMQP 0-9-1

~~~yaml
# Ví dụ cho stack Spring Boot RabbitMQ AMQP 0-9-1.
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    virtual-host: /orders
    username: ${RABBITMQ_091_USERNAME}
    password: ${RABBITMQ_091_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 4
        prefetch: 20
~~~

`spring.rabbitmq.*` phục vụ auto-config kiểu **0-9-1** khi stack tương ứng được bật. Thuộc tính `publisher-confirm-type`, `publisher-returns`, `listener.simple.prefetch` mang semantics 0-9-1.

### 5.2. RabbitMQ AMQP 1.0 dedicated module

~~~yaml
# Ví dụ cho Spring Boot 4.x với RabbitMQ AMQP 1.0 starter.
spring:
  amqp:
    rabbitmq:
      host: rabbitmq.internal
      port: 5672
      username: ${RABBITMQ_10_USERNAME}
      password: ${RABBITMQ_10_PASSWORD}
      template:
        exchange: orders.events.exchange
        routing-key: order.created
        default-receive-queue: orders.events.queue
~~~

`spring.amqp.rabbitmq.*` dành cho cấu hình **RabbitMQ AMQP 1.0 dedicated stack** ở Spring Boot có hỗ trợ. Không bê `spring.rabbitmq.publisher-confirm-type` hay `spring.rabbitmq.listener.simple.*` sang đây và cho rằng chúng có cùng hiệu lực. Nếu dùng TLS ở Boot version hỗ trợ, kiểm tra `spring.amqp.rabbitmq.ssl.bundle` theo tài liệu cụ thể.

### 5.3. Generic AMQP 1.0 — namespace khác nữa

~~~yaml
# Ví dụ cho generic AMQP 1.0 auto-configuration ở Boot 4.x.
spring:
  amqp:
    host: generic-broker.internal
    port: 5672
    username: ${GENERIC_AMQP_USERNAME}
    password: ${GENERIC_AMQP_PASSWORD}
    client:
      default-to-address: /queues/processing
      completion-timeout: 500ms
~~~

`spring.amqp.*` ở ví dụ trên **không phải** tên viết tắt của `spring.amqp.rabbitmq.*`. Cùng một broker có thể có nhiều stacks trong ứng dụng, nhưng cần **thiết kế bean, listener, configuration owners và dependency rõ ràng**; không dựa vào “binding magic” của những property tương tự tên.

### 5.4. Bảng xác minh cấu hình

| Vấn đề | 0-9-1 | RabbitMQ 1.0 | Generic 1.0 |
| --- | --- | --- | --- |
| Connection properties | `spring.rabbitmq.*` | `spring.amqp.rabbitmq.*` | `spring.amqp.*` |
| Template | `RabbitTemplate` | `RabbitAmqpTemplate` | `AmqpClient` |
| Listener annotation | `@RabbitListener` | `@RabbitListener` với factory 1.0 | `@AmqpListener` |
| Connection factory | `rabbit.connection.ConnectionFactory` | `rabbitmq.client.AmqpConnectionFactory` | Factory của generic client |
| Listener factory | `SimpleRabbitListenerContainerFactory` hoặc direct | `RabbitAmqpListenerContainerFactory` | `MethodAmqpMessageListenerContainerFactory` |
| Publish confirmation | Correlated publisher confirms | Future/outcomes của 1.0 client | API completion/outcome tương ứng |
| Prefetch/credit | `prefetch`/QoS | Receiver credit | API link credit của generic client |

Từ “cùng annotation” chỉ là tầng API tái sử dụng; **bean factory cụ thể** mới quyết định protocol đang dùng.

## 6. Địa chỉ RabbitMQ AMQP 1.0: v2 khác v1 và khác `basic.publish`

Đặc tả AMQP 1.0 **không bắt buộc** một address phải đại diện exchange hay queue. RabbitMQ quy định cách diễn giải address để map vào mô hình exchange/queue/binding của chính nó.

Từ RabbitMQ 4.0, **address format v2** được khuyến nghị. Những chuỗi v1 như `/exchange/...` hoặc `/queue/...` là legacy/deprecated và có thể không còn được hỗ trợ trong phiên bản tương lai.

### 6.1. Target address v2

| Địa chỉ AMQP 1.0 trên RabbitMQ | Ý nghĩa |
| --- | --- |
| `/exchanges/orders.events.exchange/order.created` | Publish vào exchange với routing key |
| `/exchanges/audit.fanout` | Publish vào exchange với routing key rỗng |
| `/queues/orders.events.queue` | Publish trực tiếp tới queue qua default exchange |
| `null target` + `message.to` | Cho phép chọn địa chỉ cho từng message trên cùng link theo chuẩn hỗ trợ |

Địa chỉ `/queues/myqueue` **yêu cầu queue tồn tại** và trong RabbitMQ cần permission phù hợp với default exchange `amq.default` cho thao tác gửi. Đừng mặc định format v2 sẽ âm thầm khai báo queue mới như một số format v1 trước đây.

### 6.2. Source address v2

Đọc message từ queue:

~~~text
/queues/orders.events.queue
~~~

Đây là **source của receiver link**, không phải địa chỉ publish tùy ý. Với RabbitMQ, ứng dụng vẫn cần khai báo/bảo đảm tồn tại exchange, queue và binding trước khi consume.

### 6.3. Phải percent-encode thành phần đặc biệt

Nếu routing key chứa dấu `/`, không nối thẳng:

~~~text
# Sai: dấu / làm phân tách các segment.
 /exchanges/amq.direct/orders/created

# Đúng: slash nằm bên trong routing key, được encode.
 /exchanges/amq.direct/orders%2Fcreated
~~~

Theo format v2, exchange names, queue names và routing keys trong address phải được **percent-encode theo RFC 3986**. Với tên đơn giản như `order.created`, không cần escape thêm.

Khi dùng `RabbitAmqpTemplate` với overload nhận exchange/routing key, hãy để library tạo address nếu API hỗ trợ thay vì tự lắp chuỗi một cách mơ hồ.

## 7. Mô hình settlement: không bê `basic.ack` sang AMQP 1.0

### 7.1. AMQP 0-9-1: ACK gắn với channel delivery

Một listener 0-9-1 chạy manual ACK có thể dùng `Channel.basicAck(deliveryTag,false)` sau DB commit. Delivery tag có phạm vi channel, không phải ID nghiệp vụ.

Nếu channel chết sau DB commit trước ACK, broker có thể redeliver. Consumer phải có idempotency.

### 7.2. AMQP 1.0: sender/receiver settlement và outcomes

AMQP 1.0 sử dụng **settlement** trên delivery. Những kết quả đáng chú ý gồm:

- `accepted`: phía nhận chấp nhận delivery theo semantics của link/broker.
- `rejected`: phía nhận từ chối, có thể mang thông tin lỗi.
- `released`: giao trả/release message theo semantics broker.
- `modified`: mô tả trạng thái thay đổi, một số trường hợp dùng với requeue/dead-letter; **tùy queue type và hỗ trợ của RabbitMQ**.

`Sender settle mode`/`receiver settle mode` và cách client báo kết quả cần được hiểu trên **RabbitMQ AMQP Java Client** đang dùng. Không ép kết quả 1.0 thành đúng hai nút `basic.ack` / `basic.nack`.

### 7.3. Kết quả publish khác consumer business commit

~~~mermaid
sequenceDiagram
    participant P as Sender / AMQP 1.0
    participant B as RabbitMQ
    participant C as Receiver / AMQP 1.0
    participant DB as Business DB
    P->>B: Transfer event E42
    B-->>P: Disposition/outcome
    B->>C: Transfer E42
    C->>DB: Commit effect + inbox(E42)
    C-->>B: Settle accepted
~~~

**Publisher outcome** cho biết kết quả chặng sender–broker theo semantics. **Receiver accepted/settled** là kết quả chặng broker–consumer. Không kết quả nào đơn độc chứng minh tất cả tác dụng nghiệp vụ bên ngoài đã đúng.

Nếu producer mất outcome trước khi nhận, có thể phải retry cùng `eventId`. Nếu consumer commit trước khi settle rồi mất connection, có thể nhận lại. Những cửa sổ này vẫn cần outbox và idempotency — **thay protocol không tạo exactly-once business effects**.

## 8. Credit flow control khác prefetch QoS

AMQP 0-9-1 RabbitMQ có `basic.qos`/prefetch để điều tiết delivery chưa ACK. Với AMQP 1.0, receiver điều khiển lượng delivery có thể nhận bằng **link credit**, broker có khả năng cung cấp flow control chi tiết.

Điểm thực hành:

1. **Đừng** cấu hình `spring.rabbitmq.listener.simple.prefetch=20` rồi cho rằng nó điều tiết `RabbitAmqpListenerContainer`.
2. Kiểm tra tùy chọn flow/batch/concurrency của listener factory **AMQP 1.0** trong phiên bản cụ thể.
3. Đo **message outstanding, effective credit, handler processing rate, queue ready/age và memory**, không chỉ số consumer.
4. Với downstream API bị throttling, credit không thay thế bulkhead/rate limiter và retry backoff.
5. Khi thay queue type (classic/quorum/stream), kiểm tra semantics delivery và các tính năng 1.0 hỗ trợ.

RabbitMQ 1.0 hỗ trợ flow control phong phú hơn, nhưng **đừng coi mọi API trong tài liệu 0-9-1 có tên tương tự là cùng một “knob”**. Việc tăng credit quá mức có thể làm nhiều delivery bị giữ ở client, giống rủi ro prefetch quá lớn.

## 9. Chọn một đường đi thử nghiệm, không thay toàn bộ stack cùng lúc

Trước khi viết code mới, nhóm phát triển nên chọn **một phạm vi canary nhỏ**: một producer 1.0 gửi vào exchange thử, một consumer 1.0 đọc queue thử, hoặc một chiều giao tiếp cross-protocol. Không chuyển toàn bộ producer và consumer đang chạy production trong một lần triển khai.

### 9.1. Ma trận cần ghi lại

| Hạng mục | Thông tin phải xác nhận |
| --- | --- |
| Broker | RabbitMQ version, enabled features, node/cluster, vhost |
| Client | RabbitMQ AMQP Java Client version, JDK và TLS/SASL |
| Spring | Spring Boot, Spring Framework, Spring AMQP BOM/module |
| Stack | 0-9-1, RabbitMQ-dedicated 1.0 hay generic 1.0 |
| Topology | Exchanges, queues, bindings, routing keys, DLX và queue type |
| Message | JSON schema, eventId, content type, headers, ordering |
| Reliability | Publisher outcomes, consumer settlement, retry/DLQ, outbox/inbox |
| Performance | Goodput, p95/p99, credit/prefetch, memory/queue age |
| Rollback | Cách tắt canary, ngăn replay trùng và khôi phục stack cũ |

Một test connect thành công **chưa chứng minh** routing, schema, settlement hoặc business commit tương thích.

## 10. Bean graph: tách ConnectionFactory, template và listener factory

| Vai trò | AMQP 0-9-1 | RabbitMQ AMQP 1.0 |
| --- | --- | --- |
| Connection factory | `org.springframework.amqp.rabbit.connection.ConnectionFactory` | `org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory` |
| Implementation | `CachingConnectionFactory` | `SingleAmqpConnectionFactory` + `Environment` |
| Publisher | `RabbitTemplate` | `RabbitAmqpTemplate` |
| Admin | `RabbitAdmin` | `RabbitAmqpAdmin` |
| Listener container | `SimpleMessageListenerContainer`/`DirectMessageListenerContainer` | `RabbitAmqpListenerContainer` |
| Listener factory | `SimpleRabbitListenerContainerFactory` | `RabbitAmqpListenerContainerFactory` |
| Annotation | `@RabbitListener` | `@RabbitListener` với factory 1.0 |
| Publish results | `CorrelationData`/publisher confirm/return | `CompletableFuture`/outcomes |
| Connection lifetime | AMQP channel/cache semantics | AMQP sessions/links và Environment |

Mặc dù một số Spring interfaces, message classes và annotation được **tái sử dụng** giữa hai module, **loại factory** mới thực sự quyết định giao thức.

~~~mermaid
flowchart LR
  subgraph L["0-9-1"]
    CF0["CachingConnectionFactory"] --> T0["RabbitTemplate"]
    CF0 --> F0["SimpleRabbitListenerContainerFactory"]
    CF0 --> A0["RabbitAdmin"]
  end
  subgraph N["1.0 RabbitMQ"]
    ENV["AMQP Environment"] --> CF1["SingleAmqpConnectionFactory"]
    CF1 --> T1["RabbitAmqpTemplate"]
    CF1 --> F1["RabbitAmqpListenerContainerFactory"]
    CF1 --> A1["RabbitAmqpAdmin"]
  end
  T0 --> BROKER["RabbitMQ exchange / queue / binding"]
  F0 --> BROKER
  T1 --> BROKER
  F1 --> BROKER
~~~

### 10.1. Nguy cơ khi cả hai module nằm trong classpath

- `spring-rabbit` có thể là **transitive dependency** của module 1.0 để tái sử dụng annotation và model; classpath có lớp 0-9-1 **không có nghĩa** runtime gửi theo 0-9-1.
- `@RabbitListener` không tự chọn protocol dựa trên queue name. Factory của listener phải đúng.
- Hai `AmqpAdmin` implementation có thể cùng cố khai báo exchange/queue với arguments khác nhau.
- Một Bean `MessageConverter` dùng chung có thể encode JSON khác hợp đồng nếu thiếu kiểm tra.
- Cùng một work queue nếu bị hai nhóm consumers đọc trong canary sẽ có **competing consumers**; đó không phải broadcast mirroring.
- Nếu có hai `RabbitTemplate` hoặc Spring abstraction tương tự, không nên rely vào Bean name/default injection không rõ.

**Khuyến nghị thử nghiệm:** đặt canary AMQP 1.0 trong **deployment riêng**. Khi thật sự cần dùng chung JVM, chỉ định rõ Bean name, `@Qualifier`, `containerFactory` và topology ownership; có integration test kiểm đếm consumers.

## 11. Ví dụ AMQP 0-9-1: xác định công cụ đang dùng

Trong legacy Spring AMQP:

~~~java
package com.example.protocols.legacy;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Rabbit091Configuration {

    @Bean("rabbit091ConnectionFactory")
    CachingConnectionFactory rabbit091ConnectionFactory() {
        var factory = new CachingConnectionFactory("rabbitmq.internal");
        factory.setPort(5672);
        factory.setVirtualHost("/orders");
        // Bổ sung username/password/TLS từ secret store.
        return factory;
    }

    @Bean("rabbit091Template")
    RabbitTemplate rabbit091Template(
            CachingConnectionFactory rabbit091ConnectionFactory) {
        return new RabbitTemplate(rabbit091ConnectionFactory);
    }

    @Bean("rabbit091ListenerFactory")
    SimpleRabbitListenerContainerFactory rabbit091ListenerFactory(
            CachingConnectionFactory rabbit091ConnectionFactory) {
        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(rabbit091ConnectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setPrefetchCount(20);
        factory.setConcurrentConsumers(2);
        return factory;
    }
}
~~~

Đây là ví dụ **nhận diện Bean**, chưa phải cấu hình production (credentials, JSON converter, confirms/returns, retry, monitoring cần bổ sung). Khi sử dụng auto-configuration Spring Boot cho 0-9-1, không cần tự khai báo lại nếu Bean mặc định đáp ứng đúng nhu cầu.

Listener gắn đích danh factory:

~~~java
@RabbitListener(
        queues = "orders.legacy.queue",
        containerFactory = "rabbit091ListenerFactory")
public void onEvent(String text) {
    legacyService.handle(text);
}
~~~

Đừng đưa listener này cùng lúc lên queue canary 1.0 rồi hy vọng broker phân phối **mỗi message cho cả hai**. Nếu hai consumer cùng queue, mỗi delivery thông thường đi tới **một** consumer.

## 12. Ví dụ RabbitMQ AMQP 1.0 trong Spring AMQP 4.x

Spring AMQP 4.x `spring-rabbitmq-client` dựa trên `com.rabbitmq.client:amqp-client` và có `RabbitAmqpTemplate`, `RabbitAmqpAdmin` cùng `RabbitAmqpListenerContainerFactory`.

### 12.1. Bean riêng cho protocol 1.0

~~~java
package com.example.protocols.amqp10;

import com.rabbitmq.client.amqp.Environment;
import org.springframework.amqp.rabbitmq.client.AmqpConnectionFactory;
import org.springframework.amqp.rabbitmq.client.SingleAmqpConnectionFactory;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpAdmin;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpTemplate;
import org.springframework.amqp.rabbitmq.client.config.RabbitAmqpListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Rabbit10Configuration {

    @Bean("rabbit10ConnectionFactory")
    AmqpConnectionFactory rabbit10ConnectionFactory(
            Environment environment) {
        return new SingleAmqpConnectionFactory(environment);
    }

    @Bean("rabbit10Template")
    RabbitAmqpTemplate rabbit10Template(
            AmqpConnectionFactory rabbit10ConnectionFactory) {
        var template = new RabbitAmqpTemplate(rabbit10ConnectionFactory);
        template.setExchange("orders.events.exchange");
        template.setRoutingKey("order.created");
        return template;
    }

    @Bean("rabbit10Admin")
    RabbitAmqpAdmin rabbit10Admin(
            AmqpConnectionFactory rabbit10ConnectionFactory) {
        return new RabbitAmqpAdmin(rabbit10ConnectionFactory);
    }

    @Bean("rabbit10ListenerFactory")
    RabbitAmqpListenerContainerFactory rabbit10ListenerFactory(
            AmqpConnectionFactory rabbit10ConnectionFactory) {
        return new RabbitAmqpListenerContainerFactory(
                rabbit10ConnectionFactory);
    }
}
~~~

**Bối cảnh:** `Environment` phải được cung cấp bởi Spring Boot 4.x auto-configuration hoặc một Bean 1.0 chuyên biệt với credentials/TLS/vhost đúng. Đừng thêm những Bean này trùng với Bean tự động của Boot nếu không có mục đích cụ thể. Như mọi code phụ thuộc framework major version, cần compile/test trên tổ hợp đã khóa bằng BOM.

### 12.2. Publisher 1.0 dùng future, không phải `CorrelationData`

~~~java
package com.example.protocols.amqp10;

import java.util.concurrent.TimeUnit;
import org.springframework.amqp.rabbitmq.client.RabbitAmqpTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class Rabbit10SmokePublisher {

    private final RabbitAmqpTemplate template;

    public Rabbit10SmokePublisher(
            @Qualifier("rabbit10Template") RabbitAmqpTemplate template) {
        this.template = template;
    }

    public void sendText(String value) {
        template.convertAndSend(value)
                .orTimeout(10, TimeUnit.SECONDS)
                .join();
    }
}
~~~

Đây là **smoke test String** để thử publish. `RabbitAmqpTemplate` mặc định sử dụng `SimpleMessageConverter` nếu không cấu hình converter khác; với DTO JSON cần message converter và schema test riêng. Future timeout có thể là kết quả **chưa rõ** — không khẳng định broker chắc chắn chưa nhận.

### 12.3. Listener 1.0 vẫn có thể dùng `@RabbitListener`

~~~java
package com.example.protocols.amqp10;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class Rabbit10SmokeListener {

    @RabbitListener(
            queues = "orders.canary.queue",
            containerFactory = "rabbit10ListenerFactory")
    public void onEvent(String value) {
        // Chỉ dùng queue test độc lập để kiểm chứng 1.0.
    }
}
~~~

`containerFactory="rabbit10ListenerFactory"` là điểm xác định stack; nếu cùng annotation nhưng dùng factory 0-9-1, listener không tự chuyển sang 1.0.

### 12.4. Boot 4.x auto-configuration so với cấu hình thủ công

Nếu đã dùng `spring-boot-starter-amqp-rabbitmq` đúng thế hệ Boot, ứng dụng có thể nhận `RabbitAmqpTemplate`/`RabbitAmqpAdmin` và default listener factory từ auto-config. Nên **chọn một mô hình**:

- Dùng Boot auto-config, customize ở các hook được hỗ trợ.
- Hoặc tự khai báo đầy đủ Bean, lifecycle, credentials và owner.

Không chỉ thêm một `RabbitAmqpTemplate` custom rồi mặc định mọi property Boot sẽ tự động đi qua Bean do mình tự tạo. Cần kiểm tra đúng runtime bean và context startup.

## 13. Tách cấu hình bằng deployment/profile, không “bật cả hai cho chắc”

Một chiến lược an toàn cho giai đoạn đầu:

~~~text
orders-consumer-091
  stack       = Spring RabbitMQ AMQP 0-9-1
  property    = spring.rabbitmq.*
  producer    = RabbitTemplate
  listener    = rabbit091ListenerFactory
  queue       = orders.legacy.queue

orders-consumer-10-canary
  stack       = Spring RabbitMQ AMQP 1.0
  property    = spring.amqp.rabbitmq.*
  producer    = RabbitAmqpTemplate
  listener    = rabbit10ListenerFactory
  queue       = orders.canary.queue
~~~

Mỗi deployment có **dependency và Bean graph riêng** sẽ dễ chẩn đoán hơn một JVM chứa cả hai trong giai đoạn thử nghiệm.

### 13.1. Nếu bắt buộc chạy cả hai trong cùng JVM

Hãy đặt luật:

1. Mỗi stack có connection factory và template được đặt tên rõ ràng.
2. `@RabbitListener(containerFactory = "...")` luôn chỉ định đúng factory.
3. Không để hai Admin beans tự khai báo cùng một queue với arguments khác nhau.
4. Chỉ cấu hình một owner cho các Bean `Exchange`/`Queue`/`Binding` nếu dùng chung topology.
5. Dùng `@Qualifier` hoặc inject theo concrete type, không dựa vào tên biến tình cờ.
6. Sử dụng `@Profile` hoặc feature flags để điều khiển listener startup có kiểm soát.
7. Đặt metric/log label `protocol=amqp091` hoặc `protocol=amqp10`.
8. Integration test xác minh số consumers trên từng queue và behavior khi shutdown/restart.

Dù cùng Java process, **đừng trộn** `spring.rabbitmq.listener.simple.prefetch` với listener factory 1.0. Namespace vẫn thuộc về stack tương ứng.

## 14. Inter-protocol messaging: RabbitMQ làm trung gian chuyển đổi

RabbitMQ có khả năng nhận một message qua AMQP 1.0 rồi giao cho consumer AMQP 0-9-1, hoặc ngược lại. Broker thực hiện **property conversion** khi cần; khi sender và receiver cùng dùng AMQP 1.0, broker có thể giữ định dạng message 1.0 nguyên bản theo queue type.

~~~mermaid
sequenceDiagram
    participant P as AMQP 1.0 Sender
    participant B as RabbitMQ
    participant C as AMQP 0-9-1 Consumer
    participant D as Business DB

    P->>B: Transfer E42, 1.0 properties
    B->>B: Store / protocol conversion
    B->>C: basic.deliver E42
    C->>D: Commit business + inbox(E42)
    C-->>B: basic.ack
~~~

**Khả năng truyền qua hai protocol không đảm bảo mọi metadata giữ nguyên tuyệt đối.** AMQP 0-9-1 basic properties/headers và AMQP 1.0 properties/application-properties/annotations khác nhau. Broker có các quy tắc chuyển đổi; một số kiểu dữ liệu và trường header có thể không có ánh xạ 1:1.

### 14.1. Ma trận hợp đồng message hai chiều

| Trường | Trong 0-9-1 | Trong 1.0 | Cần kiểm tra |
| --- | --- | --- | --- |
| Message ID | `messageId` | `message-id` | Kiểu UUID/string và semantic có ổn định? |
| Correlation | `correlationId` | `correlation-id` | Producer/consumer có hiểu cùng định dạng? |
| Reply destination | `replyTo` | `reply-to` address | Địa chỉ có hợp lệ theo broker version? |
| Media type | `contentType` | `content-type` | Có còn `application/json` không? |
| Header mở rộng | AMQP table | Application properties/annotations | Type và names được chuyển thế nào? |
| Routing context | Exchange/routing key | Target address hoặc message.to | Có vào đúng exchange/queue? |
| Durability | Delivery mode/persistent | Durable header/queue semantics | Có giữ đúng bảo đảm sau crash? |
| TTL/expiration | Message properties/policies | TTL fields và broker-specific policies | Deadline có bị đổi? |
| Dead-letter history | `x-death` headers | Metadata broker sau chuyển đổi | DLQ có thông tin điều tra đủ không? |
| Body | Bytes | Body section (data/value/sequence) | JSON object/string/binary có giữ đúng? |

Để chống phụ thuộc quá mức vào transport metadata, giữ **`eventId`, `eventType`, `schemaVersion` trong body envelope** nếu phù hợp nghiệp vụ. Không coi delivery tag, native message ID representation hay link ID là event ID duy nhất.

### 14.2. Hai bài thử đều cần thiết

- `0-9-1 producer → 1.0 consumer`.
- `1.0 producer → 0-9-1 consumer`.

Kiểm tra cả **body bytes, content type, JSON shape, ID và business commit**. Một message được broker ACK/settle nhưng consumer không deserialize đúng vẫn là thất bại.

## 15. Publisher confirms 0-9-1 không đồng nghĩa delivery outcomes 1.0

Một producer 0-9-1 có thể cấu hình:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

`CorrelationData` và publisher callbacks giúp quản lý confirm ACK/NACK; `mandatory` và returns hỗ trợ phát hiện unroutable message trong mô hình tương ứng.

Đối với RabbitMQ AMQP 1.0, **sender nhận delivery outcomes/settlement**. Với target address v2 của RabbitMQ, nếu message không được route tới queue vì thiếu binding, broker có thể settle với **`released`**. `RabbitAmqpTemplate` đưa kết quả qua `CompletableFuture` và native client có callback/status riêng.

**Không** sao chép `publisher-confirm-type`, `publisher-returns` và `mandatory` sang `spring.amqp.rabbitmq.*` rồi cho rằng behavior 1.0 sẽ tương đương.

### 15.1. Danh sách xác minh cho publisher 1.0

1. Target address hoặc template exchange/routing key đúng.
2. Exchange tồn tại, binding phù hợp, vhost/permissions đúng.
3. Future/outcome được xử lý — không bỏ qua async failure.
4. Unroutable/released được phân biệt với accepted.
5. Message có `eventId` và source outbox bền vững.
6. Timeout/disconnect trước outcome là **trạng thái chưa chắc chắn**, không mặc định chưa publish.
7. Retry với cùng ID, consumer có idempotency.
8. Dashboard thể hiện publisher acceptance, errors và outbox pending.

### 15.2. Không để API business hiểu nhầm mức bảo đảm

Có thể che chi tiết protocol sau interface ứng dụng:

~~~java
package com.example.messaging.api;

import java.util.concurrent.CompletionStage;

public interface EventPublisher {

    CompletionStage<Void> publish(EventEnvelope event);
}
~~~

Interface chỉ là **hợp đồng nội bộ**. Implementation 0-9-1 phải thực sự đợi confirm và xử lý returns; implementation 1.0 phải diễn giải delivery outcomes đúng. Không chuyển “đã gọi method gửi” thành “đã được broker xác nhận”, và không đánh đồng “broker accepted” với “consumer DB committed”.

## 16. Consumer settlement, retry và DLQ trong AMQP 1.0

AMQP 0-9-1 có `basic.ack`/`basic.nack`/`basic.reject`. Trong AMQP 1.0, message được **settle** với các outcomes. Spring AMQP 4.x dedicated module có `RabbitAmqpListenerContainer`; cấu hình `autoSettle=false` hỗ trợ manual settlement thông qua `AmqpAcknowledgment` hoặc native `Consumer.Context` khi sử dụng contract tương ứng.

### 16.1. Ví dụ listener 1.0 manual settle sau commit

~~~java
package com.example.protocols.amqp10;

import org.springframework.amqp.core.AmqpAcknowledgment;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersCanaryListener {

    private final OrdersCanaryService service;

    public OrdersCanaryListener(OrdersCanaryService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = "orders.canary.queue",
            containerFactory = "rabbit10ListenerFactory",
            ackMode = "#{T(org.springframework.amqp.core.AcknowledgeMode).MANUAL}")
    public void onEvent(String payload,
            AmqpAcknowledgment acknowledgment) {

        service.applyOnce(payload);
        // Business DB transaction phải commit trước khi settle.
        acknowledgment.acknowledge();
    }
}
~~~

`OrdersCanaryService` là service ví dụ cần triển khai. Đoạn này minh họa **manual settlement** trên RabbitMQ AMQP 1.0 theo API Spring AMQP 4.x. Nếu service ném exception, phải có error path và policy settle/requeue/discard được kiểm chứng để delivery không bị kẹt.

### 16.2. Ma trận outcome và ý định nghiệp vụ

| Điều kiện | Ý định | Cách xác minh |
| --- | --- | --- |
| Event hợp lệ, transaction commit | Accepted/settled | Không còn message outstanding, DB có marker |
| DB lỗi transient | Retry với backoff | Không gây requeue storm |
| Payload sai schema permanent | Reject/discard tới DLQ/quarantine | Message lỗi còn để triage |
| Message đã commit trước đó | Bỏ qua side effect, settle success | Inbox unique constraint chặn trùng |
| Mất connection sau DB commit trước settlement | Chịu redelivery | Cùng eventId không áp dụng effect lần hai |
| Quorum queue yêu cầu modified outcome | Kiểm tra broker/queue type hỗ trợ | Không áp dụng assumption của classic/stream |

Không mặc định `modified` có cùng tác dụng ở mọi loại queue: RabbitMQ hỗ trợ thay đổi message annotations trong một số trường hợp của **quorum queue**, không giống classic queue và stream.

### 16.3. DLX và retry topology vẫn phải kiểm thử

AMQP 1.0 sender/receiver có thể dùng queue, DLX và binding hiện có của RabbitMQ, nhưng **đường từ exception đến broker outcome** khác listener 0-9-1. Cần thử:

- Exception ở method listener có được settle/requeue/discard theo policy không?
- Permanent poison có đi vào terminal DLQ không?
- Header/annotations dead-letter sau cross-protocol conversion còn hữu ích không?
- Retry count/delivery limit đúng queue type/version không?
- Có vòng requeue vô hạn khi downstream lỗi không?
- Replay từ DLQ giữ `eventId` và idempotency không?

**Thay protocol không được làm thay đổi semantics xử lý lỗi một cách âm thầm.**

## 17. Transactions: tránh giả định “1.0 mạnh hơn 0-9-1 ở mọi tính năng”

AMQP 1.0 **đặc tả** các thành phần liên quan transaction, nhưng **RabbitMQ AMQP 1.0 implementation hiện không hỗ trợ transactions** theo tài liệu RabbitMQ 4.x. RabbitMQ 0-9-1 có hỗ trợ transaction ở phạm vi giao thức/broker, dù các giao dịch này không biến DB và RabbitMQ thành một global transaction.

Vì vậy:

- Đừng bê `channelTransacted=true` hay `RabbitTemplate` transaction configuration của 0-9-1 sang `RabbitAmqpTemplate` và chờ tương đương.
- Đừng coi AMQP 1.0 có transaction như một bảo đảm exactly-once.
- Không triển khai workload phụ thuộc 0-9-1 transactions trên 1.0 trước khi xác nhận giải pháp thay thế.
- Với event source trong DB, dùng **transactional outbox** để giảm cửa sổ DB commit rồi chưa publish.
- Với consumer, lưu **inbox marker và side effect trong cùng DB transaction** rồi settle/ACK sau commit.
- Với tác dụng ngoài DB (payment, email), dùng idempotency key, trạng thái bền vững và reconciliation.

### 17.1. Vì sao outbox vẫn cần?

~~~mermaid
sequenceDiagram
    participant DB as Database nguồn
    participant P as Outbox relay (1.0)
    participant R as RabbitMQ
    participant C as Consumer (1.0 hoặc 0-9-1)
    participant D as Database đích

    DB->>DB: Commit OrderPaid + outbox(E42)
    P->>R: Publish E42
    R-->>P: Delivery outcome
    R->>C: Deliver E42
    C->>D: Commit effect + inbox(E42)
    C-->>R: Settle/ACK
~~~

Có thể crash giữa bất kỳ cặp hành động nào. Outbox và idempotency **không biến toàn hệ thống thành một transaction duy nhất**, nhưng giúp giữ dữ liệu để replay an toàn và giảm mất/nhân đôi side effects.

## 18. Topology management: ai tạo exchange, queue và binding?

Trên 0-9-1, `RabbitAdmin` thường khai báo các Bean `Exchange`, `Queue`, `Binding`. Trên RabbitMQ 1.0 dedicated module, `RabbitAmqpAdmin` hiện thực interface `AmqpAdmin`, dùng native management API của connection 1.0.

### 18.1. Giữ một nguồn cấu hình topology

Có thể chọn một trong hai đường:

1. **Infrastructure/IaC provision** vhosts, permissions, queues, exchanges, bindings, policies và DLX.
2. **Ứng dụng sở hữu declarables**, nhưng có một Admin được chỉ định rõ, versioned configuration và migration plan.

Không để hai Admin cùng cố khai báo queue với **type, TTL, DLX hoặc durability khác nhau**. Một queue đang tồn tại không thể đổi classic thành quorum chỉ bằng cách redeclare một Bean.

### 18.2. Code Spring topology có thể tái sử dụng có điều kiện

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;

@Bean
DirectExchange ordersExchange() {
    return new DirectExchange("orders.events.exchange", true, false);
}

@Bean
Queue ordersQueue() {
    return QueueBuilder.durable("orders.canary.queue").build();
}

@Bean
Binding ordersBinding() {
    return BindingBuilder.bind(ordersQueue())
            .to(ordersExchange())
            .with("order.created");
}
~~~

Các Bean `Exchange`/`Queue`/`Binding` là **Spring AMQP core abstractions** có thể được các Admin tương ứng sử dụng; chính **admin implementation** xác định protocol dùng để quản trị broker. Phải kiểm tra initialization, resource recovery và quyền configure trong stack được chọn.

### 18.3. Nếu RabbitMQ 1.0 address v2 yêu cầu queue sẵn có

Địa chỉ source `/queues/orders.canary.queue` yêu cầu queue tồn tại. Không coi “attach receiver link” là một lời hứa broker sẽ tự tạo queue như một vài address format v1 cũ. Hãy provision topology rõ ràng trước khi listener bắt đầu; kiểm tra negative path khi queue thiếu.
## 19. JSON converter và schema: Spring abstractions được reuse nhưng wire vẫn khác

`RabbitAmqpTemplate` của Spring AMQP dedicated 1.0 có thể dùng những abstraction `org.springframework.amqp.core.Message`, `MessageProperties` và `MessageConverter` quen thuộc. Tuy nhiên, adapter bên trong vẫn chuyển sang native AMQP 1.0 message. **Không mặc định DTO producer 0-9-1 và consumer 1.0 luôn mapping giống nhau** chỉ vì cùng Spring `MessageConverter` interface.

Một kế hoạch tương thích cần hợp đồng **độc lập với Java classpath**:

~~~json
{
  "eventId": "81dfe285-5bcc-4c94-aec5-e11b3ba5cc2c",
  "eventType": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-26T02:00:00Z",
  "payload": {
    "orderId": "ORD-1001",
    "currency": "VND",
    "totalMinorUnits": 250000
  }
}
~~~

### 19.1. Contract test phải chạy trên cả bốn trường hợp

| Producer | Consumer | Phải xác nhận |
| --- | --- | --- |
| 0-9-1 | 0-9-1 | Baseline hiện tại |
| 0-9-1 | 1.0 | Consumer mới đọc được message lịch sử |
| 1.0 | 0-9-1 | Producer mới vẫn tương thích consumer cũ |
| 1.0 | 1.0 | Luồng đích mong muốn hoạt động |

Đừng chỉ test một hướng cross-protocol: các trường annotation, properties và body sections có thể được broker map khác nhau theo hướng chuyển.

### 19.2. `contentType`, Java class header và Jackson

- Cố định `content-type=application/json` theo hợp đồng, kiểm tra charset UTF-8.
- Dùng `eventType`/`schemaVersion` ổn định thay vì để `__TypeId__` FQCN producer quyết định mọi consumer type.
- Kiểm tra String JSON **đã serialize** có bị chuyển thành JSON **quoted string** khi truyền qua converter mới không.
- Kiểm tra Java Time/`Instant`, UUID, BigDecimal, enum và null.
- Nếu có polymorphic event, giới hạn subtype bằng allowlist; không mở `trustedPackages("*")` bừa bãi.
- Giữ event ID trong payload để đối soát khi header mapping không bảo toàn type.
- Dùng golden samples trong CI bao gồm message cũ nằm trong retry/DLQ.

Một JSON converter chạy được với DTO đơn giản chưa đủ bảo đảm mọi header/property AMQP 0-9-1 có ánh xạ tương đương trong AMQP 1.0.

## 20. Observability: các dashboard 0-9-1 có thể không đo đúng 1.0

Các metric nên phân tầng:

1. **Application outcomes:** publish accepted/rejected/unknown; business commits/s; handler errors; dedup; event age.
2. **Broker health:** queue ready/unacked, consumer count, queue/node resource alarms, quorum leader health.
3. **Protocol client:** connections, links, flow credits, settlement latency, recovery attempts, errors.
4. **End-to-end:** source outbox pending, DLQ backlog, reconciliation mismatch và p95/p99.

### 20.1. Không nhầm số liệu Management UI

Theo tài liệu RabbitMQ 4.x, một số **message rate charts theo exchange/queue trong Management UI** vốn dành cho kết nối AMQP 0-9-1 **không phản ánh tương tự kết nối AMQP 1.0**. Vì thế việc migrate có thể khiến biểu đồ bạn quen nhìn thay đổi dù message vẫn chạy.

**Không** đánh giá migration chỉ dựa vào một chart management UI. Dùng Prometheus metrics/broker instrumentation và metrics nghiệp vụ độc lập; kiểm tra exact exporter families và khả năng gắn label protocol/queue trong phiên bản đang dùng.

### 20.2. Bộ metric ứng dụng gợi ý

| Metric do ứng dụng định nghĩa | Lý do |
| --- | --- |
| `app_amqp_publish_accepted_total` | Tổng publish accepted theo protocol |
| `app_amqp_publish_released_total` | Phân biệt unroutable/released trên 1.0 |
| `app_amqp_publish_unknown_total` | Timeout/connection lost trước outcome |
| `app_amqp_handler_committed_total` | Goodput nghiệp vụ thực |
| `app_amqp_handler_failed_total` | Loại lỗi schema/business/downstream |
| `app_amqp_event_age_seconds` | End-to-end latency |
| `app_amqp_duplicate_suppressed_total` | Redelivery/replay duplicate được chặn |
| `app_outbox_pending_events` | Event chưa có kết quả publish đáng tin cậy |
| `app_amqp_dlq_oldest_age_seconds` | Message lỗi chưa được triage |

Tên `app_` là **quy ước mẫu**, không phải Spring Boot tự tạo sẵn. Nhãn nên gồm `service`, `protocol`, `queue`, `eventType`, `errorClass` nếu tập giá trị nhỏ và được quản lý. **Không gắn UUID eventId, payload hay exception message vào Prometheus labels.**

### 20.3. Đọc đúng sự cố

| Triệu chứng | Điều cần phân biệt |
| --- | --- |
| 1.0 connection open nhưng publish không tiến triển | Flow credits, target address, outcome, queue availability |
| 1.0 future failed/released | Unroutable, authorization, broker rejection, library error |
| 1.0 listener đã attach nhưng không có delivery | Source queue, credit, SAC active state, queue ready |
| 0-9-1 consumer count giảm khi canary bật | Legacy listener bị disable hay message đang được competing consumer nhận? |
| DLQ tăng sau migration | Converter/schema/settlement khác semantics cũ |
| Queue ready=0 | Chưa đủ; outbox có thể dồn hoặc event bị unroutable |

Nếu phải rollback vì thiếu dashboard, hãy coi đó là **lỗ hổng quan sát**, không cố tuyên bố migration thành công dựa vào việc client không ném exception.

## 21. Security: SASL, TLS, vhost và permissions

### 21.1. RabbitMQ AMQP 1.0 cần SASL

Ở RabbitMQ 4.x, AMQP 1.0 yêu cầu **SASL** khi thiết lập connection. Các cơ chế/xác thực có thể bao gồm username/password, token hoặc chứng chỉ TLS theo cấu hình broker và plugin auth phù hợp.

Cần xác minh:

- Broker có chấp nhận cơ chế SASL mà client chọn không?
- TLS có được bật và certificate/hostname validation đúng không?
- Virtual host được chỉ định đúng theo cấu hình của AMQP 1.0 client?
- User có quyền **write** exchange và **read** queue cần dùng không?
- Admin có quyền configure topology hay chỉ ứng dụng producer/consumer?
- Các bên dùng secret mới có thể reconnect, không chỉ giữ connection cũ?

Đối với AMQP 1.0 native client, cách chọn vhost/connection hostname có thể khác property `spring.rabbitmq.virtual-host` của 0-9-1. Nếu dùng Boot dedicated module, đọc chính xác `AmqpRabbitProperties`/connection customizer cho version đó; **không sao chép nguyên config vhost 0-9-1 sang 1.0**.

### 21.2. Tách secret không đồng nghĩa phải có user khác

Có thể dùng cùng RabbitMQ principal/vhost cho hai protocol nếu quyền và chính sách cho phép, nhưng trong canary nên cân nhắc **danh tính riêng** để:

- Audit được AMQP 1.0 clients.
- Hạn chế quyền chỉ tới canary exchange/queue.
- Thu hồi canary không ảnh hưởng legacy consumer.
- Xác định connection đang sử dụng stack nào.
- Tránh một lỗi cấu hình admin xóa hoặc declare nhầm production topology.

Dù dùng principal nào, không hard-code credentials hoặc tắt TLS hostname verification để “test dễ hơn”.

### 21.3. Cùng port không có nghĩa được phép xuyên firewall/proxy

Một số load balancer/proxy TCP có kiểm tra protocol hoặc idle timeouts. Test:

1. Kết nối 0-9-1 tới broker path hiện tại.
2. Kết nối AMQP 1.0 + SASL trên cùng endpoint.
3. TLS handshake và certificate validation.
4. Kết nối qua load balancer, không chỉ trực tiếp một node.
5. Reconnect/failover sau node restart.
6. Theo dõi connection churn và identity/truststore rotation.

Cần giữ heartbeat/idle timeout tương thích giữa client và broker, không mặc định setting 0-9-1 `requested-heartbeat` có cùng tên và ý nghĩa trong AMQP 1.0 dedicated stack.

## 22. Khi nào nên chọn AMQP 1.0, khi nào giữ 0-9-1?

Đánh giá phải dựa trên **lợi ích của use case** và **chi phí chuyển đổi**.

| Điều kiện dự án | Hướng lựa chọn ban đầu |
| --- | --- |
| Ứng dụng mới, dùng RabbitMQ 4.x, cần flow control/feature 1.0 | Đánh giá AMQP 1.0 trước bằng spike/canary |
| Ứng dụng cũ dùng `RabbitTemplate`, advice/retry/transaction 0-9-1 phức tạp | Giữ 0-9-1 cho tới khi có parity tests |
| Cần chạy với nhiều broker AMQP 1.0 | Đánh giá **generic AMQP 1.0**, không mặc định RabbitMQ-specific module portable |
| Cần 0-9-1 transactions hiện hữu | Không migrate cơ học; RabbitMQ AMQP 1.0 hiện không hỗ trợ transaction |
| Cần một plugin/interceptor chỉ hỗ trợ 0-9-1 | Giữ 0-9-1 hoặc thay kiến trúc trước |
| Need 1.0 stream filtering/credit behavior | Đánh giá trên queue type/version phù hợp |
| Doanh nghiệp có RPO gần 0 và nhiều external side effects | Ưu tiên outbox/inbox/reconciliation bất kể protocol |
| Không có khả năng test cross-protocol, rollback, metrics | Không nên migrate production ngay |

**AMQP 1.0 có thể là lựa chọn tốt cho ứng dụng mới, nhưng điều đó không biến AMQP 0-9-1 thành “sai” trong ứng dụng đang vận hành.** Việc migrate chỉ đáng giá khi các chức năng thiết yếu đã được chứng minh tương thích.

### 22.1. Dựng scorecard thay vì tranh luận “phiên bản nào mới hơn?”

Dùng các tiêu chí có trọng số theo dự án:

| Tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| Feature parity | Publish/consume, routing, RPC, TTL/DLX, batch, priorities, plugin hooks có đủ không? |
| Reliability | Unknown outcome, redelivery, outbox/inbox, settle/retry có tương đương mục tiêu? |
| Performance | Goodput/p95/p99 và tài nguyên dưới tải thật? |
| Interoperability | Broker, producer/consumer đa ngôn ngữ, data conversion có đúng không? |
| Operations | Metrics, traces, alarms, DR và DLQ replay ra sao? |
| Security | SASL/TLS/vhost/permissions, type/header validation có an toàn không? |
| Upgrade path | Java/Boot/Spring/RabbitMQ versions có được hỗ trợ đồng thời không? |
| Rollback | Có thể quay về 0-9-1 mà không mất/nhân đôi event không? |

Hãy yêu cầu kết quả **PASS/FAIL/NOT TESTED** cho từng tiêu chí, kèm evidence, thay vì kết luận cảm tính.

## 23. Kế hoạch canary từng pha và rollback

Một quá trình migration điển hình:

### Pha A — Inventory và ranh giới

1. Liệt kê producer/consumer, các queue/exchange/binding thực tế.
2. Ghi rõ Spring Boot/Spring AMQP/JDK/RabbitMQ versions.
3. Phân loại nghiệp vụ phụ thuộc `RabbitTemplate` APIs, `Channel`, transaction hoặc RabbitAdmin.
4. Ghi event schema/headers/version, DLQ topology và routing keys.
5. Xác định SLA/SLO, RPO/RTO và owner của từng luồng.

### Pha B — Spike độc lập

1. Dựng broker thử RabbitMQ 4.x có cấu hình gần production.
2. Tạo queue/exchange/binding **tách biệt** cho AMQP 1.0.
3. Tạo service dùng dedicated Spring AMQP 1.0 stack, cấu hình đúng namespace.
4. Smoke test future/outcome và listener settlement.
5. Test address v2, credentials/SASL/TLS, topology provisioning.

### Pha C — Compatibility và failure injection

1. Thử cả hai hướng cross-protocol.
2. Verify JSON schema, metadata, event ID và reply-to nếu có RPC.
3. Thử thiếu binding, auth fail, consumer crash, loss of outcome.
4. Kiểm tra retry/DLQ và poison message.
5. Đo publish acceptance, consumer commits và tail latency.
6. Chứng minh outbox/idempotency hoạt động với duplicate/replay.

### Pha D — Canary traffic thật có kiểm soát

1. Dùng một nhóm sự kiện/tenant nhỏ có thể đối soát.
2. Không để hai consumer cạnh tranh trên cùng queue nếu không có chủ đích.
3. So sánh kết quả AMQP 1.0 với baseline 0-9-1.
4. Theo dõi feature flags, queue age, resource alarms, confirm/settlement.
5. Chạy trong khoảng đủ dài để có reconnect/rolling deploy và message lỗi.
6. Có quyết định go/no-go với tiêu chí định lượng.

### Pha E — Mở rộng và rollback

1. Nâng traffic theo các nấc đã định.
2. Duy trì khả năng ngừng canary và chuyển producer/consumer về legacy path.
3. Khi rollback, **không xóa** queue/metadata còn message chưa xử lý.
4. Đối chiếu outbox và inbox theo event ID, xử lý event chưa có outcome.
5. Replay có giới hạn khi có gap, giữ event ID gốc.
6. Chỉ bỏ legacy path khi đủ retention/compatibility window và được owner phê duyệt.

**Không rollback bằng cách purge queue hoặc đổi eventId hàng loạt.** Dòng message được bảo vệ trước khi flip route, và business side effect phải có bằng chứng không mất/trùng.

## 24. Mười sáu kịch bản kiểm thử trước khi quyết định migrate

Mọi test gây lỗi phải chạy trên **staging có vhost/queue riêng**, dùng event giả và có kiểm soát. Ghi lại source/target versions, protocol, message IDs, publish outcomes, settlement, DLQ và business commit.

### A. Kiểm tra protocol handshake

1. Dựng RabbitMQ 4.x với AMQP 0-9-1 và 1.0 native.
2. Dùng client 0-9-1 gửi event thử và xác minh connection.
3. Dùng AMQP 1.0 client mở connection mới tới cùng host/port.
4. Xác minh broker nhận đúng protocol và SASL.
5. So log connections/node health của hai bên.

**Kỳ vọng:** cùng port không có nghĩa client/ConnectionFactory hoán đổi được.

### B. Sai namespace YAML

1. Chạy một canary `spring-rabbitmq-client` đúng version.
2. Cố tình chỉ đặt `spring.rabbitmq.*` mà bỏ `spring.amqp.rabbitmq.*` cần thiết.
3. Quan sát client không nhận đúng connection settings hoặc dùng mặc định.
4. Sửa đúng namespace và xác minh broker/vhost được chọn.

**Kỳ vọng:** không “mượn” property 0-9-1 cho Bean 1.0.

### C. Sai Bean listener factory

1. Một ứng dụng thử có cả hai listener factories.
2. Một `@RabbitListener` cố tình không chỉ `containerFactory`.
3. Kiểm tra factory mặc định thực được chọn.
4. Chỉ định rõ factory 1.0 cho canary và factory 0-9-1 cho legacy.
5. Kiểm tra consumer count bằng broker instrumentation.

**Kỳ vọng:** annotation giống nhau không làm stack tự phân biệt theo tên queue.

### D. Canary tranh delivery với legacy consumer

1. Gắn hai listeners khác protocol vào **cùng một work queue test**.
2. Gửi 20 event ID phân biệt.
3. Ghi lại mỗi event được consumer nào nhận.
4. Quan sát đó là competing consumers, không phải cả hai cùng nhận bản sao.
5. Chuyển canary sang queue riêng, binding riêng và kiểm tra lại.

**Kỳ vọng:** không sử dụng chung queue như một cơ chế mirrored shadow traffic.

### E. Address v2 so với legacy v1

1. Test publisher AMQP 1.0 với `/exchanges/demo.direct/key`.
2. Thử một địa chỉ kiểu v1 `/exchange/demo.direct/key` trên môi trường test.
3. Ghi nhận behavior tùy deprecation policy/version.
4. Chuyển sang v2 và cấu hình target rõ ràng.
5. Xác minh DLQ/unroutable handling khi địa chỉ không hợp lệ.

**Kỳ vọng:** không xây ứng dụng mới phụ thuộc address v1 bị deprecate.

### F. Routing key chứa dấu slash

1. Tạo binding với routing key `orders/created`.
2. Gửi qua địa chỉ sai `/exchanges/demo.direct/orders/created`.
3. So với địa chỉ đúng `/exchanges/demo.direct/orders%2Fcreated`.
4. Kiểm tra broker routing và event ID.
5. Đặt regression test percent-encoding.

**Kỳ vọng:** encode component, không nối chuỗi có `/` tùy tiện.

### G. Producer 0-9-1 → consumer 1.0

1. Producer legacy gửi JSON body với messageId và headers.
2. Consumer canary 1.0 nhận từ queue thử.
3. So bytes, content type, eventId, correlationId, schemaVersion.
4. Commit một marker inbox với eventId.
5. ACK/settle thành công, không tạo duplicate.

**Kỳ vọng:** xác minh inter-protocol conversion chiều legacy → new.

### H. Producer 1.0 → consumer 0-9-1

1. Publisher 1.0 gửi JSON cùng contract.
2. Consumer legacy 0-9-1 đọc queue thử.
3. So body shape, Jackson DTO, basic properties và headers.
4. Kiểm tra `@RabbitListener` handler commit và ACK.
5. Đưa test vào CI trước khi tăng canary.

**Kỳ vọng:** tương thích hai chiều được chứng minh, không suy luận từ G.

### I. Publish vào exchange không có binding

1. Tạo exchange test không có binding tới queue đích.
2. Publish bằng 0-9-1 với mandatory/returns.
3. Publish bằng 1.0 với target address v2.
4. Quan sát kết quả publisher confirm/return **so với** 1.0 outcome, chẳng hạn `released` theo RabbitMQ semantics.
5. Đảm bảo outbox không coi unroutable là success.

**Kỳ vọng:** routing failure được xử lý đúng ở mỗi protocol stack.

### J. Outcome bị mất trước khi producer nhận

1. Ghi event E42 trong transactional outbox.
2. Cho producer 1.0 gửi rồi giả lập mất connection trước completion.
3. Không kết luận broker đã nhận hay chưa.
4. Retry cùng eventId từ outbox.
5. Xác minh consumer idempotent không áp dụng side effect hai lần.

**Kỳ vọng:** đổi giao thức không tạo được exactly-once publish hay exactly-once business effect.

### K. Consumer DB commit trước khi settle

1. Consumer 1.0 nhận E43, commit business DB + inbox.
2. Mô phỏng mất connection trước settlement.
3. Khôi phục consumer và cho message redeliver.
4. Kiểm tra unique constraint chặn thực thi lần hai.
5. Xác minh message được settle/ACK thành công sau duplicate detection.

**Kỳ vọng:** idempotency còn đúng khi thay ACK 0-9-1 bằng settlement 1.0.

### L. Poison message và terminal DLQ

1. Gửi payload sai schema vào queue canary.
2. Kiểm tra container error handler/settlement.
3. Xác minh reject/discard theo chính sách được dùng thực.
4. Kiểm tra terminal DLQ nhận được message với metadata cần điều tra.
5. Replay có chọn lọc sau khi sửa lỗi, giữ eventId.

**Kỳ vọng:** không tạo requeue storm hoặc drop âm thầm.

### M. Tính năng transaction không còn tương đương

1. Liệt kê một use case legacy phụ thuộc `channelTransacted` hoặc RabbitMQ transaction.
2. Xác minh RabbitMQ AMQP 1.0 không hỗ trợ protocol transactions trong version test.
3. Thiết kế thay thế bằng outbox/inbox hoặc giữ use case đó ở 0-9-1.
4. Thử crash giữa DB commit và broker publish.
5. Đánh giá RPO/RTO và unknown outcome.

**Kỳ vọng:** không migrate một yêu cầu nghiệp vụ chưa có phương án thay thế.

### N. Flow credit, prefetch và throughput

1. Giữ input và số pods cố định.
2. Đo consumer 0-9-1 với prefetch đã biết.
3. Đo consumer 1.0 với link credit/configuration được library hỗ trợ.
4. So business commits/s, p95/p99, unacked/outstanding, memory và queue age.
5. Giảm tải khi DB/API bắt đầu saturation.

**Kỳ vọng:** không coi prefetch và credit là cùng một thuộc tính có thể copy.

### O. Reconnect, failover và Single Active Consumer

1. Dùng quorum queue canary theo cấu hình test.
2. Chạy 1.0 consumer với monitoring links/active state.
3. Mô phỏng node failover hoặc chuyển active consumer.
4. Quan sát recovery và redelivery.
5. Kiểm tra thứ tự và business idempotency.

**Kỳ vọng:** recovery hoạt động trên client/server versions đã khóa, không dựa vào mô tả khái quát của AMQP 1.0.

### P. Rollback khi canary có dữ liệu chưa xử lý

1. Cho canary nhận/đẩy một lượng event có eventId.
2. Giả lập một tỷ lệ lỗi conversion/settlement.
3. Dừng **đúng canary** mà không purge queue.
4. Xác định event chưa accepted/settled; reconcile với inbox/outbox.
5. Chuyển route về legacy theo runbook và replay có rate limit.
6. Xác minh không mất hoặc lặp business side effects.

**Kỳ vọng:** rollback được kiểm chứng ở mức dữ liệu, không chỉ ở mức deploy.

## 25. Runbook chẩn đoán và những nhầm lẫn cần tránh

### 25.1. Khi ứng dụng không kết nối được

Kiểm tra theo thứ tự:

1. **Stack nào?** 0-9-1 hay 1.0? Module và concrete factory nào đang được inject?
2. **Broker hỗ trợ không?** RabbitMQ version native 1.0 hay legacy plugin?
3. **Đường kết nối:** TCP/TLS, proxy, protocol negotiation, SASL credentials.
4. **Vhost/permissions:** write exchange, read queue, configure declarables.
5. **Property namespace:** `spring.rabbitmq.*` hay `spring.amqp.rabbitmq.*`?
6. **Environment/connection bean:** 1.0 native `Environment` có đúng connection settings không?
7. **Logs:** không log secret; ghi protocol, cluster, vhost và exception category.

Một lỗi “connection refused” có thể là TCP, còn “protocol header rejected”/SASL auth failure là các tầng khác. Đừng chữa chúng bằng cách đổi `prefetch` hoặc `RabbitTemplate` confirm type.

### 25.2. Khi kết nối được nhưng không có message

1. Kiểm tra target/source address v2 và percent-encoding.
2. Kiểm tra exchange/queue/binding/permissions.
3. Xem publish Future/outcome, không chỉ method invocation.
4. Xem consumer credit/active state và số consumer.
5. Kiểm tra cross-protocol body/metadata conversion.
6. Xem DLQ và error handler; message có thể bị reject trước handler.
7. Xem outbox pending/oldest age để biết event chưa publish.
8. Xác minh business DB commits chứ không chỉ message count.

### 25.3. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ AMQP 1.0 là bản wire-upgrade của 0-9-1 | Dùng sai client/factory | Chọn stack theo protocol, test handshake |
| Cùng port 5672 nên cùng cấu hình | Bean không đọc đúng property | Tách namespace và class |
| Bê `spring.rabbitmq.listener.simple.prefetch` sang 1.0 | Không điều tiết credit như dự kiến | Dùng API/factory 1.0 |
| Cho rằng `spring-boot-starter-amqp` luôn là 0-9-1 | Nhầm giữa Boot 3.x và Boot 4.x | Khóa Boot version và starter phù hợp |
| Coi `spring-rabbitmq-client` là broker-agnostic | Không chạy với AMQP 1.0 broker khác | Chọn generic module khi portability là mục tiêu |
| Thấy `spring-rabbit` transitively nên chạy 0-9-1 | Đánh giá sai runtime | Xem concrete Template/Factory/connection |
| Chỉ thấy `@RabbitListener` rồi cho rằng protocol giống nhau | Listener bind sai factory | Khai báo factory rõ ràng |
| Dùng address `/exchange/...` legacy v1 | Có thể bị deprecate/không còn hỗ trợ | Address v2 `/exchanges/...` |
| Quên percent-encoding | Routing key có slash bị hiểu sai | Encode RFC 3986 |
| Map confirm ACK sang accepted 1:1 | Bỏ qua unroutable/outcome khác | Test release/reject/unknown outcome |
| Coi AMQP 1.0 transactions được RabbitMQ hỗ trợ | Sai feature parity | Kiểm tra limitations, dùng outbox/inbox |
| Hai consumer dùng chung queue để “shadow” | Mất bản copy dùng so sánh | Tạo queue riêng/binding phù hợp |
| Quên JSON type conversion | Handler fail trước business logic | Golden payloads, schema tests hai chiều |
| Bỏ qua DLQ khi migrate | Poison message rơi mất hoặc lặp | Test settlement/DLX/terminal DLQ |
| Đo mỗi UI publish rate | Bỏ sót 1.0 hoặc business errors | App metrics, queue metrics, trace/commit |
| Rollback bằng purge hoặc ID mới | Mất dữ liệu hoặc duplicate effect | Outbox/inbox và reconciliation |

### 25.4. Tiêu chí tạm dừng migration

Dừng canary khi một trong các điều kiện xảy ra:

- Không thể xác minh broker acceptance và business commit của message.
- Unroutable/outcome unknown không được ghi nhận có nguồn phát lại.
- DLQ có message hợp lệ bị reject do schema mismatch.
- Error/timeout p95/p99 vượt mức đã thỏa thuận.
- Một feature quan trọng (transaction, plugin hook, stream behavior) chưa có parity.
- Listener bị bind nhầm factory hoặc queue không mong muốn.
- Không có đủ metrics để phân biệt broker lỗi với client lỗi.
- Không thể rollback mà vẫn bảo toàn eventId và side effects.

## 26. Checklist và kết luận

### Checklist trước production

- [ ] Đã khóa RabbitMQ/JDK/Spring Boot/Spring AMQP/Java client versions tương thích.
- [ ] Đã xác minh AMQP 1.0 native trên broker version và yêu cầu SASL/TLS.
- [ ] Đã chọn **một** trong RabbitMQ-specific 1.0, generic 1.0 hoặc giữ 0-9-1.
- [ ] Dependency/starter phù hợp với **đúng major version Spring Boot**.
- [ ] `spring.rabbitmq.*` và `spring.amqp.rabbitmq.*` không bị dùng lẫn.
- [ ] Connection factory, template, admin, listener factory được phân định theo protocol.
- [ ] Không có listener canary vô tình cạnh tranh trên work queue production.
- [ ] Topology exchanges/queues/bindings/permissions được provision đúng owner.
- [ ] Address v2 và percent-encoding có integration test.
- [ ] Cross-protocol message conversion được test cả hai chiều.
- [ ] JSON content type, eventId, schemaVersion và type headers có hợp đồng.
- [ ] Publisher accepted/released/rejected/unknown outcomes được xử lý theo API thực.
- [ ] Settlement sau business commit, idempotency chống redelivery.
- [ ] Retry hữu hạn, DLX/terminal DLQ có end-to-end test.
- [ ] Tính năng 0-9-1 transactions/plugin hooks đã có phương án tương thích hoặc được giữ nguyên.
- [ ] Flow credit/concurrency và downstream capacity đã benchmark.
- [ ] Metrics 1.0 không phụ thuộc hoàn toàn vào chart Management UI của 0-9-1.
- [ ] Có canary, rollback và reconciliation bằng eventId cùng owner phê duyệt.
- [ ] Đã diễn tập mất outcome, consumer crash, poison message, failover và rollback.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [RabbitMQ — AMQP 1.0](https://www.rabbitmq.com/docs/amqp)
- [RabbitMQ — Protocols](https://www.rabbitmq.com/docs/protocols)
- [RabbitMQ — Inter-Protocol Property Conversion](https://www.rabbitmq.com/docs/conversions)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Queues and Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Spring AMQP — RabbitMQ AMQP 1.0 Support](https://docs.spring.io/spring-amqp/reference/rabbitmq-amqp-client.html)
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html)
- [RabbitMQ AMQP 1.0 Java Client](https://rabbitmq.github.io/rabbitmq-amqp-java-client/stable/htmlsingle/)

### Tổng kết

**AMQP 1.0 và AMQP 0-9-1 không phải hai phiên bản có thể thay thế bằng cách sửa một dòng cấu hình.** RabbitMQ 4.x có thể phục vụ cả hai, và Spring AMQP 4.x cung cấp module RabbitMQ 1.0 riêng, nhưng **ConnectionFactory, template, listener container, property namespace, flow control, publisher outcomes và settlement** phải được hiểu đúng theo từng stack. Cross-protocol messaging là khả năng hữu ích của RabbitMQ, song cần kiểm tra property mapping, JSON schema và routing/transaction semantics theo chiều dữ liệu thực tế.

Chiến lược an toàn là **khóa compatibility matrix → chọn canary tách biệt → thử cả hai chiều cross-protocol → đo outcome và business commit → kiểm tra retry/DLQ/idempotency → xác nhận hiệu năng/vận hành → rollout có rollback**.

Trong **SPRING_AMQP**, câu hỏi quan trọng không phải “AMQP 1.0 mới hơn bao nhiêu?”, mà là **“Ta đã xác minh đúng module, đúng protocol và đúng hợp đồng dữ liệu, đồng thời chứng minh event vẫn được publish, xử lý và phục hồi đáng tin cậy khi có lỗi hay chưa?”**





