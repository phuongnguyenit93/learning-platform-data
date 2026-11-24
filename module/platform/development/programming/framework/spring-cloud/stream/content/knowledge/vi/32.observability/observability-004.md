# Điều khiển STARTED, STOPPED, PAUSED và RESUMED theo khả năng binder

Spring Cloud Stream cho phép quan sát và điều khiển vòng đời của từng binding. Qua Actuator hoặc API trong ứng dụng, ta có thể khởi động một binding đang dừng, dừng một binding đang chạy, tạm dừng consumer hoặc tiếp tục consumer đã tạm dừng.

Bốn trạng thái thường gặp là:

- **STARTED:** binding được khởi động.
- **STOPPED:** binding bị dừng.
- **PAUSED:** consumer tạm ngừng nhận message nhưng vẫn có thể duy trì kết nối.
- **RESUMED:** consumer tiếp tục nhận message sau khi pause.

Điểm quan trọng là **PAUSED/RESUMED phụ thuộc binder và thành phần nền có hỗ trợ pause hay không**. Tài liệu Spring Cloud Stream hiện liệt kê Kafka binder và Solace binder cho hai trạng thái này. Kafka Streams binder chỉ hỗ trợ STARTED/STOPPED. Không nên giả định RabbitMQ hoặc Pulsar binder có pause/resume chỉ vì endpoint Actuator chấp nhận cùng một giá trị state.

Bài học này tập trung vào binding lifecycle của Spring Cloud Stream trong hệ thống xử lý sự kiện, cách điều khiển qua Actuator và Java API, khác biệt giữa stop với pause, phạm vi hỗ trợ của từng binder và quy trình vận hành an toàn.

## 1. Binding lifecycle nằm ở đâu?

Spring Cloud Stream kết nối function của ứng dụng với destination thông qua binding và binder. Binding có vòng đời riêng, được binder tạo ra khi ứng dụng khởi động hoặc khi binding được tạo động.

Ví dụ function:

~~~java
@Bean
Consumer<OrderCreated> processOrder(OrderService service) {
    return order -> service.process(order);
}
~~~

Với function tên `processOrder`, input binding mặc định là `processOrder-in-0`. Binding đó kết nối consumer với destination được cấu hình, chẳng hạn topic Kafka hoặc queue RabbitMQ.

~~~text
Spring Boot application
       |
       v
Spring Cloud Stream binding
  processOrder-in-0
       |
       v
Binder
       |
       v
Broker destination
  orders.created
~~~

Lifecycle controller điều khiển binding có tên `processOrder-in-0`. Nó không điều khiển trực tiếp toàn bộ ứng dụng Spring Boot, không dừng JVM và cũng không thay đổi cấu hình topic/queue trên broker.

Cần phân biệt ba phạm vi:

| Phạm vi | Ví dụ | Được điều khiển bởi |
|---|---|---|
| Application instance | Một JVM hoặc một pod | Process manager, Kubernetes, systemd |
| Spring Cloud Stream binding | `processOrder-in-0` | Binding lifecycle controller / Actuator |
| Broker resource | Kafka topic, Rabbit queue, Pulsar subscription | Công cụ quản trị broker |

Khi dừng một binding, application instance vẫn có thể chạy, health endpoint vẫn trả lời và các binding khác vẫn hoạt động.

## 2. Bốn trạng thái STARTED, STOPPED, PAUSED và RESUMED

| State | Ý nghĩa | Dùng khi |
|---|---|---|
| `STARTED` | Khởi động binding đang dừng | Bật lại một consumer hoặc producer binding đã STOPPED |
| `STOPPED` | Dừng thành phần gắn với binding | Bảo trì, thay đổi cấu hình cần restart hoặc ngừng luồng |
| `PAUSED` | Tạm ngừng nhận message trên consumer có hỗ trợ | Tạm ngừng tiêu thụ nhưng muốn giữ trạng thái kết nối/partition |
| `RESUMED` | Tiếp tục consumer đã PAUSED | Tiếp tục nhận message sau khi điều kiện vận hành được khôi phục |

Có hai cặp thao tác:

~~~text
STARTED  <---->  STOPPED
RESUMED  <---->  PAUSED
~~~

Không dùng nhầm hai cặp:

- Sau `STOPPED`, dùng `STARTED` để chạy lại.
- Sau `PAUSED`, dùng `RESUMED` để tiếp tục.
- `STARTED` không phải tên thay thế cho `RESUMED`.
- `STOPPED` không phải tên thay thế cho `PAUSED`.

`STARTED` và `STOPPED` là vòng đời Lifecycle cơ bản. `PAUSED` và `RESUMED` yêu cầu thành phần tiêu thụ triển khai khả năng `Pausable` của Spring Integration hoặc cơ chế tương đương do binder cung cấp.

## 3. STOPPED khác PAUSED như thế nào?

Đây là khác biệt quan trọng nhất khi vận hành Kafka consumer.

### STOPPED

Khi binding bị STOPPED, thành phần được binding quản lý bị dừng. Với Kafka consumer thông thường, consumer container dừng và rời khỏi nhóm consumer. Việc này có thể làm Kafka thực hiện partition rebalance để phân phối lại partition cho các consumer còn hoạt động.

Dùng STOPPED khi cần dừng hẳn binding, ví dụ:

- Thay đổi cấu hình consumer cần khởi động lại.
- Bảo trì ứng dụng.
- Tạm thời loại bỏ một binding khỏi hoạt động.
- Chuẩn bị triển khai hoặc thay đổi topology.

### PAUSED

Khi consumer được PAUSED, consumer tạm ngừng nhận/phân phối record nhưng vẫn có thể duy trì kết nối với broker. Với Kafka binder thông thường, pause/resume được thiết kế để ngừng tiêu thụ mà không làm partition rebalance.

Điều đó hữu ích khi:

- Downstream database đang bảo trì.
- Cần tạm ngừng xử lý để kiểm tra sự cố.
- Tốc độ xử lý cần được điều tiết trong thời gian ngắn.
- Muốn giữ phân công partition hiện tại trong lúc consumer tạm nghỉ.

Một endpoint đang pause vẫn có thể được xem là running ở mức Lifecycle. Vì vậy, khi quan sát trạng thái, cần kiểm tra cả cờ `paused` hoặc `pausable`, không chỉ nhìn `state=running`.

~~~text
Kafka consumer binding

Đang chạy
   |
   | PAUSED
   v
Tạm dừng nhận record
Giữ consumer/container và assignment
   |
   | RESUMED
   v
Tiếp tục nhận record

Đang chạy
   |
   | STOPPED
   v
Consumer container dừng
Có thể rời consumer group và gây rebalance
   |
   | STARTED
   v
Consumer khởi động và tham gia group lại
~~~

Pause không có nghĩa là broker ngừng nhận message từ producer. Producer vẫn có thể tiếp tục ghi. Backlog có thể tăng trong lúc consumer tạm dừng. Pause cũng không tự xử lý các message đang được function xử lý dở; hãy kiểm tra thời gian xử lý và acknowledgment của binder trước khi thao tác.

## 4. Binder nào hỗ trợ pause/resume?

Spring Cloud Stream cung cấp API lifecycle chung, nhưng khả năng thực tế do binder và thành phần nền quyết định.

Theo tài liệu Spring Cloud Stream hiện hành:

| Binder / kiểu binding | STARTED / STOPPED | PAUSED / RESUMED | Ghi chú |
|---|---:|---:|---|
| Kafka binder thông thường | Có | Có, với consumer | Pause consumer mà không gây partition rebalance |
| Kafka Streams binder | Có | Không | Chỉ hỗ trợ STOPPED và STARTED |
| Solace binder | Có | Có theo tài liệu chung | Kiểm tra phiên bản và cấu hình Solace cụ thể |
| RabbitMQ binder | Có qua lifecycle chung | Không được tài liệu chung liệt kê | Không giả định pause/resume có hiệu lực |
| Pulsar binder | Có qua lifecycle chung | Không được tài liệu chung liệt kê | Không giả định pause/resume có hiệu lực |
| Custom binder | Tùy implementation | Chỉ khi có hỗ trợ tương ứng | Thành phần đích cần triển khai khả năng pausable |

Bảng này mô tả khả năng được tài liệu Spring Cloud Stream công bố, không phải cam kết rằng mọi phiên bản binder đều có cùng hành vi. Hãy đối chiếu đúng phiên bản Spring Cloud Stream, binder và client mà ứng dụng đang dùng.

### Kafka binder thông thường

Kafka binder hỗ trợ pause/resume cho consumer. Tài liệu riêng hướng dẫn dùng binding lifecycle với `State.PAUSED` và `State.RESUMED`. Mục tiêu là tạm ngừng tiêu thụ mà không tạo partition rebalance.

### Kafka Streams binder

Kafka Streams binder có tài liệu điều khiển riêng. Nó chỉ hỗ trợ hai lifecycle phase là `STOPPED` và `STARTED`; `PAUSED` và `RESUMED` không có sẵn.

Ngoài ra, các binding của cùng một Kafka Streams function được hỗ trợ bởi cùng một `StreamsBuilderFactoryBean`. Vì vậy, gọi thao tác STOPPED/STARTED trên input hoặc output binding của function có thể điều khiển cùng processor. Không xem từng binding name của một function Kafka Streams là một tiến trình độc lập.

### RabbitMQ và Pulsar

API lifecycle chung cho phép điều khiển STARTED/STOPPED. Tài liệu chung hiện không liệt kê RabbitMQ và Pulsar trong nhóm binder hỗ trợ PAUSED/RESUMED. Nếu cần chức năng pause riêng, phải kiểm tra tài liệu đúng phiên bản hoặc thử nghiệm với binder đang triển khai; không suy ra khả năng chỉ từ việc REST endpoint nhận request.

## 5. Bật Binding Actuator endpoint

Actuator cho phép liệt kê binding, xem thông tin của một binding và gửi yêu cầu thay đổi state.

Cần dependency Actuator và một web runtime. Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu ứng dụng dùng WebFlux, có thể dùng `spring-boot-starter-webflux` thay cho `spring-boot-starter-web`.

Cấu hình expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Endpoint bindings không nhất thiết được expose mặc định. Chỉ thêm `bindings` vào danh sách expose khi ứng dụng thực sự cần chức năng này.

Sau khi ứng dụng khởi động, có thể truy cập:

~~~text
GET /actuator/bindings
GET /actuator/bindings/{bindingName}
POST /actuator/bindings/{bindingName}
~~~

Ví dụ binding có tên `processOrder-in-0`:

~~~bash
curl http://localhost:8080/actuator/bindings
curl http://localhost:8080/actuator/bindings/processOrder-in-0
~~~

Tên trong URL là **binding name**, không nhất thiết là tên topic hoặc queue. Với function `processOrder`, binding input mặc định là `processOrder-in-0`.

## 6. Đọc trạng thái binding qua Actuator

GET danh sách binding giúp quan sát các binding đang được quản lý:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

Phản hồi có thể chứa thông tin như:

~~~json
[
  {
    "bindingName": "processOrder-in-0",
    "name": "processOrder-in-0",
    "group": "order-projection",
    "pausable": true,
    "state": "running",
    "paused": false,
    "input": true,
    "extendedInfo": {}
  }
]
~~~

Các trường thường cần chú ý:

| Trường | Ý nghĩa |
|---|---|
| `bindingName` | Tên binding trong Spring Cloud Stream |
| `name` | Tên binding được quản lý |
| `group` | Consumer group hoặc thông tin nhóm mà binder cung cấp |
| `pausable` | Binding có hỗ trợ pause/resume hay không |
| `state` | Trạng thái Lifecycle, thường là running hoặc stopped |
| `paused` | Consumer hiện có đang pause hay không |
| `input` | Binding là input hay output |
| `extendedInfo` | Thông tin bổ sung do binder cung cấp |

Phản hồi thực tế có thể khác theo binder và phiên bản. Ví dụ Kafka Streams binder trả `pausable: false`, `paused: false` và chỉ cung cấp STARTED/STOPPED.

Khi muốn pause, hãy kiểm tra `pausable` trước. Nếu `pausable=false`, không nên gửi lệnh PAUSED rồi coi như consumer đã dừng nhận message.

## 7. Điều khiển state bằng HTTP POST

Spring Cloud Stream dùng cùng endpoint để thay đổi state. Body là JSON có field `state`.

### Dừng binding

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"STOPPED"}'
~~~

### Khởi động lại binding

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"STARTED"}'
~~~

### Tạm dừng consumer

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

### Tiếp tục consumer

~~~bash
curl -X POST   http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"RESUMED"}'
~~~

Sau POST, đọc lại binding:

~~~bash
curl http://localhost:8080/actuator/bindings/processOrder-in-0
~~~

Đừng chỉ dựa vào HTTP status của request để kết luận broker đã ngừng hoặc tiếp tục giao message. Hãy xác nhận trạng thái binding và kiểm tra hành vi tiêu thụ thực tế.

## 8. Điều khiển bằng BindingsLifecycleController

Ngoài Actuator, Spring Cloud Stream cung cấp bean `BindingsLifecycleController` từ phiên bản 3.1. Có thể inject bean này vào service quản trị hoặc listener nội bộ.

Ví dụ:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.cloud.stream.binder.Binding;
import org.springframework.stereotype.Service;

@Service
public class StreamBindingOperations {

    private final BindingsLifecycleController lifecycle;

    public StreamBindingOperations(
            BindingsLifecycleController lifecycle) {
        this.lifecycle = lifecycle;
    }

    public boolean isRunning(String bindingName) {
        Binding<?> binding = lifecycle.queryState(bindingName);
        return binding != null && binding.isRunning();
    }

    public void stop(String bindingName) {
        lifecycle.stop(bindingName);
    }

    public void start(String bindingName) {
        lifecycle.start(bindingName);
    }

    public void pause(String bindingName) {
        lifecycle.pause(bindingName);
    }

    public void resume(String bindingName) {
        lifecycle.resume(bindingName);
    }
}
~~~

Các phương thức tiện ích tương ứng với thao tác lifecycle:

| Method | Tác dụng |
|---|---|
| `queryState(name)` | Lấy binding để kiểm tra trạng thái |
| `stop(name)` | Dừng binding |
| `start(name)` | Khởi động binding đã dừng |
| `pause(name)` | Pause nếu thành phần đích hỗ trợ |
| `resume(name)` | Resume nếu binding đã pause và có hỗ trợ |
| `changeState(name, state)` | Đổi state theo enum lifecycle được cung cấp |

Ví dụ tài liệu chính thức:

~~~java
BindingsLifecycleController controller =
    context.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("echo-in-0");

if (binding.isRunning()) {
    controller.stop("echo-in-0");
}

// Có thể dùng phương thức tiện ích:
controller.start("echo-in-0");
~~~

Nếu binding không hỗ trợ pause, lời gọi pause không tạo ra khả năng mới cho binder. Hãy kiểm tra `pausable` và log của ứng dụng. Không tự xây dựng một API quản trị trả về thành công khi thao tác nền không được hỗ trợ.

## 9. Điều khiển binding theo tên function

Tên binding mặc định được tạo từ tên function bean và vị trí input/output.

~~~java
@Bean
Function<Order, Order> normalizeOrder() {
    return order -> order.normalized();
}

@Bean
Consumer<PaymentReceived> processPayment() {
    return payment -> paymentService.process(payment);
}
~~~

Binding mặc định:

| Function | Binding |
|---|---|
| `normalizeOrder` input | `normalizeOrder-in-0` |
| `normalizeOrder` output | `normalizeOrder-out-0` |
| `processPayment` input | `processPayment-in-0` |

Nếu cấu hình destination riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder;processPayment

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw

        normalizeOrder-out-0:
          destination: orders.normalized

        processPayment-in-0:
          destination: payments.received
~~~

Tên binding vẫn là `normalizeOrder-in-0` hoặc `processPayment-in-0`. Không gửi lệnh Actuator tới `orders.raw` nếu đó chỉ là tên destination.

## 10. Khởi động consumer thủ công với autoStartup

Input binding có thuộc tính `autoStartup`. Mặc định consumer được khởi động tự động. Có thể đặt false nếu ứng dụng cần kiểm soát thời điểm bắt đầu tiêu thụ.

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            autoStartup: false
~~~

Khi `autoStartup=false`, consumer không tự khởi động cùng ứng dụng. Sau khi ứng dụng sẵn sàng, có thể dùng binding lifecycle controller hoặc Actuator với state STARTED.

Một quy trình có thể là:

1. Ứng dụng khởi động và hoàn tất kiểm tra dependency.
2. Kiểm tra database, schema, cấu hình và quyền truy cập broker.
3. Xác nhận instance đã sẵn sàng xử lý.
4. Gửi lệnh STARTED cho input binding.
5. Theo dõi backlog, lỗi và throughput.

Thuộc tính này áp dụng cho consumer binding. Nó không thay thế cơ chế quản lý readiness/liveness của Kubernetes hoặc health check của ứng dụng.

## 11. PAUSED và RESUMED trên Kafka binder thông thường

Kafka binder thông thường có thể pause consumer mà không gây partition rebalance. Điều này hữu ích khi muốn tạm dừng xử lý trong khi vẫn giữ consumer tham gia group.

Ví dụ:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

Trong lúc pause:

- Producer vẫn có thể tiếp tục gửi record.
- Consumer không tiếp tục nhận/phân phối record mới vào listener.
- Backlog/lag có thể tăng.
- Consumer có thể giữ kết nối và assignment hiện tại.
- Các xử lý đã bắt đầu trước khi pause có thể cần thời gian hoàn tất.

Tiếp tục:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/processOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"RESUMED"}'
~~~

Sau resume, consumer tiếp tục nhận record theo vị trí và trạng thái commit hiện có. Pause không tự rewind offset, không xóa backlog và không đổi consumer group.

Tài liệu Kafka binder cũng mô tả khả năng tự resume bằng cách nhận `ListenerContainerIdleEvent` qua `ApplicationListener` hoặc `@EventListener`. Tần suất phát idle event được điều khiển bởi `idleEventInterval`. Đây là lựa chọn khi muốn có quy tắc tự động tiếp tục sau khi consumer idle; phải thiết kế điều kiện resume để tránh lặp hoặc resume sai thời điểm.

## 12. Kafka Streams binder chỉ hỗ trợ STARTED và STOPPED

Kafka Streams binder có lifecycle control riêng. Tài liệu của binder nêu rõ chỉ hai phase được hỗ trợ:

- `STOPPED`
- `STARTED`

`PAUSED` và `RESUMED` không có sẵn trong Kafka Streams binder.

Ví dụ function:

~~~java
@Bean
Consumer<KStream<String, String>> logEvents() {
    return stream -> stream.foreach(
        (key, value) -> log.info("event={}", value)
    );
}
~~~

Input binding mặc định là `logEvents-in-0`. Có thể dừng và khởi động lại:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/logEvents-in-0   -H "Content-Type: application/json"   -d '{"state":"STOPPED"}'

curl -X POST http://localhost:8080/actuator/bindings/logEvents-in-0   -H "Content-Type: application/json"   -d '{"state":"STARTED"}'
~~~

Với một Kafka Streams function có nhiều binding, các binding của function đó được hỗ trợ bởi cùng một `StreamsBuilderFactoryBean`. Vì vậy, thao tác lifecycle trên một binding có thể dừng hoặc khởi động processor gắn với function đó. Hãy đọc lại endpoint và kiểm tra cả function thay vì cho rằng chỉ một input/output riêng lẻ bị ảnh hưởng.

Không dùng PAUSED/RESUMED để thay thế STARTED/STOPPED trên Kafka Streams binder. Nếu cần tạm ngừng xử lý topology, phải thiết kế cơ chế phù hợp với Kafka Streams runtime và phiên bản đang dùng.

## 13. RabbitMQ và Pulsar: xác minh theo binder

Spring Cloud Stream cung cấp giao diện lifecycle chung, nhưng pause/resume không tự động xuất hiện ở mọi broker.

Với RabbitMQ và Pulsar:

- STARTED/STOPPED được điều khiển qua lifecycle binding chung.
- Tài liệu Spring Cloud Stream hiện không liệt kê hai binder này trong danh sách binder có PAUSED/RESUMED.
- Nếu gửi PAUSED tới binding không hỗ trợ, framework có thể ghi cảnh báo; không được coi đó là bằng chứng consumer đã dừng.
- Khi cần ngừng tiêu thụ, có thể dùng STOPPED nếu chấp nhận tác động vòng đời của binder.
- Nếu muốn pause mà giữ subscription/consumer state, phải xác minh API native của binder và cách tích hợp được hỗ trợ trong phiên bản đang chạy.

Không dùng lệnh quản trị broker để xóa queue, subscription hoặc consumer group chỉ nhằm thay thế pause. Những thao tác đó có thể làm mất backlog, cursor hoặc trạng thái xác nhận.

## 14. Điều khiển một binding trong ứng dụng có nhiều binder

Một ứng dụng có thể dùng nhiều binder cùng lúc, ví dụ một input đọc Kafka và một output ghi RabbitMQ. Mỗi binding có tên riêng và có thể gắn với binder khác nhau.

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder

    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          binder: kafka

        enrichOrder-out-0:
          destination: orders.enriched
          binder: rabbit
~~~

Điều khiển input:

~~~bash
curl -X POST http://localhost:8080/actuator/bindings/enrichOrder-in-0   -H "Content-Type: application/json"   -d '{"state":"PAUSED"}'
~~~

Lệnh này chỉ có ý nghĩa pause nếu input Kafka binder đang dùng hỗ trợ. Output Rabbit binding không tự động bị pause cùng input. Nếu muốn dừng output hoặc toàn bộ function, cần điều khiển đúng binding và đánh giá ảnh hưởng của việc ngừng publish.

Trong ứng dụng nhiều binder, luôn kiểm tra thông tin binding trước khi thao tác. Không suy ra binder từ tên topic hoặc tên function.

## 15. Điều khiển trên nhiều instance hoặc pod

Binding lifecycle controller hoạt động trong application context của một instance. Nếu service có nhiều replica, một POST tới một pod chỉ điều khiển binding trong pod đó.

Ví dụ ba replica:

~~~text
order-projection deployment
  |
  +-- pod A: processOrder-in-0
  +-- pod B: processOrder-in-0
  +-- pod C: processOrder-in-0
~~~

Gửi PAUSED tới pod A không tự pause pod B và pod C. Với Kafka group, hai consumer còn lại có thể tiếp tục nhận các partition mà chúng sở hữu; consumer A giữ assignment ở trạng thái pause nếu binder hỗ trợ.

Nếu muốn dừng toàn bộ service:

1. Xác định tất cả instance đang chạy.
2. Gửi lệnh lifecycle tới từng instance hoặc dùng control plane có khả năng fan-out.
3. Xác nhận trạng thái từng binding.
4. Theo dõi backlog và xử lý đang dở.
5. Chỉ hoàn tất bảo trì khi toàn bộ instance ở trạng thái mong muốn.

Không dùng một lần gọi Actuator tới load balancer rồi giả định mọi pod đã nhận lệnh. Load balancer thường chỉ chuyển request tới một instance.

Nếu dùng Kubernetes, có thể kết hợp lifecycle binding với rollout strategy và readiness. Tuy nhiên, readiness không tự pause binding; hai cơ chế giải quyết hai vấn đề khác nhau.

## 16. Quy trình vận hành an toàn

### Tạm dừng để bảo trì downstream

Với Kafka binder thông thường:

1. Kiểm tra binding có `pausable=true`.
2. Ghi nhận consumer lag và tốc độ xử lý hiện tại.
3. Gửi PAUSED.
4. Đọc lại binding để xác nhận `paused=true`.
5. Theo dõi backlog tăng và các xử lý đang dở.
6. Thực hiện bảo trì downstream.
7. Xác nhận dependency đã sẵn sàng.
8. Gửi RESUMED.
9. Kiểm tra `paused=false`, lag giảm và throughput trở lại.

### Dừng binding để thay đổi cấu hình

1. Xác định chính xác binding name.
2. Đánh giá tác động lên consumer group và rebalance.
3. Dừng hoặc drain các công việc đang xử lý theo khả năng ứng dụng.
4. Gửi STOPPED.
5. Xác nhận binding không còn running.
6. Thay đổi cấu hình theo quy trình triển khai.
7. Gửi STARTED hoặc khởi động lại ứng dụng theo kế hoạch.
8. Kiểm tra binding, consumer group và backlog.

Không giả định STOPPED đồng nghĩa mọi message đang xử lý đã hoàn tất hoặc offset đã commit. Hãy kiểm tra acknowledgment mode, transaction, retry và thời gian xử lý của binder cụ thể.

## 17. Bảo vệ Actuator binding endpoint

Endpoint POST có thể làm ngừng hoặc tiếp tục tiêu thụ message. Đây là API quản trị có ảnh hưởng trực tiếp đến vận hành.

Các nguyên tắc:

- Chỉ expose endpoint bindings khi cần thiết.
- Không expose toàn bộ Actuator endpoint chỉ để bật binding control.
- Giới hạn truy cập bằng Spring Security hoặc lớp xác thực của nền tảng.
- Dùng network policy, management port hoặc mạng nội bộ cho endpoint quản trị.
- Chỉ cấp quyền cho nhóm vận hành được phép thay đổi lifecycle.
- Ghi audit log gồm binding name, state cũ, state mới, actor, thời điểm và lý do.
- Bảo vệ endpoint trước request giả mạo hoặc lặp.
- Kiểm tra các thông tin nhạy cảm trong extended binding properties.

Binding Actuator có thể trả thông tin cấu hình bổ sung. Tài liệu Spring Cloud Stream khuyến nghị dùng `SanitizingFunction` của Spring Boot để che các giá trị nhạy cảm như `sasl.jaas.config` hoặc thông tin SSL.

Ví dụ bean che giá trị SASL:

~~~java
import org.springframework.boot.actuate.endpoint.SanitizingFunction;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ActuatorSanitizationConfiguration {

    @Bean
    SanitizingFunction sanitizingFunction() {
        return data -> {
            if ("sasl.jaas.config".equals(data.getKey())) {
                return data.withValue("******");
            }
            return data;
        };
    }
}
~~~

Hãy rà soát các key nhạy cảm khác mà ứng dụng sử dụng. Không ghi token, password hoặc private key vào log khi điều khiển binding.

## 18. Kiểm thử binding lifecycle

Kiểm thử cần xác minh cả state trong ứng dụng và hành vi nhận message.

### Kiểm tra STARTED và STOPPED

Có thể lấy controller từ Spring context:

~~~java
BindingsLifecycleController controller =
    context.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("processOrder-in-0");

assertThat(binding.isRunning()).isTrue();

controller.stop("processOrder-in-0");

Binding<?> stopped = controller.queryState("processOrder-in-0");
assertThat(stopped.isRunning()).isFalse();

controller.start("processOrder-in-0");

Binding<?> started = controller.queryState("processOrder-in-0");
assertThat(started.isRunning()).isTrue();
~~~

Ví dụ dùng AssertJ. Trong test thực tế, cần khởi tạo application context và binder phù hợp, đồng thời chờ trạng thái bất đồng bộ nếu binder cần thời gian khởi động.

### Kiểm thử PAUSED và RESUMED với Kafka binder

Với Kafka binder thông thường:

1. Khởi chạy Kafka broker thử nghiệm.
2. Tạo input binding và consumer group.
3. Gửi một số message và xác nhận consumer nhận được.
4. Xác nhận binding có `pausable=true`.
5. Gửi PAUSED.
6. Gửi thêm message vào topic.
7. Xác nhận ứng dụng tạm ngừng nhận message mới trong thời gian pause.
8. Kiểm tra consumer group không trải qua partition rebalance do thao tác pause.
9. Gửi RESUMED.
10. Xác nhận consumer tiếp tục nhận backlog.

Để xác minh không có rebalance, có thể quan sát assignment và rebalance listener của Spring Kafka, không chỉ kiểm tra số message nhận được.

### Kiểm thử binder không hỗ trợ pause

Với binder không có pause/resume:

- Xác nhận `pausable=false` hoặc thông tin tương đương.
- Gửi lệnh PAUSED trong môi trường test.
- Kiểm tra warning log.
- Xác nhận không ghi nhận consumer đã pause nếu binder không hỗ trợ.
- Dùng STOPPED/STARTED theo semantics mà binder cung cấp.

### Kiểm thử Kafka Streams binder

Với Kafka Streams binder:

- Xác nhận binding state ban đầu là running.
- STOPPED và kiểm tra processor ngừng xử lý.
- STARTED và kiểm tra processor hoạt động lại.
- Kiểm tra endpoint hiển thị `pausable=false`.
- Không viết test kỳ vọng PAUSED/RESUMED hoạt động.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thấy /actuator/bindings | Thiếu Actuator hoặc Web/WebFlux | Thêm dependency phù hợp |
| Endpoint trả 404 | Chưa expose `bindings` | Cấu hình management exposure |
| POST trả lỗi bảo mật | Spring Security/CSRF chặn request | Cấp quyền quản trị và cấu hình bảo mật phù hợp |
| Không tìm thấy binding | Dùng destination thay cho binding name | Kiểm tra function binding name |
| PAUSED không có hiệu lực | Binder hoặc endpoint không hỗ trợ Pausable | Kiểm tra `pausable` và tài liệu binder |
| Log có warning khi pause | Thành phần đích không hỗ trợ pause | Dùng STOPPED hoặc giải pháp riêng của binder |
| Kafka Streams không pause | Kafka Streams binder chỉ hỗ trợ STARTED/STOPPED | Dùng lifecycle phase được hỗ trợ |
| Một pod pause nhưng service vẫn xử lý | Các replica khác vẫn đang chạy | Điều khiển tất cả instance nếu cần dừng toàn bộ |
| STOPPED gây rebalance | Consumer rời group | Dùng PAUSED nếu Kafka binder hỗ trợ và mục tiêu là giữ assignment |
| Resume nhưng không thấy message | Binding name sai, consumer lỗi hoặc không có backlog | Kiểm tra state, log, offset và broker |
| Output binding không dừng theo input | Mỗi binding có lifecycle riêng | Điều khiển đúng output hoặc toàn function theo binder |
| Actuator trả dữ liệu cấu hình nhạy cảm | Extended info chưa được sanitize | Cấu hình SanitizingFunction |

## 20. Checklist trước khi thao tác production

| Hạng mục | Câu hỏi |
|---|---|
| Binding name | Đã xác định đúng input/output binding chưa? |
| Binder | Binding đang dùng Kafka, Kafka Streams, RabbitMQ, Pulsar hay Solace? |
| Capability | Binding có hỗ trợ pause/resume không? |
| State hiện tại | Đang running, stopped hay paused? |
| Phạm vi instance | Lệnh áp dụng một pod hay tất cả replica? |
| Consumer group | STOPPED có làm consumer rời group và rebalance không? |
| In-flight work | Có message đang xử lý hoặc transaction chưa hoàn tất không? |
| Backlog | Backlog/lag có thể tăng tới mức nào trong thời gian pause? |
| Recovery | Dùng STARTED hay RESUMED để khôi phục đúng trạng thái? |
| Security | Ai được phép gọi POST endpoint? |
| Audit | Có lưu actor, lý do và thời điểm thay đổi không? |
| Verification | Đã GET lại binding và xác nhận broker behavior chưa? |

## 21. Bài thực hành và tiêu chí hoàn thành

Tạo một Spring Cloud Stream application với function `processOrder` đọc từ binding `processOrder-in-0`.

1. Thêm Actuator và Web dependency.
2. Expose endpoint `bindings`.
3. Khởi động ứng dụng và gọi GET `/actuator/bindings`.
4. Xác định binding name, destination, group, state và khả năng pausable.
5. Với Kafka binder thông thường, gửi PAUSED và xác nhận consumer tạm ngừng nhận record.
6. Gửi thêm message vào topic trong lúc pause và quan sát backlog.
7. Gửi RESUMED và xác nhận consumer xử lý tiếp.
8. Gửi STOPPED rồi STARTED và so sánh với pause/resume.
9. Lặp lại trên Kafka Streams binder, xác nhận chỉ STARTED/STOPPED được hỗ trợ.
10. Thử kiểm tra RabbitMQ hoặc Pulsar binder theo phiên bản dự án, không giả định PAUSED/RESUMED.
11. Chạy hai replica và chứng minh một request tới một pod chỉ điều khiển instance đó.
12. Bảo vệ endpoint bằng authentication/authorization và kiểm tra dữ liệu nhạy cảm được sanitize.
13. Viết integration test xác nhận state và hành vi broker.

Hoàn thành bài khi có thể phân biệt STOPPED với PAUSED; chọn đúng STARTED hoặc RESUMED để khôi phục; điều khiển binding bằng Actuator và BindingsLifecycleController; xác định capability của Kafka, Kafka Streams, RabbitMQ và Pulsar binder; và xây dựng quy trình thao tác an toàn trên nhiều instance.

## 22. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html) — Actuator endpoint, BindingLifecycleController, các trạng thái lifecycle, bảo vệ và sanitize thông tin.
- [Spring Cloud Stream 5.0 — Pausing and Resuming the Consumer](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/pause_resume.html) — pause/resume Kafka consumer mà không gây partition rebalance.
- [Spring Cloud Stream — Kafka Streams Binder: Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html) — giới hạn Kafka Streams binder chỉ hỗ trợ STARTED/STOPPED.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — binding name, consumer properties và autoStartup.
- [Spring Integration — Pausable API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/core/Pausable.html) — hợp đồng pause/resume của endpoint và semantics kết nối.

