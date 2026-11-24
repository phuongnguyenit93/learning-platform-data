# Graceful shutdown và xử lý thông điệp đang thực thi

Một ứng dụng Spring Cloud Stream thường chạy liên tục để nhận message từ Kafka, RabbitMQ hoặc Pulsar. Khi triển khai phiên bản mới, scale down, node bảo trì hoặc container bị thay thế, tiến trình có thể nhận tín hiệu dừng trong lúc một consumer đang xử lý message. Nếu đóng kết nối quá sớm, message có thể được giao lại, offset chưa được commit, publish đầu ra chưa hoàn tất hoặc side effect nghiệp vụ bị thực hiện lặp.

Graceful shutdown là quá trình ngừng nhận công việc mới, cho phép công việc đang thực thi kết thúc trong một khoảng thời gian có giới hạn, hoàn tất các xác nhận giao nhận cần thiết rồi mới đóng tài nguyên. Nó không tự biến pipeline thành exactly-once. Ứng dụng vẫn cần idempotency, retry có giới hạn và cơ chế phục hồi phù hợp với broker.

## 1. Điều gì xảy ra khi ứng dụng dừng?

Một consumer xử lý message thường có các bước:

1. Broker giao message hoặc record cho consumer.
2. Binder chuyển message tới Function/Consumer.
3. Code nghiệp vụ gọi database, HTTP service hoặc hệ thống khác.
4. Ứng dụng hoàn tất side effect.
5. Binder/client acknowledge message hoặc commit offset.
6. Nếu có output, producer gửi message tiếp theo.

Shutdown có thể xảy ra ở bất kỳ bước nào. Ví dụ database đã commit nhưng consumer chưa acknowledge; broker có thể giao lại message. Nếu consumer acknowledge trước khi database commit, message có thể mất khỏi luồng chính trong khi nghiệp vụ chưa hoàn tất.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Binder / Consumer
    participant S as Business Service
    participant D as Database
    participant P as Producer / Output
    B->>C: Deliver event
    C->>S: Invoke handler
    S->>D: Commit business change
    Note over C,S: SIGTERM có thể đến tại đây
    S-->>C: Handler completed
    C->>B: ACK / commit offset
    C->>P: Publish output (nếu có)
    P-->>C: Publish confirmation
~~~

Thứ tự thực tế giữa commit, acknowledge và publish phụ thuộc thiết kế ứng dụng, binder và transaction boundary. Sơ đồ biểu diễn một luồng mong muốn để thảo luận; không phải mọi binder đều cung cấp một transaction bao trùm database, input broker và output broker.

## 2. Graceful shutdown có những mục tiêu nào?

Một quy trình dừng an toàn cần đạt các mục tiêu:

- Không nhận thêm request hoặc message mới khi instance bắt đầu rời hệ thống.
- Không làm mất message đang được broker giữ và chưa được xác nhận.
- Cho phép handler đang chạy hoàn tất nếu còn đủ thời gian.
- Hoàn tất database transaction và các side effect cần thiết.
- Chỉ acknowledge/commit sau khi công việc đạt ranh giới hoàn tất đã định nghĩa.
- Hoàn tất publish đầu ra đang chờ hoặc để lại trạng thái có thể phục hồi.
- Đóng consumer, producer, connection pool, executor và tài nguyên theo thứ tự phù hợp.
- Thoát trước deadline do nền tảng cấp; nếu không thể, để broker giao lại message và ứng dụng xử lý lặp an toàn.

Không thể bảo đảm mọi công việc đều hoàn tất khi tiến trình bị kill -9, máy mất điện hoặc node gặp sự cố đột ngột. Thiết kế đúng phải coi graceful shutdown là cơ hội giảm gián đoạn, còn độ bền dữ liệu đến từ broker acknowledgment, transaction, outbox và idempotency.

## 3. Phân biệt readiness, web server shutdown và message consumer shutdown

Ba cơ chế thường bị nhầm lẫn:

| Cơ chế | Điều khiển | Không tự làm điều gì? |
|---|---|---|
| Readiness | Instance có được xem là sẵn sàng nhận traffic mới hay không | Không tự dừng Kafka consumer hoặc Rabbit/Pulsar listener |
| Graceful web server shutdown | Ngừng nhận HTTP request mới và chờ request đang xử lý | Không tự flush producer hoặc drain message consumer |
| Binder/listener lifecycle | Dừng hoặc pause việc nhận message theo khả năng binder | Không tự bảo đảm side effect nghiệp vụ và output đã commit |

Spring Boot hỗ trợ graceful shutdown cho embedded web server:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

server.shutdown=graceful áp dụng cho web server được Spring Boot quản lý. Nó không phải công tắc chung để tự drain mọi message của Spring Cloud Stream. spring.lifecycle.timeout-per-shutdown-phase đặt thời gian chờ cho từng lifecycle phase; cần cấu hình dựa trên thời gian xử lý tối đa và deadline của nền tảng.

Khi ApplicationContext đóng, các bean có lifecycle được dừng theo phase. Spring Cloud Stream và binder quản lý lifecycle của binding/consumer. Hành vi dừng chi tiết phụ thuộc binder implementation và phiên bản thư viện. Nếu cần pause binding trước, chờ in-flight counter rồi mới cho binder đóng, hãy dùng cơ chế lifecycle/binding control được hỗ trợ bởi phiên bản đang dùng và kiểm thử thứ tự stop thực tế.

### 3.1. Readiness không phải công tắc consumer

Đặt readiness thành REFUSING_TRAFFIC giúp load balancer hoặc nền tảng ngừng gửi HTTP traffic mới tới Pod. Một Kafka consumer hoặc Rabbit listener có thể vẫn tiếp tục nhận message vì nó kết nối trực tiếp tới broker.

Với dịch vụ vừa có HTTP endpoint vừa có message binding, quy trình drain cần điều khiển cả hai:

1. Đánh dấu instance không nhận HTTP traffic mới.
2. Ngừng nhận message mới bằng binding/listener lifecycle phù hợp.
3. Chờ message đang thực thi.
4. Đóng ứng dụng.

Không dùng readiness DOWN như bằng chứng rằng consumer đã ngừng nhận message.

## 4. Vòng đời dừng của Spring

Spring quản lý các bean Lifecycle và SmartLifecycle khi context khởi động hoặc đóng. SmartLifecycle hỗ trợ callback trong stop(Runnable) để một thành phần hoàn tất công việc dừng bất đồng bộ trước khi báo đã dừng.

Một số nguyên tắc:

- Khởi tạo dependency nghiệp vụ trước khi bắt đầu nhận message.
- Khi dừng, ngừng intake trước khi đóng database/client mà handler đang sử dụng.
- Dành đủ thời gian cho listener đang chạy và callback publish.
- Không tự đóng connection factory hoặc producer do binder quản lý nếu chưa hiểu quyền sở hữu lifecycle.
- Nếu có custom lifecycle bean, phải xác định phase của nó so với binder và dependency.

Lifecycle phase có ý nghĩa với thứ tự start/stop: các thành phần có phase cao thường được start muộn hơn và stop sớm hơn. Không chọn một giá trị phase tùy ý rồi giả định binder sẽ tự chờ custom bean. Hãy xem lifecycle phase của binder ở đúng phiên bản và viết integration test xác minh thứ tự.

### 4.1. Vì sao chỉ dùng @PreDestroy có thể chưa đủ?

@PreDestroy phù hợp để giải phóng tài nguyên đồng bộ, nhanh và cục bộ. Nó không phải lúc nào cũng là nơi phù hợp để điều phối một quá trình drain kéo dài:

- Có thể chạy khi một số thành phần lifecycle đã bắt đầu dừng.
- Không cung cấp callback lifecycle bất đồng bộ như SmartLifecycle.stop(Runnable).
- Một lời gọi chờ vô hạn có thể vượt termination deadline.
- Không tự dừng việc broker giao message mới.

Nếu cần drain có thời hạn, hãy điều phối trong lifecycle phase phù hợp, dùng binder/listener API để ngừng intake, theo dõi in-flight work và kết thúc trước deadline. @PreDestroy chỉ nên xử lý phần cleanup cuối cùng còn lại.

## 5. Quy trình shutdown theo từng giai đoạn

~~~mermaid
flowchart TD
    A["Nhận SIGTERM / yêu cầu drain"] --> B["Đánh dấu REFUSING_TRAFFIC"]
    B --> C["Ngừng nhận HTTP và message mới"]
    C --> D["Theo dõi in-flight handlers"]
    D --> E{"Đã hoàn tất trước deadline?"}
    E -- Có --> F["Hoàn tất ACK / offset / publish"]
    E -- Không --> G["Dừng chờ theo timeout"]
    G --> H["Để message chưa ACK được giao lại"]
    F --> I["Đóng binder và dependency"]
    H --> I
    I --> J["Thoát tiến trình"]
~~~

Một quy trình có thể chia thành các bước sau:

**Giai đoạn 1 — bắt đầu drain**

- Ghi nhận tín hiệu dừng một lần; tránh nhiều luồng cùng khởi động drain.
- Đánh dấu readiness không nhận traffic mới.
- Từ chối hoặc chuyển hướng request mới theo contract của HTTP API.
- Ngừng tạo tác vụ nền hoặc lịch phát message mới.

**Giai đoạn 2 — dừng intake**

- Pause/stop binding hoặc listener theo API binder hỗ trợ.
- Ngừng nhận record mới hoặc message delivery mới.
- Không đóng database connection pool khi handler còn cần dùng.
- Kiểm tra các delivery đã được broker gửi trước khi lệnh stop có hiệu lực.

**Giai đoạn 3 — drain in-flight**

- Đếm handler đang chạy và thời gian chạy lâu nhất.
- Chờ database transaction hoặc downstream call hoàn tất.
- Hoàn tất publish output cần thiết.
- Để framework thực hiện ack/commit theo chế độ đã cấu hình.

**Giai đoạn 4 — deadline**

- Dừng chờ khi hết thời gian drain.
- Không acknowledge công việc chưa hoàn tất chỉ để shutdown nhanh.
- Đóng consumer để broker có thể giao lại message chưa được xác nhận.
- Đảm bảo xử lý lặp an toàn khi instance mới nhận lại message.

**Giai đoạn 5 — cleanup**

- Đóng producer do ứng dụng tự quản lý sau khi flush các send đang chờ.
- Để binder đóng producer/consumer/connection do binder sở hữu.
- Đóng executor, database pool và client downstream sau cùng.
- Ghi log thời điểm drain bắt đầu/kết thúc và số công việc chưa hoàn tất.

## 6. Theo dõi công việc đang thực thi

Một in-flight counter cho biết có bao nhiêu handler đã bắt đầu nhưng chưa kết thúc. Counter giúp quan sát tiến độ drain; nó không thay thế cơ chế pause/stop listener của binder.

Ví dụ một tracker đơn giản:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class InFlightTracker {

    private int active;
    private boolean accepting = true;

    public synchronized Ticket enter() {
        if (!accepting) {
            throw new ShutdownInProgressException();
        }
        active++;
        return new Ticket(this);
    }

    public synchronized void stopAccepting() {
        accepting = false;
        notifyAll();
    }

    public synchronized int activeCount() {
        return active;
    }

    public synchronized boolean awaitDrained(Duration timeout)
            throws InterruptedException {
        long remaining = timeout.toNanos();
        long deadline = System.nanoTime() + remaining;

        while (active > 0 && remaining > 0) {
            TimeUnit.NANOSECONDS.timedWait(this, remaining);
            remaining = deadline - System.nanoTime();
        }
        return active == 0;
    }

    private synchronized void leave() {
        active--;
        if (active == 0) {
            notifyAll();
        }
    }

    public static final class Ticket implements AutoCloseable {
        private final InFlightTracker owner;
        private final AtomicBoolean closed = new AtomicBoolean();

        private Ticket(InFlightTracker owner) {
            this.owner = owner;
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                owner.leave();
            }
        }
    }

    public static final class ShutdownInProgressException
            extends RuntimeException {
        public ShutdownInProgressException() {
            super("Application is draining");
        }
    }
}
~~~

Handler dùng ticket trong try-with-resources để giảm counter cả khi xử lý thành công hoặc ném exception:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderAccepted(String eventId, String orderId) {}

@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderAccepted> processOrder(
            InFlightTracker tracker,
            OrderService orderService) {
        return event -> {
            try (InFlightTracker.Ticket ignored = tracker.enter()) {
                orderService.processAndCommit(event);
            }
        };
    }
}
~~~

processAndCommit phải chỉ trả về sau khi ranh giới nghiệp vụ đã hoàn tất. Trong triển khai thực tế, cần phối hợp stopAccepting() với việc pause/stop binding để broker không tiếp tục giao message. Nếu một callback đến sau khi tracker đã đóng intake, exception phải được xử lý như tình trạng shutdown tạm thời theo chính sách binder; tuyệt đối không bắt exception rồi trả về bình thường vì như vậy có thể khiến message bị acknowledge dù chưa xử lý.

Tracker trên minh họa cách đếm và chờ có timeout. Nó không tự đăng ký thành phần lifecycle, không điều khiển broker và không bảo đảm rằng mọi callback bất đồng bộ đã kết thúc. Nếu handler gửi tác vụ sang executor rồi trả về, ticket phải bao trùm cả thời gian tác vụ thực sự hoàn tất, không chỉ thời gian submit.

## 7. Đặt deadline drain

Thời gian drain phải nhỏ hơn thời gian nền tảng cho phép Pod kết thúc. Ví dụ:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 50s

server:
  shutdown: graceful
~~~

Kubernetes:

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
~~~

Các giá trị trên chỉ minh họa. Cần chừa thời gian cho:

- Hook trước khi SIGTERM được gửi, nếu có.
- Readiness propagation và ngừng traffic mới.
- Listener stop và chờ in-flight handler.
- Commit/ack và flush output.
- Đóng connection pool và JVM.

Không đặt timeout lifecycle đúng bằng terminationGracePeriodSeconds. Khi hết grace period, kubelet có thể gửi SIGKILL; ứng dụng không còn cơ hội cleanup. Hãy giữ một khoảng đệm đủ để kết thúc các phase cuối.

Lưu ý `timeout-per-shutdown-phase` là ngân sách cho từng phase, không phải tổng thời gian shutdown của toàn ứng dụng. Nếu có nhiều phase chờ, tổng thời gian có thể lớn hơn giá trị cấu hình. Hãy cộng ngân sách của các phase thực tế, thời gian preStop và cleanup rồi bảo đảm tổng đó vẫn nằm trong termination grace period.

### 7.1. Thời gian xử lý tối đa phải có giới hạn

Nếu một handler có thể treo vô hạn khi gọi HTTP hoặc database, không thể tính được thời gian drain. Đặt timeout cho:

- HTTP client connect/read/request.
- Database query, lock wait và transaction.
- Future hoặc executor task.
- Retry delay và tổng thời gian retry.
- External process hoặc file operation.

Timeout của một dependency phải phù hợp với deadline còn lại. Nếu drain còn 10 giây, không bắt đầu một request downstream có timeout 60 giây.

## 8. Kubernetes gửi tín hiệu dừng như thế nào?

Khi Pod bị xóa hoặc thay thế, Kubernetes bắt đầu quá trình termination. preStop hook (nếu khai báo) chạy trước khi container nhận SIGTERM và thời gian hook được tính vào terminationGracePeriodSeconds. Sau đó runtime gửi SIGTERM tới process; khi grace period hết, container còn chạy có thể bị SIGKILL.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: example/order-consumer:1.0.0
          ports:
            - name: management
              containerPort: 8081
          lifecycle:
            preStop:
              httpGet:
                path: /internal/drain
                port: management
~~~

/internal/drain là endpoint do ứng dụng tự xây dựng, không phải endpoint mặc định của Spring Boot. Endpoint này cần được bảo vệ, chỉ cho phép kubelet hoặc mạng quản trị gọi và phải kích hoạt quy trình drain thật: readiness, ngừng intake message và chờ theo deadline. Nếu không có endpoint drain riêng, hãy dùng cơ chế lifecycle tự xử lý SIGTERM và không khai báo hook giả định rằng readiness tự dừng consumer.

Container image nên chạy Java process theo dạng exec để process nhận SIGTERM đúng cách. Nếu shell script làm PID 1 mà không forward signal, JVM có thể không nhận tín hiệu như mong đợi; dùng exec trong entrypoint hoặc init process phù hợp.

## 9. Kafka: dừng consumer, commit offset và rebalance

Kafka consumer đọc record theo partition và theo dõi tiến độ bằng offset của consumer group. Khi ứng dụng dừng:

1. Listener container ngừng poll hoặc ngừng nhận record mới theo lifecycle.
2. Record đang được listener xử lý cần hoàn tất hoặc bị bỏ dở.
3. Offset được commit theo acknowledgment/commit mode đã cấu hình.
4. Consumer rời group; partition có thể được assign cho consumer khác.
5. Record chưa được commit có thể được consumer mới đọc lại.

Với Spring Cloud Stream Kafka binder, binder quản lý listener container và tương tác với Spring Kafka. Không tự tạo một KafkaConsumer khác để commit offset cho binding nếu chưa thiết kế rõ quyền sở hữu.

### 9.1. Commit sau khi xử lý

Mục tiêu thường là chỉ commit offset sau khi handler đã hoàn thành công việc cần bảo vệ. Nếu process chết sau khi database commit nhưng trước offset commit, record có thể được đọc lại. Vì thế database operation phải idempotent theo event ID hoặc business key.

Nếu commit offset trước khi side effect hoàn tất, crash có thể làm record không được giao lại dù nghiệp vụ chưa hoàn tất. Cần chọn acknowledgment semantics dựa trên yêu cầu mất/duplicate message chấp nhận được.

### 9.2. Poll interval và handler chạy lâu

Kafka có max.poll.interval.ms để giới hạn khoảng thời gian giữa các lần poll. Nếu handler đồng bộ mất quá lâu, consumer có thể bị xem là không tiến triển và partition bị rebalance trước khi handler hoàn tất. Khi đó commit có thể thất bại và record có thể được giao lại.

Các biện pháp:

- Giữ thời gian xử lý trong giới hạn đã đo.
- Điều chỉnh max.poll.interval.ms và max.poll.records theo tải thực tế.
- Tránh đưa toàn bộ batch lớn vào một handler kéo dài.
- Nếu xử lý bất đồng bộ, phải kiểm soát offset/ack theo đúng thứ tự partition và semantics của container.
- Theo dõi rebalance, commit failures và lag.

Không tăng max.poll.interval.ms để che một handler bị treo. Hãy giới hạn dependency timeout và quan sát thời gian xử lý p95/p99.

### 9.3. Rebalance và duplicate

Khi Pod rời consumer group, partition được phân phối lại. Một record đã xử lý nhưng chưa commit có thể được consumer khác nhận. Điều này là một phần của at-least-once processing.

Producer idempotence giúp chống duplicate do retry ở producer trong phạm vi Kafka protocol; nó không làm cho side effect database của consumer exactly-once. Kafka transaction có thể phối hợp consume-transform-produce trong Kafka, nhưng không tự bao trùm một database hoặc HTTP API tùy ý.

### 9.4. Batch listener

Nếu một poll trả về nhiều record, cần xác định record nào đã hoàn tất trước khi dừng. Commit cả batch sau khi chỉ một phần record thành công có thể bỏ qua record lỗi; không commit batch có thể khiến record đã thành công bị giao lại. Dùng error handling, batch acknowledgment và retry semantics của binder/container thay vì tự ước lượng offset.

## 10. RabbitMQ: consumer cancel và unacknowledged delivery

RabbitMQ theo dõi delivery chưa được acknowledge. Khi consumer channel/connection đóng, các delivery còn unacknowledged thường được đưa trở lại trạng thái có thể giao cho consumer khác. Consumer mới có thể nhận lại message đó.

Một quy trình graceful shutdown cần:

- Ngừng nhận delivery mới bằng cách dừng/cancel listener consumer.
- Cho callback đang chạy hoàn tất.
- Acknowledge sau khi nghiệp vụ commit thành công.
- Để delivery chưa được ack được requeue khi channel đóng.
- Không dùng auto-ack nếu yêu cầu cần bảo vệ message trong thời gian xử lý.

### 10.1. Prefetch ảnh hưởng đến số message đang giữ

Prefetch giới hạn số delivery chưa được acknowledge mà broker có thể gửi trước cho consumer. Prefetch quá lớn có thể khiến một instance giữ nhiều message trong bộ nhớ khi shutdown, trong khi prefetch quá thấp có thể làm giảm throughput.

Ví dụ: consumer có prefetch 100 và đang xử lý song song 20 message. Khi Pod bị dừng, cần tính cả message đang chạy và message đã giao nhưng còn nằm trong buffer của listener. Nếu channel đóng trước khi chúng được ack, các message chưa ack có thể được giao lại.

Điều chỉnh prefetch dựa trên:

- Thời gian xử lý trung bình và p99.
- Concurrency thực tế của listener.
- Bộ nhớ mỗi message.
- Số message unacked khi shutdown.
- Khả năng chịu duplicate của business handler.

### 10.2. Ack và side effect

Nếu dùng manual acknowledgment, chỉ gửi ack sau khi business transaction hoàn tất. Với container-managed acknowledgment, hiểu chính xác chế độ ack và exception behavior của Spring AMQP/Rabbit binder.

Không ack trong finally block. Nếu handler ném exception do database timeout, ack trong finally sẽ xác nhận message dù nghiệp vụ chưa hoàn tất.

Khi listener dừng, Spring AMQP container có cơ chế stop consumer và chờ callback theo lifecycle của container. Timeout, requeue và hành vi force stop có thể phụ thuộc loại container và phiên bản Spring AMQP. Hãy kiểm thử trên đúng loại listener container đang dùng; không suy luận từ một cấu hình RabbitMQ khác.

## 11. Pulsar: acknowledgment, negative acknowledgment và redelivery

Pulsar subscription theo dõi message đã acknowledge. Khi consumer đóng, message chưa được acknowledge vẫn chưa hoàn tất ở subscription và có thể được giao lại theo cơ chế redelivery của subscription/client.

Các khái niệm cần phân biệt:

- Individual acknowledgment: xác nhận một message.
- Cumulative acknowledgment: xác nhận message và các message trước đó trong subscription mode hỗ trợ.
- Negative acknowledgment: yêu cầu broker giao lại message theo chính sách redelivery.
- Acknowledgment timeout: message chưa ack trong thời gian cấu hình có thể được giao lại.
- Batch acknowledgment: một batch có thể được xác nhận theo semantics của client.

Với shutdown, hãy dừng consumer nhận message mới, chờ handler đang chạy, ack message đã hoàn tất và để message chưa ack được redeliver. Không acknowledge trước khi side effect hoàn tất chỉ để giảm backlog.

Không phải mọi subscription type đều hỗ trợ cùng kiểu acknowledgment hoặc cùng semantics cumulative ack. Kiểm tra loại subscription (Exclusive, Failover, Shared, Key_Shared), batch settings và Pulsar client version.

### 11.1. Ack timeout không phải shutdown timeout

Ack timeout là chính sách redelivery của broker/client cho message chưa được xác nhận. Shutdown timeout là thời gian tiến trình được phép drain trước khi bị kết thúc. Hai giá trị giải quyết vấn đề khác nhau.

Nếu ack timeout ngắn hơn thời gian xử lý hợp lệ, message có thể được giao lại khi consumer cũ vẫn đang xử lý. Nếu shutdown timeout quá ngắn, ứng dụng có thể bị kill trước khi hoàn tất. Cấu hình cả hai theo phân phối thời gian xử lý và chính sách duplicate.

## 12. Không để công việc bất đồng bộ thoát khỏi ranh giới ack

Một lỗi thường gặp là function nhận message, submit task vào executor rồi trả về ngay:

~~~java
@Bean
Consumer<OrderAccepted> unsafeConsumer(
        Executor executor, OrderService orderService) {
    return event -> executor.execute(() -> orderService.process(event));
}
~~~

Binder có thể coi handler đã hoàn tất khi execute() trả về, trong khi task nghiệp vụ vẫn chạy. Nếu message được ack/commit rồi process bị kill, task có thể mất và broker không giao lại message.

Nếu xử lý bất đồng bộ, cần giữ acknowledgment boundary cho đến khi task thực sự hoàn tất. Có thể dùng API hỗ trợ asynchronous result của framework/binder ở phiên bản tương ứng, hoặc thiết kế worker queue bền vững riêng. Không giả định mọi Consumer trả về void có thể theo dõi future được submit bên trong.

Ví dụ về nguyên tắc: chỉ tăng in-flight counter khi bắt đầu task, và chỉ giảm sau khi future hoàn tất. Khi shutdown, ngừng submit task mới, chờ các future đang chạy trong deadline; task chưa hoàn tất phải giữ trạng thái có thể retry và không được ack sớm.

## 13. Producer đang gửi output khi shutdown

Consumer có thể hoàn tất input nhưng còn đang gửi output tới broker khác. Cần phân biệt:

- Message đã được tạo trong memory.
- Send đã được submit cho producer.
- Broker đã nhận và xác nhận publish.
- Consumer downstream đã xử lý output.

Các trạng thái này không tương đương. Nếu ứng dụng dùng producer client trực tiếp, cần flush hoặc chờ future/callback send hoàn tất trước khi close producer. Với producer do binder quản lý, để binder thực hiện lifecycle và không tự đóng client bên dưới binder.

RabbitMQ publisher confirms cho biết broker đã xác nhận publish theo cấu hình; Pulsar send future cho biết kết quả gửi theo client API; Kafka producer callback/future cho biết kết quả send. Chúng không tự chứng minh downstream business consumer đã hoàn tất.

Nếu input commit thành công nhưng output publish thất bại, có thể mất liên kết giữa hai bước nếu không có transaction phù hợp. Outbox pattern là lựa chọn phổ biến: ghi business change và outbox record trong cùng database transaction, sau đó relay publish outbox record với retry/idempotency. Điều này giúp phục hồi publish sau restart.

## 14. Idempotency để xử lý message được giao lại

Graceful shutdown không loại bỏ mọi duplicate. Ví dụ:

1. Consumer nhận event evt-123.
2. Database cập nhật đơn hàng thành công.
3. Process nhận SIGKILL trước khi ack/commit.
4. Broker giao lại evt-123 cho instance khác.

Nếu handler không idempotent, đơn hàng có thể bị trừ tiền hoặc phát hành thông báo hai lần.

Một cách phổ biến là lưu event ID đã xử lý trong cùng transaction với business update:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudo-code:

~~~java
@Transactional
public void processAndCommit(OrderAccepted event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderService.apply(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId(), Instant.now())
    );
}
~~~

Trong production, thao tác kiểm tra và insert cần được bảo vệ bởi unique constraint/transaction để xử lý hai consumer đồng thời. Chỉ gọi existsById rồi insert mà không có unique constraint có thể gặp race condition.

Nếu duplicate đến sau khi business update đã commit, handler trả về thành công mà không lặp side effect; binder có thể ack/commit record. Thời gian lưu idempotency key phải dài hơn khoảng retry/replay có thể xảy ra.

## 15. Transaction và outbox trong lúc dừng

Nếu handler thực hiện database transaction:

- Không ack trước khi transaction commit.
- Nếu transaction rollback, message phải còn khả năng retry.
- Nếu process chết trong transaction, database sẽ rollback khi connection bị đóng hoặc transaction timeout.
- Nếu database commit xong nhưng broker ack chưa xong, duplicate vẫn có thể xảy ra.

Nếu handler phát output:

- Gửi trực tiếp sau commit có khoảng hở giữa commit database và publish broker.
- Gửi output trước commit có thể phát event cho một thay đổi cuối cùng bị rollback.
- Dùng outbox để ghi event cần publish cùng transaction nghiệp vụ; relay publish sau đó.

Không gọi đây là distributed transaction nếu chỉ có database transaction và một broker publisher. Exactly-once giữa nhiều hệ thống cần cơ chế phối hợp cụ thể và thường có giới hạn.

## 16. Retry, DLQ và shutdown

Khi handler lỗi trong lúc shutdown:

- Lỗi tạm thời có thể được retry theo chính sách binder.
- Message chưa ack có thể được broker giao lại sau khi consumer đóng.
- Message độc hại hoặc không tương thích schema có thể đi vào DLQ theo error handler.
- Retry delay có thể kéo dài hơn thời gian shutdown.

Không chờ retry vô hạn trong shutdown. Dừng intake, kết thúc các handler đang chạy trong deadline và để broker/framework xử lý message chưa hoàn tất theo semantics đã cấu hình. DLQ nên dành cho message cần xử lý riêng, không phải nơi đẩy mọi message chỉ vì Pod đang dừng.

Với Kafka, offset commit và retry topic có thể khiến record được xử lý ở một luồng khác. Với RabbitMQ, requeue hoặc dead-letter routing phụ thuộc reject/nack và queue policy. Với Pulsar, negative acknowledgment, retry letter topic và dead letter policy có semantics riêng. Kiểm tra đúng binder.

## 17. Readiness và preStop trong Kubernetes

Một Pod xử lý message không nhận traffic qua Service vẫn có thể cần readiness cho rollout, nhưng readiness không trực tiếp điều khiển consumer group. Có thể xây dựng endpoint nội bộ để:

1. Đánh dấu instance REFUSING_TRAFFIC.
2. Yêu cầu binding pause/stop qua API được hỗ trợ.
3. Chờ in-flight counter bằng 0 hoặc tới deadline.
4. Trả kết quả cho hook.

Endpoint drain phải được bảo vệ, idempotent và có timeout. Nếu gọi nhiều lần, không khởi động nhiều quá trình chờ. Nếu hook timeout, SIGTERM vẫn cần kích hoạt shutdown path an toàn.

preStop không nên dùng một khoảng sleep tùy ý để giả định endpoint routing đã cập nhật. Hãy đo thời gian propagation và thiết kế hook theo tín hiệu thật của ứng dụng/nền tảng.

## 18. Shutdown khi rolling deployment và scale down

Trong rolling deployment, Pod cũ và mới có thể cùng tham gia consumer group trong một khoảng thời gian. Khi consumer cũ dừng, Kafka có thể rebalance partition; RabbitMQ có thể chuyển delivery chưa ack sang consumer khác; Pulsar có thể redeliver message chưa ack.

Để rollout an toàn:

- Triển khai consumer mới tương thích schema với message hiện có.
- Đảm bảo producer không phát schema/codec mà consumer cũ hoặc mới không hiểu trong giai đoạn chuyển tiếp.
- Chọn maxSurge/maxUnavailable và số replica theo năng lực broker.
- Đặt termination grace period đủ lớn so với thời gian drain p99.
- Theo dõi rebalance, queue unacked, Pulsar backlog và DLQ trong rollout.
- Giữ handler idempotent vì message có thể chuyển giữa instance.

PodDisruptionBudget giúp giới hạn số Pod bị voluntary disruption cùng lúc nhưng không bảo đảm handler hoàn tất hoặc message không bị duplicate.

## 19. Quan sát và cảnh báo quá trình shutdown

Ghi nhận ít nhất:

| Tín hiệu | Ý nghĩa |
|---|---|
| Shutdown started timestamp | Thời điểm nhận SIGTERM hoặc yêu cầu drain |
| Intake stopped timestamp | Thời điểm listener không nhận thêm công việc |
| In-flight count | Số handler còn đang chạy |
| Longest in-flight duration | Handler lâu nhất còn hoạt động |
| Drain duration | Tổng thời gian drain |
| Drain timeout count | Số lần hết deadline mà còn công việc |
| Ack/commit failures | Message đã xử lý nhưng xác nhận thất bại |
| Producer flush duration/errors | Output đang gửi có hoàn tất không |
| Redelivery/duplicate count | Tác động sau khi consumer dừng |

Log nên có application instance, binding name, consumer group/subscription, event ID (nếu an toàn), số in-flight và deadline còn lại. Không log payload nhạy cảm.

Một shutdown hoàn tất thành công không nhất thiết có in-flight count bằng 0 nếu deadline đã hết; trường hợp này phải được ghi nhận rõ và dự kiến broker sẽ giao lại các message chưa ack. Không ghi một log chung Shutdown complete mà bỏ qua số công việc chưa hoàn tất.

## 20. Kiểm thử graceful shutdown

Unit test cho tracker chỉ xác minh counter và timeout. Cần integration test với binder/broker thật hoặc container test để xác minh acknowledgment và redelivery.

### 20.1. Kịch bản kiểm thử

| Kịch bản | Cách tạo | Kết quả mong đợi |
|---|---|---|
| Dừng khi không có message | Gửi SIGTERM khi idle | Process thoát nhanh, connection đóng sạch |
| Dừng khi handler đang chạy | Handler chờ latch hoặc downstream giả lập chậm | Handler hoàn tất trước deadline, message được ack/commit |
| Dừng sau database commit trước ack | Chèn điểm dừng test sau commit | Message có thể được giao lại; idempotency ngăn side effect lặp |
| Handler vượt deadline | Giữ handler lâu hơn grace period | Process dừng theo deadline; message chưa ack được giao lại |
| Producer đang gửi output | Giữ send future chưa hoàn tất | Flush/chờ confirmation hoặc outbox phục hồi sau restart |
| Consumer dừng giữa batch | Gửi nhiều record rồi dừng | Chỉ phần đã xác nhận được commit; phần còn lại được giao lại |
| Nhiều Pod rolling | Scale hoặc deploy khi có tải | Không mất message; duplicate được xử lý an toàn |
| SIGKILL | Kill đột ngột | Không kỳ vọng graceful cleanup; broker redelivery và idempotency bảo vệ |

### 20.2. Kiểm tra Kafka

- Gửi record vào topic trong lúc handler đang chạy.
- Kích hoạt shutdown và quan sát consumer group.
- Xác minh offset đã commit và partition được assign lại.
- Dừng sau side effect nhưng trước commit để xác minh duplicate.
- Kiểm tra rebalance và max.poll.interval.ms khi handler chạy lâu.

### 20.3. Kiểm tra RabbitMQ

- Gửi message và giữ listener callback chưa trả về.
- Dừng application context.
- Quan sát consumer bị cancel và message unacked.
- Xác minh message chưa ack được requeue khi channel đóng.
- Xác minh message đã ack không bị giao lại.

### 20.4. Kiểm tra Pulsar

- Gửi message vào subscription durable.
- Dừng consumer khi handler đang chạy.
- Xác minh message đã ack không bị redeliver.
- Xác minh message chưa ack vẫn có thể được giao lại.
- Kiểm tra ack timeout, negative ack và batch acknowledgment theo subscription type.

## 21. Lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Pod bị SIGKILL khi còn handler | Grace period ngắn hơn thời gian xử lý | Đo p99, giới hạn dependency timeout và tăng grace period phù hợp |
| Readiness DOWN nhưng consumer vẫn nhận message | Readiness chỉ điều khiển traffic qua Service | Dừng binding/listener qua lifecycle |
| Message bị duplicate sau rollout | Side effect xong nhưng ack/commit chưa hoàn tất | Idempotency key và transaction boundary |
| Message mất sau restart | Ack/commit trước khi side effect hoàn tất | Chỉ ack sau ranh giới nghiệp vụ |
| Shutdown chờ vô hạn | Handler hoặc dependency không có timeout | Đặt deadline và timeout cho từng dependency |
| Producer output chưa gửi xong | Đóng producer quá sớm | Flush/chờ send hoặc dùng outbox; để binder quản lý producer của binder |
| Consumer group rebalance liên tục | Handler quá lâu hoặc shutdown/scale quá thường xuyên | Kiểm tra poll interval, processing time và rollout strategy |
| RabbitMQ có nhiều unacked khi Pod dừng | Prefetch lớn hoặc callback chậm | Điều chỉnh prefetch/concurrency và drain |
| Pulsar redelivery khi handler cũ còn chạy | Ack timeout ngắn hoặc consumer chưa ack | Điều chỉnh timeout theo xử lý và làm handler idempotent |
| Message đi vào DLQ khi Pod dừng | Exception shutdown bị phân loại như lỗi poison message | Tách shutdown exception khỏi business failure; cấu hình retry/requeue đúng |
| Task async mất sau khi handler trả về | Ack xảy ra trước khi future hoàn tất | Giữ acknowledgment boundary tới khi task hoàn tất |

## 22. Nguyên tắc thiết kế

1. Phân biệt readiness, web server graceful shutdown và binder/listener lifecycle.
2. Ngừng intake trước khi đóng dependency mà handler cần.
3. Đặt timeout hữu hạn cho handler và mọi lời gọi downstream.
4. Theo dõi in-flight work và chờ trong một deadline có giới hạn.
5. Chỉ acknowledge/commit sau khi side effect đạt ranh giới hoàn tất.
6. Không ack trong finally hoặc trả về thành công khi task async còn chạy.
7. Chờ output publish theo semantics thực tế; dùng outbox khi cần phục hồi publish.
8. Làm handler idempotent vì duplicate vẫn có thể xảy ra.
9. Đặt Kubernetes grace period lớn hơn tổng thời gian drain và cleanup.
10. Kiểm thử từng binder vì Kafka, RabbitMQ và Pulsar có semantics khác nhau.
11. Để binder quản lý tài nguyên binder sở hữu; không đóng client bên dưới binder tùy tiện.
12. Quan sát drain timeout, in-flight count, commit/ack failure và redelivery sau rollout.

## Tài liệu tham khảo chính thức

- [Spring Boot - Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): graceful shutdown của embedded web server.
- [Spring Framework - Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle callback và SmartLifecycle.
- [Spring Cloud Stream - Binding Lifecycle](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): quan sát và điều khiển binding theo API hỗ trợ.
- [Apache Kafka Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs): max.poll.interval.ms, max.poll.records và commit behavior.
- [Spring for Apache Kafka - Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): listener container lifecycle và acknowledgment.
- [RabbitMQ Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ack, nack, unacked delivery và publisher confirmation.
- [Spring AMQP - Listener Container](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): listener container, concurrency và lifecycle.
- [Apache Pulsar - Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): subscription, acknowledgment và redelivery.
- [Kubernetes - Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination grace period, preStop và SIGTERM.
