# Graceful rolling deployment trong Spring Kafka

## 1. Tại sao triển khai lần lượt vẫn có thể làm consumer xử lý sai?

Một hệ thống dùng Spring Kafka có ba replica `orders-consumer`, cùng tham gia consumer group `orders-workers`. Mỗi replica nhận các partitions từ topic `orders.events`, cập nhật database và xác nhận offset sau khi xử lý. Đội vận hành muốn nâng phiên bản ứng dụng mà không dừng luồng xử lý trên toàn hệ thống.

Kubernetes `Deployment` với chiến lược `RollingUpdate` có thể thay Pod cũ bằng Pod mới từng đợt. Tuy nhiên, **rolling update của Kubernetes không tự bảo đảm Kafka consumer hoàn tất record đang xử lý hoặc commit offset an toàn**. Khi Pod cũ nhận tín hiệu kết thúc, có thể vẫn còn record trong lần `poll()` gần nhất, một transaction đang mở, thao tác HTTP chưa có phản hồi, hoặc một `CompletableFuture` đang chạy ở thread pool khác.

Một triển khai lỗi có thể tạo chuỗi sự kiện:

```text
Consumer A (v1)                        Consumer B (v2)
-------------------------------        ----------------------------
poll offset 104                         Pod mới khởi động
ghi DB cho offset 104                   tham gia cùng consumer group
Pod A nhận SIGTERM                      rebalance bắt đầu
JVM bị SIGKILL trước khi commit 105     nhận partition từ A
                                       đọc lại offset 104
                                       ghi DB lần thứ hai
```

Đây là hành vi **at-least-once có khả năng redelivery**, không nhất thiết là lỗi Kafka. Nếu nghiệp vụ không idempotent, cùng record có thể làm tăng số dư, gửi thông báo hoặc tạo giao dịch trùng. Ngược lại, nếu ứng dụng **commit offset trước khi side effect thực sự bền vững**, crash có thể làm mất công việc chưa hoàn thành về mặt nghiệp vụ.

Mục tiêu của *graceful rolling deployment* là:

1. Cho Pod/consumer cũ dừng **nhận thêm work** theo đường lifecycle được hỗ trợ.
2. Cho work đang được xử lý kết thúc hoặc được bàn giao theo cơ chế retry có kiểm soát.
3. Commit những offset **thật sự an toàn** theo ack mode và transaction semantics.
4. Để consumer group chuyển quyền sở hữu partitions sang members còn sống hoặc mới được tạo.
5. Bảo đảm các lần redelivery có thể chạy lại an toàn nhờ idempotency.
6. Duy trì khả năng phục vụ chung, theo dõi consumer lag và có phương án rollback phiên bản.

**Graceful không có nghĩa chính xác một lần xử lý tuyệt đối, không có rebalance và không có độ trễ.** Nó là một quy trình giảm rủi ro, giảm thời gian gián đoạn và quản lý các cửa sổ lỗi còn lại.

## 2. Những lớp lifecycle tham gia rollout

```text
Kubernetes Deployment
   | RollingUpdate: tạo Pod mới, chọn Pod cũ để terminate
   v
Kubernetes Pod / container runtime
   | readiness, preStop (nếu có), SIGTERM, grace deadline
   v
Java process / Spring ApplicationContext
   | đóng context, dừng SmartLifecycle beans
   v
Spring Kafka listener container
   | hoàn tất callback theo stop policy, xử lý ack/commit,
   | đóng KafkaConsumer, rời group
   v
Kafka consumer group
   | rebalance / giao lại partitions
   v
Pod mới tiêu thụ từ committed offsets
   | idempotency bảo vệ trường hợp redelivery
   v
Business DB / external services
```

Mỗi lớp có cơ chế timeout riêng. Ví dụ Kubernetes có 90 giây grace period nhưng Spring Kafka container chỉ được chờ tối đa 10 giây ở cấu hình riêng; hoặc Spring Boot chờ shutdown phase 30 giây trong khi callback đang gọi một API timeout 120 giây. Vì vậy cần thiết kế **ngân sách shutdown tổng thể**, không chỉ đặt một `terminationGracePeriodSeconds` thật lớn.

### 2.1. Khác biệt giữa availability và correctness

| Khía cạnh | Câu hỏi | Ví dụ điều kiện đạt |
|---|---|---|
| Pod availability | Có đủ replica sẵn sàng theo Kubernetes không? | `maxUnavailable` và readiness đáp ứng chiến lược rollout. |
| Consumer availability | Consumer group còn thành viên nhận partitions không? | Members hoạt động, assignment được tạo lại. |
| Processing correctness | Record đã hoàn thành trước khi offset được xác nhận chưa? | Side effect bền vững trước khi ack/commit; retry an toàn. |
| Business correctness | Record được xử lý lại có gây kết quả trùng không? | Unique key, idempotency key hoặc reconciliation. |
| Recovery | Khi Pod bị kill cưỡng bức, hệ thống tự tiến lên được không? | Broker giữ record, group reassign, handler có retry/DLT thích hợp. |

Kubernetes readiness probe thường kiểm soát **định tuyến traffic qua Service**, không kiểm soát trực tiếp việc Kafka broker gán partitions. Một consumer có thể tiếp tục `poll()` dù Pod bị đánh dấu `NotReady`. Tương tự, một Pod `Ready` không chứng minh nó đã được gán partition hoặc đã bắt kịp toàn bộ consumer lag.

## 3. Một rolling deployment bình thường diễn ra như thế nào?

Giả sử Deployment có ba Pod v1, topic sáu partitions và mỗi Pod chạy `concurrency=2`. Trước rollout có tối đa sáu consumer instances thuộc cùng group; các partitions được phân phối theo cơ chế group assignment.

```text
Trước rollout:
  v1-Pod-A  -> 2 consumer threads
  v1-Pod-B  -> 2 consumer threads
  v1-Pod-C  -> 2 consumer threads

Rollout với maxSurge=1, maxUnavailable=0:
  1. Tạo v2-Pod-D, chờ Pod đủ điều kiện Ready.
  2. D có thể tham gia consumer group -> rebalance.
  3. Chọn một Pod v1 để chấm dứt.
  4. Pod cũ nhận SIGTERM -> Spring đóng listener container.
  5. Group điều chỉnh assignment, thành viên còn sống tiêu thụ tiếp.
  6. Lặp lại với các Pod v1 còn lại.

Kết quả kỳ vọng:
  v2-Pod-D/E/F chạy; Pod A/B/C đã rời group.
```

Với `maxSurge=1`, số consumer tạm thời có thể **lớn hơn số Kafka partitions**; một số consumer không có assignment là bình thường. Do đó, **đừng đặt readiness bắt buộc mọi consumer phải có partition**, vì Pod surge có thể không đạt Ready và rollout bị kẹt. Mặt khác, readiness của HTTP server không nên được xem là bảo đảm Kafka producer/consumer đã khỏe nếu nghiệp vụ cần tín hiệu chuyên biệt.

`maxUnavailable=0` đảm bảo số Pod sẵn sàng theo **định nghĩa Kubernetes**, không đảm bảo thông lượng Kafka luôn bằng 100% hay không có pause do rebalance. Một đợt rolling update thay đổi group membership là tình huống bình thường có thể gây dao động lag trong chốc lát.

## 4. Spring Kafka đóng listener container như thế nào?

Các listener được tạo từ `@KafkaListener` thường được quản lý bởi `KafkaListenerEndpointRegistry`. Listener containers thực thi `SmartLifecycle`, được khởi động/dừng như một phần vòng đời `ApplicationContext`.

Khi Spring Boot shutdown bình thường, framework dừng các `SmartLifecycle` beans theo phase. Spring Kafka container có cơ chế dừng tiêu thụ, giải phóng Kafka consumer và xử lý commit theo cấu hình tương ứng. Tuy vậy, kết quả cuối phụ thuộc **ack mode**, handler error, thời gian callback và việc có bất kỳ async work nào nằm ngoài container hay không.

### 4.1. `stopImmediate` và các record từ lần poll trước

Spring Kafka `ContainerProperties` có property `stopImmediate`:

| Giá trị | Hành vi của record listener khi yêu cầu stop | Đánh đổi |
|---|---|---|
| `false` (mặc định trong dòng Spring Kafka 3.x) | Thường hoàn tất việc xử lý các records lấy từ lần `poll()` trước rồi mới dừng. | Dễ drain poll batch; thời gian shutdown có thể dài khi `max.poll.records` lớn hoặc mỗi record chậm. |
| `true` | Dừng sau record hiện tại thay vì xử lý hết các records của poll trước. | Dừng nhanh hơn; các records chưa xử lý cần được nhận lại khi group tiếp tục, tùy ack/offset semantics. |

Ví dụ một lần `poll()` trả 100 records, mỗi record xử lý 200 ms. Nếu container được yêu cầu stop ngay sau record đầu, với `stopImmediate=false` có thể cần xử lý phần còn lại trong khoảng 20 giây (ước lượng) mới hoàn tất; với `true`, container có thể dừng sớm hơn nhưng còn work chưa xử lý.

**Giá trị `false` không phải bảo đảm shutdown sẽ chờ vô hạn.** Nếu process bị `SIGKILL`, ứng dụng treo trong callback hoặc hết timeout, container vẫn không có cơ hội hoàn tất đúng đường lifecycle. Với batch listener, một lời gọi nhận nhiều records cần được thiết kế như một đơn vị xử lý riêng; `stopImmediate=true` không thể ngắt giữa chừng callback đang chạy.

### 4.2. `shutdownTimeout`

`ContainerProperties.setShutdownTimeout(long)` quy định thời gian tối đa (millisecond) để chờ việc dừng container. Trong Spring Kafka 3.3, giá trị mặc định thường là **10.000 ms**. Một callback mất 25 giây có thể cần cấu hình timeout lớn hơn nếu muốn cho phép hoàn tất theo đường shutdown.

Điều cần phân biệt: timeout dừng container, timeout của Spring lifecycle phase và deadline SIGKILL của Kubernetes là **ba giới hạn khác nhau**. `shutdownTimeout` không làm một HTTP request đang treo tự kết thúc; các thư viện HTTP/JDBC bên trong listener cần timeout và cancellation phù hợp.

### 4.3. `pause()` không phải `stop()`

`MessageListenerContainer.pause()` yêu cầu ngừng lấy records để phát cho listener sau thời điểm pause có hiệu lực. Khi đã pause, container vẫn tiếp tục `poll()` ở mức KafkaConsumer để duy trì thành viên của group; vì thế **pause không tự giải phóng assignment** cho Pod mới.

| API | Ứng dụng | Có rời consumer group? |
|---|---|---|
| `pause()` | Tạm ngừng phân phối records, ví dụ backpressure hoặc giai đoạn drain có điều phối. | Không, container vẫn poll để giữ group khi đang pause. |
| `resume()` | Tiếp tục nhận records sau pause. | Không, tiếp tục nhóm hiện tại. |
| `stop()` | Ngừng container theo lifecycle, đóng consumer, trao cơ hội reassign partitions. | Thông thường có, khi consumer đóng/rời group hoặc session hết hạn. |
| Shutdown ApplicationContext | Dừng lifecycle của các containers rồi đóng các tài nguyên khác theo phase. | Thường dẫn đến rời group theo đường graceful. |

`pauseImmediate` lại là property khác: khi pause, nó quyết định dừng phân phối sau record hiện tại hay sau toàn bộ kết quả poll. Nó **không đồng nghĩa** `stopImmediate` và không tự quản lý shutdown của ứng dụng.

Nếu cần triển khai protocol **drain trước khi stop**, một tầng điều phối có thể yêu cầu pause, chờ trạng thái `isConsumerPaused()` hoặc `ConsumerPausedEvent` và in-flight work về mức an toàn, rồi stop container trên **thread điều phối**. Đừng gọi API điều khiển consumer trực tiếp từ Kafka listener callback rồi block chờ chính callback đó hoàn tất: có thể tự gây deadlock hoặc trì hoãn poll.

## 5. Offset commit và ack mode quyết định phạm vi replay

Trong consumer có `enable.auto.commit=false`, Spring Kafka container hỗ trợ các `AckMode` khác nhau. Phải hiểu cách offset được commit trước khi tin rằng stop là “không mất record”.

| Ack mode | Điểm xác nhận điển hình | Lưu ý khi rolling update |
|---|---|---|
| `RECORD` | Commit offset sau khi listener xử lý xong từng record (với record listener). | Dễ diễn giải phạm vi xử lý đã hoàn tất, nhưng tăng overhead commit. |
| `BATCH` (mặc định phổ biến với record listener) | Commit khi xử lý hết records của một lần poll. | Ít commit hơn; crash giữa batch có thể khiến records đã xử lý nhưng chưa commit được nhận lại. |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`, container áp dụng quy tắc commit tương ứng. | Chỉ ack sau khi business work hoàn tất; tránh quên ack hoặc ack sớm. |
| `MANUAL_IMMEDIATE` | Ack được commit sớm khi gọi đúng từ consumer thread, theo cấu hình. | Phải hiểu thread gọi ack, sync/async commit và thời điểm side effect. |

`enable.auto.commit=true` làm Kafka client commit offsets định kỳ theo timer riêng, có thể tạo hành vi khác với sự hoàn tất xử lý nghiệp vụ. Với một pipeline cần quản lý rõ ràng at-least-once, thường đặt `enable.auto.commit=false` và chọn ack mode phù hợp.

### 5.1. At-least-once và cửa sổ duplicate

```text
1. Consumer nhận record offset 200.
2. Business DB transaction commit thành công.
3. JVM bị kill TRƯỚC khi Kafka offset 201 commit thành công.
4. Consumer thay thế nhận offset 200 lần nữa.

=> Không mất record, nhưng có thể bị xử lý lặp.
```

Giải pháp thường là **idempotent business processing**, không phải cố ép Kafka commit sớm. Commit offset trước khi xử lý bền vững có thể dẫn đến mất work nếu process chết sau commit offset nhưng trước business transaction.

### 5.2. Commit cuối cùng không được bảo đảm khi shutdown timeout

Khi container được yêu cầu dừng, nó cố xử lý/commit theo ack mode và các callback; nhưng nếu transaction DB bị block, consumer mất quyền sở hữu partition, xảy ra rebalance giữa chừng hoặc mất kết nối broker, commit có thể thất bại. Vì vậy phải quan sát lỗi commit/rebalance và thiết kế replay an toàn.

`CommitFailedException`, `RebalanceInProgressException`, transaction fencing và callback bị ngắt là các sự kiện cần chẩn đoán theo phiên bản client/handler. Một số trường hợp retry commit có thể được cấu hình, nhưng không thể lấy retry vô hạn làm giải pháp nếu consumer đã mất quyền sở hữu partitions.

### 5.3. Kafka transactions và exactly-once

Nếu pipeline **consume Kafka → produce Kafka** dùng Kafka transactions và offset trong transaction đúng cách, Spring Kafka/Kafka hỗ trợ exactly-once semantics theo phạm vi Kafka transaction. Điều này **không tự mở rộng** thành một atomic transaction giữa Kafka offsets và mọi thay đổi ở database/HTTP/third-party APIs.

Khi dùng transactional producers trong rolling update, cần quản lý `transactional.id`/`transaction-id-prefix` để tránh **producer fencing không mong muốn** giữa hai Pod đang cùng sống trong thời gian surge. Không dùng cùng transactional ID cố định cho hai process có thể chạy đồng thời; cấu hình transaction identity phải phù hợp replica và concurrency.

## 6. Ví dụ Spring Boot 3.x / Spring Kafka 3.x: consumer đồng bộ

Ví dụ sau dùng Java 17+, Spring Boot 3.x và Spring Kafka 3.x. Đây là kiến trúc **record listener đồng bộ**, dễ dùng làm đường chuẩn trước khi thêm worker threads bất đồng bộ. Các property được minh họa; cần điều chỉnh theo SLA và dependency thực tế.

### 6.1. `application.yml`

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 60s

  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-workers
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
    listener:
      ack-mode: record

server:
  shutdown: graceful

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

**Giải thích:**

- `timeout-per-shutdown-phase` giới hạn thời gian Spring chờ mỗi phase dừng `SmartLifecycle`; không phải tổng tuyệt đối của toàn shutdown.
- `server.shutdown=graceful` liên quan chủ yếu tới embedded web server; Kafka listener container có lifecycle/timeout riêng.
- `max.poll.records=100` giúp giới hạn số records một lần poll trả về ở mức client; không tự biến mỗi record thành một transaction.
- `max.poll.interval.ms` phải đủ cho thời gian xử lý giữa các lần poll, bao gồm tình huống xử lý hết batch và backoff; nếu không, consumer có thể bị coi là không hoạt động và rebalance.
- `session.timeout.ms` phụ thuộc giới hạn của broker/group protocol và không phải một giá trị tối ưu chung. Tăng nó không làm callback nhanh hơn và có thể trì hoãn phát hiện consumer chết đột ngột.
- `auto-offset-reset=earliest` **chỉ áp dụng khi group không có committed offset hợp lệ**; rollout bình thường tiếp tục từ committed offset, không vì property này mà đọc lại từ đầu.
- Actuator readiness endpoint phải tồn tại thực tế nếu có dependency và cấu hình tương ứng; nó phản ánh health model được định nghĩa, không tự chứng minh Kafka partition assignment.

### 6.2. Container factory với shutdown policy

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
class OrdersKafkaContainerConfig {

    @Bean("ordersKafkaListenerFactory")
    ConcurrentKafkaListenerContainerFactory<String, String> ordersKafkaListenerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        configurer.configure(factory, consumerFactory);

        factory.setConcurrency(2);
        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD);
        factory.getContainerProperties().setStopImmediate(false);
        factory.getContainerProperties().setShutdownTimeout(45_000L);

        return factory;
    }
}
```

Ở đây `shutdownTimeout=45s`, Spring lifecycle phase `60s`, và ví dụ Kubernetes ở mục sau dùng grace period `90s`. Đây là **ngân sách minh họa có khoảng dự phòng**, không phải công thức tự đảm bảo shutdown êm. Với callback 2 phút hoặc network call không có timeout, Pod vẫn có thể bị kill khi hết deadline.

`setConcurrency(2)` tạo tối đa hai consumer instances cho container; tổng members của group còn phụ thuộc số Pods, các listener khác và partition count. Khi concurrency lớn hơn số assigned partitions, một số consumer threads sẽ không có partition. Không bắt readiness của mọi child consumer phải có assignment.

### 6.3. Listener chỉ trả về sau khi nghiệp vụ hoàn tất

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrdersEventConsumer {

    private final OrderProcessingService orderProcessingService;

    OrdersEventConsumer(OrderProcessingService orderProcessingService) {
        this.orderProcessingService = orderProcessingService;
    }

    @KafkaListener(
            id = "ordersConsumer",
            topics = "orders.events",
            groupId = "orders-workers",
            containerFactory = "ordersKafkaListenerFactory")
    public void onRecord(ConsumerRecord<String, String> record) {
        orderProcessingService.applyIdempotently(
                record.key(), record.value());
        // RECORD ack mode: container có thể commit sau khi method trả về.
    }
}
```

`OrderProcessingService.applyIdempotently(...)` là logic **ứng dụng tự cài đặt**, không phải API Spring Kafka. Nó cần hoàn tất transaction nghiệp vụ và kiểm soát duplicate **trước khi** trả về. Khi gặp lỗi chưa được recover hợp lệ, hãy để exception tới error handler đã cấu hình thay vì catch rồi nuốt để listener trả thành công.

Ví dụ cơ chế idempotency PostgreSQL đơn giản:

```sql
CREATE TABLE processed_order_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Trong CÙNG business transaction với thay đổi nghiệp vụ:
INSERT INTO processed_order_event (event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;
```

Phần service thực tế phải kiểm tra **row insert thành công hay đã tồn tại** để biết có nên thực hiện thay đổi nghiệp vụ. Chỉ insert marker rồi luôn xử lý lại vẫn tạo duplicate. `event_id` cần ổn định giữa các lần retry/redelivery và được quy định bởi hợp đồng dữ liệu; không nên dùng random UUID tạo mới mỗi khi consume.

Nếu marker và business update nằm ở **hai database/transaction khác nhau**, lời hứa idempotency cũng cần được đánh giá lại. Marker phải đi cùng transaction có ranh giới nhất quán với side effect mà nó bảo vệ.

## 7. Ví dụ Kubernetes Deployment dùng rolling update

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-consumer
spec:
  replicas: 3
  revisionHistoryLimit: 5
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-consumer
  template:
    metadata:
      labels:
        app: orders-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: orders-consumer
          image: example/orders-consumer:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          env:
            - name: KAFKA_BOOTSTRAP_SERVERS
              valueFrom:
                configMapKeyRef:
                  name: kafka-connectivity
                  key: bootstrap-servers
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              memory: 1Gi
```

YAML trên là **mẫu triển khai cần có** ConfigMap `kafka-connectivity`, ứng dụng có web/Actuator ở port 8080, Kafka brokers và bảo mật kết nối tương ứng. Image `example/...` là placeholder; không dùng trực tiếp. Các số timeout, CPU/RAM và replica chỉ để trình bày cách phối hợp, phải đo theo thời gian xử lý record thực tế.

### 7.1. `maxSurge` và `maxUnavailable`

- `maxSurge: 1`: cho phép một Pod mới vượt quá số replica mong muốn trong lúc rollout, giúp có năng lực khởi động phiên bản mới trước khi giảm số Pod cũ.
- `maxUnavailable: 0`: Kubernetes cố giữ số Pods **Ready** ít nhất bằng số replica mong muốn trong rollout. Nó không bảo đảm consumer lag không tăng hay Kafka group không rebalance.
- Khi topic có ít partitions hơn tổng consumers tạm thời, Pod mới vẫn có thể Ready dù không sở hữu partition; đây là tình huống có thể chấp nhận được.
- `progressDeadlineSeconds` hỗ trợ đánh dấu rollout không tiến triển, không thay thế giám sát consumer lag hoặc lỗi xử lý.

### 7.2. Readiness, liveness và startup probes

| Probe | Nên trả lời | Không nên suy diễn |
|---|---|---|
| Startup | Ứng dụng đã khởi động đủ để bắt đầu kiểm tra liveness/readiness chưa? | Chưa chắc đã xử lý hết backlog. |
| Liveness | Process có cần được restart vì tình trạng không thể phục hồi không? | Kafka broker tạm thời lỗi không nhất thiết là lý do kill Pod ngay. |
| Readiness | Pod có đủ điều kiện phục vụ traffic/nhận vai trò theo health policy không? | Pod Ready không đồng nghĩa đã có partition assignment. |

Nếu liveness probe phụ thuộc quá chặt vào Kafka broker health, một outage ngắn có thể làm **mọi Pod bị restart hàng loạt**, gây thêm rebalances. Health policy nên phân biệt kết nối tạm thời lỗi, consumer được pause chủ động, và process thật sự kẹt không thể hồi phục.

Trong mô hình consumer-only không nhận HTTP traffic, readiness có thể được dùng cho chính sách rollout/observability, nhưng đừng nghĩ readiness `false` tự ngắt Kafka `poll()`. Nếu cần drain Kafka cụ thể, dùng API listener container hoặc shutdown lifecycle.

### 7.3. Vì sao không cần `preStop` trong mọi ứng dụng?

Kubernetes thực thi hook `preStop` (nếu có) **trước khi** gửi stop signal, và thời gian chạy `preStop` được tính trong `terminationGracePeriodSeconds`. Một hook chỉ làm `sleep 30` không khiến Kafka consumer tự stop; nó có thể vẫn nhận thêm records trong lúc sleep rồi còn ít thời gian cho Spring shutdown thực sự.

Chỉ bổ sung `preStop` khi có **một protocol drain cụ thể đã được triển khai, kiểm thử và có timeout**. Ví dụ hook gọi endpoint nội bộ đặt application vào trạng thái draining, dừng listener containers và trả kết quả sau khi work đã hoàn tất; khi đó phải phối hợp với SIGTERM tiếp theo và budget chung. Không gọi endpoint không tồn tại hoặc đóng consumer từ thread xử lý record rồi tự block chờ deadlock.

### 7.4. Java cần nhận được tín hiệu dừng

Docker image nên chạy Java trực tiếp hoặc shell wrapper phải dùng `exec` để chuyển PID 1 và signals đúng:

```dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Nếu entrypoint là shell script không `exec`, hãy kiểm tra SIGTERM có tới JVM và Spring context có thực sự đóng hay không. Một process có thể chạy bình thường nhưng không graceful shutdown nếu signal bị wrapper nuốt.

## 8. Thiết kế ngân sách thời gian shutdown

Một cấu hình graceful chỉ đáng tin nếu mọi giới hạn thời gian được đặt từ **số đo thực tế**. Gọi:

- `T_preStop`: thời gian hook trước khi hệ điều hành gửi signal (nếu dùng).
- `T_listener`: thời gian tối đa để listener hoàn tất work đang xử lý sau yêu cầu dừng.
- `T_commit`: thời gian flush/ack/commit và giải phóng Kafka consumer, database connections.
- `T_other`: shutdown của HTTP server, executors, publisher, cache, telemetry và các resources khác.
- `T_margin`: dự phòng cho scheduling, GC, network và chậm bất thường.

Một quy tắc ước lượng để bắt đầu thiết kế là:

\[
T_{KubernetesGrace} > T_{preStop} + T_{listener} + T_{commit}
   + T_{other} + T_{margin}
\]

Đây là **budget bảo thủ**, không phải công thức Spring hay Kubernetes tự tính. Một số shutdown phases có thể diễn ra chồng lấp, còn một số được chạy tuần tự; phải quan sát lifecycle thực tế để tránh cộng/trừ sai. Ngoài ra, `spring.lifecycle.timeout-per-shutdown-phase` được áp dụng **theo từng phase**, nên không nhất thiết là toàn bộ thời gian Spring shutdown.

### 8.1. Ước lượng drain từ `max.poll.records`

Với record listener tuần tự, một ngưỡng trên gần đúng của thời gian xử lý kết quả một lần poll là:

\[
T_{pollBatch} \approx N_{polled} \times T_{record,pessimistic}
\]

Ví dụ `max.poll.records=100`, p99 latency xử lý mỗi record là 300 ms; trong trường hợp xấu nếu cả 100 records đều mất khoảng này, drain có thể tới 30 giây **chưa tính** commit/flush. Nếu mỗi record có thể timeout 3 giây, cùng poll batch có thể mất đến nhiều phút và khó gói trong grace 90 giây.

| Phương án | Tác động throughput | Ảnh hưởng shutdown |
|---|---|---|
| Giảm `max.poll.records` | Có thể tăng số lần poll/overhead hoặc giảm batch processing throughput. | Giảm work tối đa đã nhận trong một poll. |
| `stopImmediate=true` | Thường không ảnh hưởng steady state nhưng thay đổi hành vi dừng. | Có thể dừng sau record hiện tại; cần chấp nhận replay phần chưa xử lý. |
| Timeout ở HTTP/DB per item | Tránh callback treo vô hạn. | Giới hạn thời gian xử lý/rollback trong nhiều lỗi. |
| Idempotent writer | Có thể thêm overhead DB/unique constraints. | Cho phép redelivery an toàn, giảm áp lực phải drain tuyệt đối. |
| Grace period lớn hơn | Không tăng throughput. | Cho thêm thời gian, nhưng kéo dài rollout và giữ tài nguyên. |
| Async pipeline có drain protocol | Tăng concurrency nhưng phức tạp. | Cần theo dõi in-flight futures và hoàn tất/rollback rõ ràng. |

**Đừng tăng `max.poll.interval.ms` chỉ để che việc dừng quá lâu.** Nó điều khiển thời gian tối đa giữa các lần poll trong consumer group, không phải deadline của Kubernetes; một listener xử lý blocking quá lâu vẫn có thể bị kill bởi Pod grace period.

### 8.2. Ví dụ budget có khoảng dự phòng

Giả sử kết quả benchmark cho thấy poll batch lớn nhất trong đường chạy thường mất 25 giây, flush/commit tối đa 5 giây, đóng các resources khác 10 giây. Có thể dự kiến:

```text
Kubernetes terminationGracePeriodSeconds  = 90 s
Spring lifecycle timeout per phase        = 60 s
Kafka listener container shutdownTimeout  = 45 s
Normal poll batch drain                   = 25 s
Commit + cleanup                           = 5–10 s
Margin                                      = còn lại
```

Nếu callback có trường hợp 120 giây, cấu hình này không đủ. Có thể sửa logic để request có timeout, giảm poll batch, điều chỉnh stop policy hoặc thiết kế replay an toàn. Không coi giá trị 90 giây ở YAML là “đã giải quyết graceful” mà chưa có test khi ứng dụng đang bận.

## 9. Consumer group rebalance khi thay Pods

Kafka phân công partitions cho các thành viên consumer group. Khi Pod mới tham gia hoặc Pod cũ rời group, Kafka có thể cần **rebalance** để phân phối lại partitions. Đây là một phần bình thường của rolling update, không phải lỗi cần retry bằng cách restart tất cả Pods.

### 9.1. Eager và cooperative rebalancing

| Kiểu assignment | Đặc điểm khái quát | Hệ quả khi rollout |
|---|---|---|
| Eager rebalance | Các members có thể phải revoke nhiều partitions để group tái phân công. | Có thể tạm ngừng xử lý rộng hơn trong lúc membership thay đổi. |
| Cooperative / incremental rebalance | Cố gắng chỉ revoke những partitions cần chuyển theo assignor hỗ trợ. | Có thể giảm phạm vi gián đoạn, nhưng không loại bỏ mọi pause/rebalance. |

Kafka client có assignor như `CooperativeStickyAssignor`; muốn sử dụng phải bảo đảm **toàn consumer group hỗ trợ chiến lược tương thích** và tuân thủ quy trình migration được tài liệu Kafka nêu. Không thay `partition.assignment.strategy` ngẫu nhiên khi đang rollout hai phiên bản vì members cũ/mới có thể chưa thống nhất protocol.

Ví dụ một property khi đã thiết kế group phù hợp:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Đây là **lựa chọn có điều kiện**, không phải cấu hình bắt buộc cho mọi ứng dụng. Trong các phiên bản Kafka client mới, consumer group protocol/assignor được quản lý khác nhau, nên cần dựa trên broker/client versions đang dùng. Với hệ thống nhiều consumer types trong một group, thống nhất compatibility trước rollout.

### 9.2. Rebalance listener không phải nơi làm việc nặng

Spring Kafka hỗ trợ các callback rebalance như `ConsumerAwareRebalanceListener`, cho phép quan sát partition assignment/revocation và thực hiện thao tác cần thiết trước/ sau commit theo hợp đồng. Handler này nằm trong lifecycle consumer; không đặt các HTTP call chờ vô hạn hoặc tác vụ đối soát hàng triệu bản ghi ở đây.

Một số việc phù hợp:

- Ghi metric số partitions được giao/revoke, thời gian rebalance và consumer group member ID đã được phép log.
- Flush state cục bộ **khi thật sự cần và hỗ trợ được**, trong timeout có giới hạn.
- Xác minh các record đã hoàn tất/ack theo ack mode, không commit offset cho work còn đang chạy ở thread khác.

Việc Kafka revoke partition không khiến database transaction bên ngoài tự rollback. Nếu phần xử lý bất đồng bộ vẫn đang chạy sau revoke, cần một quy tắc ownership/idempotency rõ ràng; không gọi `Consumer.commitSync(...)` tùy tiện từ callback ở thread khác.

### 9.3. Static membership (`group.instance.id`)

Static membership có thể giúp giảm một số rebalances khi một consumer khởi động lại nhanh và giữ cùng identity. Với Spring Kafka `ConcurrentMessageListenerContainer`, khi cấu hình `group.instance.id` và concurrency lớn hơn một, framework có thể bổ sung hậu tố `-n` cho từng child consumer.

**Cảnh báo về Kubernetes Deployment:** Pod names thường thay đổi khi rollout; nếu mọi replica được cấu hình một `group.instance.id` cố định giống nhau, Kafka có thể **fence members** do identity trùng. Tương tự, dùng Pod ordinal/identity không ổn định trong Deployment mà hy vọng identity giữ nguyên là sai giả định. Static membership nên được thiết kế với danh tính **duy nhất cho mỗi consumer có thể cùng hoạt động, đủ ổn định qua restart**, thường dễ tổ chức hơn trong StatefulSet hoặc môi trường có identity bền.

Tăng `session.timeout.ms` có thể giảm một số rebalance ngắn hạn nhưng làm failover sau crash lâu hơn; phải cân bằng availability với thời gian phát hiện thành viên mất kết nối. Không dùng static membership như biện pháp thay thế shutdown đúng và idempotent output.

## 10. Trường hợp listener chạy lâu, batch listener và offset ordering

### 10.1. Callback xử lý lâu

Ví dụ listener gọi service ngoài mất 40 giây mỗi record. Nếu Kafka poll trả 100 records, `stopImmediate=false` có thể mất quá thời gian termination. Thay vì chỉ tăng thời gian chờ vô hạn, cân nhắc:

1. Đặt connection/read/overall timeout cho HTTP/gRPC/DB calls.
2. Giảm số records một lần poll nếu throughput chịu được.
3. Tách xử lý chậm qua hệ thống có work ownership/ack semantics riêng.
4. Dùng `stopImmediate=true` với idempotent processing để chấp nhận replay.
5. Đo p95/p99 processing latency và kiểm thử SIGTERM khi backlog lớn.

`max.poll.interval.ms` phải đủ cho thời gian thực giữa các lần poll. Nếu callback liên tục xử lý quá lâu và consumer mất membership, commit về sau có thể thất bại mặc dù logic nghiệp vụ chạy xong.

### 10.2. Batch listener nhận một danh sách records

Với `@KafkaListener` sử dụng batch mode, một callback có thể xử lý cả danh sách. Container không thể ngắt Java method giữa chừng chỉ bằng `stopImmediate=true`. Nếu business batch cần 3 phút, phải lựa chọn: cho phép thời gian phù hợp hoặc thiết kế batch nội bộ có checkpoints/idempotency, timeout/cancellation.

Khi ack mode `BATCH`, nên hiểu kết quả được commit sau khi poll batch đã được xử lý theo quy tắc. Nếu listener tự xử lý một nửa rồi trả thành công, framework **có thể coi batch đã hoàn thành**; đừng trả thành công khi còn records chưa được xử lý an toàn.

### 10.3. Manual ack và async acks

Nếu listener gọi `Acknowledgment.acknowledge()` trước khi transaction DB commit, có nguy cơ offset tiến trước business result. Nếu listener dispatch việc vào thread pool rồi trả về, **return của method không chứng minh work đã xong**. Một số chế độ ack bất đồng bộ hỗ trợ out-of-order completion nhưng cần đặc biệt kiểm soát shutdown và rebalance.

```text
Consumer thread                Worker thread
  receive offset 50              process offset 50...
  submit task -------->          gọi API/DB
  returns immediately             chưa hoàn tất
  container stop
  worker result đến sau stop -> ack có thể không còn hợp lệ
```

Với Spring Kafka 3.2+, listener có thể trả `CompletableFuture` hoặc reactive type; framework có handling dành riêng cho async completion. Tuy nhiên **không được mặc nhiên coi việc stop consumer container là đã chờ mọi async work của ứng dụng hoàn tất**, đặc biệt khi nhiệm vụ được dispatch sang executor riêng. Kiểm tra tài liệu đúng phiên bản về stop/drain và cài thêm logic đợi in-flight tasks khi cần.

Một protocol async drain có thể gồm: đặt trạng thái `DRAINING`, ngừng tiếp nhận work mới, chờ số `inFlight` về 0 trong timeout, flush/ack những kết quả an toàn, stop container và đóng executor sau đó. Cần làm rõ cách quản lý pending futures khi timeout, không báo “đã drain” khi chỉ có consumer thread dừng.

## 11. Retry, DLT và công việc còn dở khi Pod thay phiên bản

Spring Kafka thường có `DefaultErrorHandler`, retry/backoff và dead-letter publishing để xử lý lỗi. Trong rolling update, một record lỗi đang chờ retry có thể gặp shutdown/rebalance. Phải hiểu policy lỗi trước khi quyết định ack hay stop.

| Tình huống | Hệ quả có thể xảy ra | Thiết kế cần có |
|---|---|---|
| Error handler retry cùng record | Shutdown giữa retry, record có thể xuất hiện lại trên member mới. | Retry side effects idempotent, backoff hợp lý. |
| Retry được chuyển sang retry topic | Work có thể chờ ở topic khác qua nhiều phiên bản triển khai. | Schema/handler của cả v1 và v2 phải tương thích với retry payload. |
| Publish tới DLT thành công | Record được lưu cho điều tra/reprocess theo cấu hình. | DLT retention, alert, correlation và xử lý re-drive có kiểm soát. |
| Producer gửi DLT thành công nhưng offset source chưa commit | Khi restart record có thể được gửi DLT lần nữa. | DLT consumer/producer idempotency, delivery semantics rõ. |
| Shutdown trong long backoff | Có thể kéo dài stop hoặc cần ngắt/replay. | Dùng error handler/backoff phù hợp lifecycle và deadline. |

**Không tự động nuốt exception để rollout nhanh hơn.** Nếu business record chưa được xử lý thành công hoặc chưa được recover theo một policy được chấp nhận, không nên trả thành công rồi commit offset. Ngược lại, nếu đã được gửi DLT an toàn và policy coi đó là recovery, phải có bằng chứng và khả năng re-drive.

### 11.1. Compatibility giữa hai phiên bản ứng dụng

Trong rolling update, v1 và v2 chạy **đồng thời** trên cùng topic/group trong một khoảng thời gian. Nếu v2 thay schema message, deserializer hoặc database schema không tương thích với v1, record có thể được giao cho v1 giữa rollout và gây lỗi.

Chiến lược nâng cấp an toàn thường là **expand → migrate → contract**:

1. Cho consumer v1 hiểu dữ liệu v2 hoặc giữ producer ở schema tương thích.
2. Triển khai database migration dạng mở rộng tương thích cả hai version.
3. Rolling deploy consumer v2 và quan sát group/retry/DLT.
4. Chỉ khi v1 rời toàn bộ hệ thống và rollback path đã được xem xét mới loại bỏ field/bảng cũ hoặc phát định dạng breaking change.

Một Kafka record **không mang thông tin “chỉ được v2 consume”** nếu hai versions dùng cùng group. Đừng trông cậy vào thứ tự triển khai Pod để đảm bảo record phù hợp luôn đến đúng code.

## 12. Observability trong lúc rolling deployment

Một rollout không nên chỉ dựa vào `kubectl rollout status` để kết luận chất lượng xử lý Kafka. Theo dõi những tín hiệu sau theo khoảng **trước, trong và sau** rollout:

| Tín hiệu | Điều kiểm tra |
|---|---|
| Số Pods `Ready`/`Terminating` | Kubernetes có duy trì khả năng sẵn sàng theo chiến lược không? |
| Consumer group members và assigned partitions | Group có members/assignment hoạt động, số consumers không vượt kỳ vọng bất thường? |
| Consumer lag và lag growth rate | Backlog có tăng trong rebalance hoặc tiến tới ngưỡng SLA không? |
| Records consumed/s và processing latency p95/p99 | Throughput có giảm bất thường sau v2? |
| Offset commit latency/failures | Có commit lỗi hoặc tăng đáng kể do shutdown/rebalance không? |
| Rebalance count/duration | Rollout có gây rebalance quá nhiều hoặc kéo dài? |
| Kafka producer errors/transaction fencing | Nếu app phát records/transactions, có lỗi identity hoặc transactional ID không? |
| Retries, DLT, deserialization errors | v2 có tạo lỗi schema/handler mới không? |
| Duplicate suppression/idempotency conflict rate | Redelivery có được kiểm soát không, duplicate có tăng sau rollout? |
| Shutdown duration và forced kills | Pod có bị SIGKILL do hết grace period không? |
| DB pool/locks/HTTP timeouts | Side effects có hoàn tất đúng trước khi listener return không? |

Một bộ log sự kiện kỹ thuật nên có những trường ổn định:

```text
deployment.shutdown.requested pod=orders-consumer-abc version=v1
kafka.listener.stop.requested listenerId=ordersConsumer
kafka.listener.stopped listenerId=ordersConsumer elapsedMs=18800
deployment.shutdown.completed pod=orders-consumer-abc elapsedMs=21400

kafka.partition.assigned group=orders-workers topic=orders.events partition=3
kafka.partition.revoked group=orders-workers topic=orders.events partition=3
```

Các dòng trên là **format gợi ý**, không phải events được Spring tự ghi đúng y hệt. Tránh log nguyên payload hoặc access credentials chỉ để điều tra deployment. Nếu không có event `shutdown.completed` vì process crash, cần dựa thêm vào Kubernetes termination reason/exit code và Kafka group metrics.

**Giữ metric cardinality hợp lý:** dùng `application`, `version`, `listenerId`, `topic` ở tập hữu hạn. Không tạo label riêng cho từng message key/payload hoặc random request ID. Pod ID có thể hữu ích trong log và một số metrics có vòng đời ngắn, nhưng cần kiểm soát retention/tập giá trị của monitoring backend.

### 12.1. Xác định rollout thành công

Một định nghĩa có thể kiểm thử gồm:

- Toàn bộ Pods mục tiêu ở phiên bản v2 và Ready theo chính sách.
- Không còn members v1 trong consumer group khi rollout hoàn tất.
- Lag quay về baseline hoặc dưới ngưỡng SLO trong một khoảng chờ đã thống nhất.
- Error/timeout/DLT rate không tăng bất thường so với trước triển khai.
- Không có bằng chứng mất kết quả nghiệp vụ; duplicate nếu có được idempotency xử lý đúng.
- Thời gian shutdown Pods cũ nằm trong grace period; không có SIGKILL bất thường.

Khi không đủ điều kiện, chọn rollback hoặc dừng rollout theo runbook. **`kubectl rollout undo` không xóa được side effects dữ liệu đã tạo bởi v2**; cần thiết kế rollback dữ liệu, schema và message compatibility riêng.

## 13. Integration test Spring Kafka cho đường dừng bình thường

Unit test cho handler không chứng minh container sẽ chờ callback hoặc commit offset khi shutdown. Ít nhất một integration test phải thực sự chạy listener container với broker test, yêu cầu stop lúc listener đang xử lý rồi kiểm tra kết quả.

### 13.1. Dependencies và môi trường

Ví dụ Gradle Groovy với Spring Boot quản lý dependency versions:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`@EmbeddedKafka` dùng broker thử nghiệm trong integration tests; Testcontainers Kafka cũng là lựa chọn tốt nếu cần kiểm tra broker/container gần thực tế. Sử dụng **topic và group ID riêng cho từng test suite**, tránh test trước để lại offsets làm kết quả test sau sai.

### 13.2. Test listener đang xử lý rồi yêu cầu stop

Ta có thể tạo một test listener với `CountDownLatch` để xác định chính xác callback đang chạy, sau đó yêu cầu stop container và chỉ cho callback hoàn tất sau khi stop đã được gửi. Đây là cách kiểm thử **deterministic hơn `Thread.sleep(3000)`**.

```java
// Trong test configuration của một @SpringBootTest + @EmbeddedKafka.
@Component
class ControlledOrderListener {

    final CountDownLatch entered = new CountDownLatch(1);
    final CountDownLatch mayFinish = new CountDownLatch(1);
    final AtomicInteger completed = new AtomicInteger();

    @KafkaListener(
            id = "controlledOrders",
            topics = "orders-rolling-it",
            groupId = "orders-rolling-it-group")
    public void onMessage(String value) throws InterruptedException {
        entered.countDown();

        if (!mayFinish.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test release timeout");
        }

        completed.incrementAndGet();
        // Trong hệ thống thực, thay bằng transaction nghiệp vụ bền vững.
    }
}
```

Phần logic test:

```java
@Autowired KafkaTemplate<String, String> kafkaTemplate;
@Autowired KafkaListenerEndpointRegistry registry;
@Autowired ControlledOrderListener listener;

@Test
void gracefulStopAllowsCurrentCallbackToFinish() throws Exception {
    kafkaTemplate.send("orders-rolling-it", "order-1")
            .get(10, TimeUnit.SECONDS);

    assertTrue(listener.entered.await(15, TimeUnit.SECONDS));

    MessageListenerContainer container =
            registry.getListenerContainer("controlledOrders");
    assertNotNull(container);

    CompletableFuture<Void> stopped = new CompletableFuture<>();
    container.stop(() -> stopped.complete(null));

    assertFalse(stopped.isDone(),
            "Container should still be stopping while callback is blocked");

    listener.mayFinish.countDown();
    stopped.get(20, TimeUnit.SECONDS);

    assertEquals(1, listener.completed.get());
}
```

Các imports cần thiết gồm `CountDownLatch`, `AtomicInteger`, `TimeUnit`, `CompletableFuture`, `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, Spring Kafka `@KafkaListener`, `@Component` và các assertion JUnit. Đây là **các phần trích tích hợp vào một test class**, giả định đã có test `ApplicationContext` chứa `ControlledOrderListener`, Kafka serializers/deserializers String, `KafkaTemplate` và broker/bean wiring tương ứng.

Điểm cần giữ:

1. Dùng `entered` để chứng minh callback bắt đầu trước khi yêu cầu stop.
2. Gọi `stop(Runnable callback)` và chờ callback hoàn tất; không block consumer thread bằng thao tác control.
3. Dùng `mayFinish` để test có thể giải phóng callback, tránh chờ vô hạn.
4. Dùng timeout hữu hạn cho broker ACK, listener startup và container stop.
5. **Không gọi stop callback rồi kết luận offset đã được commit và không có duplicate** chỉ từ `completed=1`. Test phải xác nhận riêng offset/state.

`assertFalse(stopped.isDone())` trong đoạn này là assertion trong cửa sổ callback còn bị giữ bởi latch; vẫn phải dựa vào container stop contract và runner scheduling. Trong test thực tế, dùng cơ chế probe riêng nếu cần kiểm tra mọi ordering guarantee; bảo đảm `mayFinish.countDown()` được gọi trong `finally` để không làm rò thread khi assertion thất bại.

### 13.3. Kiểm tra offset và redelivery sau stop/restart

Để thực sự chứng minh at-least-once và không mất work, test nên mở thêm một consumer với **cùng `group.id`** sau khi container cũ đã stop, rồi kiểm tra vị trí committed offset hoặc record được giao lại theo scenario:

| Scenario | Kỳ vọng |
|---|---|
| Callback hoàn tất, ack/commit thành công, sau đó stop | Consumer mới thường bắt đầu sau offset đã commit, không xử lý lại record đó. |
| Callback bị chấm dứt trước khi business work hoàn tất và chưa ack | Record có thể được consumer mới đọc lại. |
| Business DB đã commit, Kafka offset chưa commit | Record có thể redeliver; idempotency ngăn tác dụng phụ trùng. |
| Listener catch exception rồi trả thành công sai | Offset có thể tiến, mất work nghiệp vụ. Đây là bug cần test phát hiện. |

Việc kiểm tra committed offsets nên dùng Kafka `AdminClient` hoặc consumer riêng sau khi group ổn định, với các APIs phù hợp client version. Đừng dựa vào `auto.offset.reset=earliest` để suy ra offset đã commit; setting đó chỉ được áp dụng nếu không có committed offset hợp lệ.

### 13.4. Test `stopImmediate=true`

Với `max.poll.records` đủ lớn, gửi nhiều records và yêu cầu stop khi callback đầu đang chạy. Khi đặt `stopImmediate=true`, test cần xác minh:

- Callback hiện tại có cơ hội hoàn tất theo timeout.
- Những records chưa xử lý trong poll được **xử lý lại** sau restart theo ack/offset policy, không bị bỏ mất.
- Số business rows cuối cùng đúng, không duplicate; kiểm tra bằng unique business key hoặc data assertions.
- Lúc callback có lỗi, error handler vẫn điều khiển retry/DLT đúng; không tự commit tất cả offsets.

Không viết assertion rằng listener sẽ xử lý **đúng một record** sau stop trong mọi scheduling race: stop request có thể đến khi container vừa chuyển sang record tiếp theo. Test phải đồng bộ bằng latch/record identifier và dùng hành vi cuối cùng ở Kafka/DB để kết luận.

## 14. Test triển khai trên Kubernetes / process thật

`@EmbeddedKafka` không mô phỏng đầy đủ SIGTERM, SIGKILL, Pod lifecycle, network partitions hay group rebalance trên nhiều process. Một vòng kiểm thử staging nên dùng **Kafka broker test bền qua nhiều Pod** và dữ liệu nghiệp vụ cô lập.

### 14.1. Kịch bản rolling update thực tế

```text
Chuẩn bị:
  - Topic test có 6 partitions.
  - 3 Pods consumer v1, concurrency 2.
  - Producer phát bản ghi với eventId ổn định.
  - Business DB có unique eventId để đối soát.

Thử nghiệm:
  1. Chạy workload đều và ghi baseline throughput/lag.
  2. Bắt đầu rolling update v1 -> v2, maxSurge=1/maxUnavailable=0.
  3. Theo dõi partition revoke/assign, consumer lag, commits,
     shutdown duration và Pod termination reasons.
  4. Chờ toàn bộ Pods v2 Ready, old Pods chấm dứt.
  5. Chờ lag trở lại baseline, đối soát event IDs/DB output.

Đạt:
  - Không mất business events;
  - Duplicate nếu xảy ra được idempotency xử lý;
  - Không có Pod buộc SIGKILL do shutdown timeout;
  - Throughput và error rate đáp ứng SLO.
```

Một số lệnh quan sát trong môi trường Kubernetes **test/staging đã được phép truy cập**:

```bash
kubectl rollout status deployment/orders-consumer -n batch-staging
kubectl get pods -n batch-staging -l app=orders-consumer -o wide
kubectl describe deployment orders-consumer -n batch-staging
kubectl logs -n batch-staging deployment/orders-consumer --tail=200
```

Chỉ quan sát rollout không chứng minh correctness; cần so khớp tập business event IDs đã publish với tập kết quả đã commit. Những lệnh `kubectl rollout restart` hoặc `kubectl rollout undo` là **thao tác có tác động** và chỉ nên thực thi theo quy trình triển khai/staging tương ứng.

### 14.2. Kịch bản mất grace: buộc kill process thử nghiệm

Kiểm thử trường hợp xấu:

1. Đưa listener vào trạng thái đang xử lý một record có side effect DB được kiểm soát.
2. Trên process/Pod **thử nghiệm riêng**, giả lập không còn cơ hội cleanup (ví dụ kill container theo quy trình chaos test).
3. Quan sát Kafka group session/rebalance, record redelivery và DB state.
4. Xác minh kết quả cuối **không mất, không nhân đôi ngoài ý định**, nhờ idempotency.
5. Ghi lại thời gian phát hiện failure và phục hồi lag.

Không kill Pod production hoặc JVM chứa toàn bộ JUnit suite để thực hiện bài test này. Kết quả kỳ vọng phải có retry/redelivery, không yêu cầu record luôn đi qua graceful path sau kill cưỡng bức.

### 14.3. Test phối hợp với database migration và schema change

Cho v1 và v2 chạy cùng lúc trong một group trong khi producer vẫn phát dữ liệu theo schema đã công bố. Kiểm tra cả hai versions đều deserialize và xử lý đúng. Với database, chạy migration kiểu expand trước rolling update; chỉ contract schema khi không còn v1 và đã có đường rollback hợp lý.

Đây là kiểm thử quan trọng vì **rolling update mang tính cố ý chạy hai phiên bản song song**. Một deploy hạ tầng graceful nhưng message/DB schema breaking change vẫn có thể làm consumer group thất bại hàng loạt.

## 15. Runbook triển khai và rollback

### Trước rollout

1. Xác minh phiên bản mới tương thích event schema, retry topics, DLT và database với v1.
2. Xem số partitions, replicas, concurrency và năng lực DB; kiểm tra `maxSurge` không làm vượt budget tài nguyên.
3. Kiểm tra listener callbacks có timeout, ack mode rõ và writer idempotent.
4. Xác định `max.poll.records`, latency p99 và budget `shutdownTimeout`/Spring lifecycle/Kubernetes grace.
5. Đọc baseline lag, records/s, retry/DLT, consumer members, commit failures.
6. Kiểm tra log shutdown ở staging đã từng cho thấy container hoàn tất trước SIGKILL.
7. Chuẩn bị lệnh rollback và tiêu chí dừng rollout nếu lag/error vượt SLO.

### Trong rollout

1. Tạo Pod v2 và quan sát startup, readiness, lỗi deserialization/auth/transaction fencing.
2. Khi Pod v1 được chọn để terminate, theo dõi SIGTERM → listener stop → consumer rời group.
3. Theo dõi rebalance count/duration, assignment, lag tăng/giảm và các offsets sau takeover.
4. Nếu v2 gây lỗi dữ liệu hoặc DLT tăng, **pause/rollback rollout theo quy trình**, không tự restart hàng loạt bằng liveness probe.
5. Không force delete Pods cũ chỉ vì chúng còn xử lý một poll batch bình thường; điều tra vì sao shutdown quá budget nếu bị kẹt.

### Sau rollout

1. Xác minh các Pods v1 đã được thay; số group members và assignment ở trạng thái ổn định.
2. Chờ consumer lag/latency trở về ngưỡng mục tiêu trong thời gian đã định.
3. Đối soát business event IDs/DB output, kiểm tra duplicates đã được xử lý an toàn.
4. Kiểm tra các retry/DLT events có thể đã được tạo bởi v1 và còn chờ v2 xử lý.
5. Lưu thông số/metrics của rollout để điều chỉnh timeout, concurrency hoặc `max.poll.records` cho lần sau.

### Khi cần rollback

Rollback image version không tự rollback database migrations hoặc các side effects đã ghi. Phải xác minh old code vẫn xử lý được dữ liệu do v2 tạo ra. Nếu schema đã chuyển sang dạng breaking, cần **roll-forward fix**, compatibility adapter hoặc quy trình khôi phục dữ liệu có kiểm soát, không chỉ `kubectl rollout undo`.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Pod bị SIGKILL dù đã dùng `RollingUpdate` | Grace 30s không đủ hoặc Spring/container shutdown timeout quá ngắn. | Đo drain time, tăng budget phù hợp, giảm poll batch/timeout external call. |
| Pod `Ready` nhưng chưa nhận message | Không có assignment, dư consumers so với partitions hoặc rebalance chưa xong. | Đối chiếu group members/partitions, không coi readiness HTTP là Kafka assignment. |
| Rollout kẹt khi surge Pod mới không Ready | Readiness bắt buộc phải có assigned partitions trong group đã kín. | Sửa health contract, tránh đòi mọi Pod phải có partition. |
| Tăng consumer lag trong rollout | Rebalance/pause tạm thời, throughput v2 thấp, backlog producer tăng. | Đo rebalance duration, process rate, DB waits và error handler. |
| Record bị xử lý hai lần sau Pod thay | DB commit xong trước Kafka offset commit, consumer redelivery. | Idempotency/unique business key và test commit crash window. |
| Record nghiệp vụ bị mất dù Kafka còn offset tiến | Ack/commit trước side effect hoặc nuốt exception. | Chỉ ack sau xử lý bền vững, kiểm tra error handling. |
| `pause()` rồi Pod mới không nhận partition | Pause vẫn poll để giữ group. | Dùng `stop()`/shutdown lifecycle để rời group, không dùng pause thay stop. |
| Stop mất lâu dù `stopImmediate=false` | Listener cần xử lý hết records của poll và/hoặc callback block. | Đo `max.poll.records` × processing latency, đặt timeout, chọn policy. |
| Stop nhanh nhưng records được replay | `stopImmediate=true`, ack/commit chưa bao gồm records chưa xử lý. | Đây có thể là hành vi đúng; kiểm tra idempotency và committed offsets. |
| Consumer liên tục rebalance | Replica/concurrency vượt thiết kế, poll quá lâu, liveness restart storm. | Đo membership churn, `max.poll.interval`, health probes và assignment strategy. |
| Static membership bị fenced | `group.instance.id` trùng giữa các Pods cùng sống. | Định danh ổn định và duy nhất, xem xét StatefulSet/rollout overlap. |
| Transactional producer fenced lúc v1/v2 cùng chạy | Cùng transactional ID trên hai instances. | Prefix/transaction ID unique per active instance, phù hợp concurrency. |
| Async callback còn chạy sau khi container dừng | `stop()` không chờ executor/in-flight futures của ứng dụng. | Thiết kế drain protocol theo version, chờ completion hoặc replay/idempotency. |
| DLT tăng mạnh sau rollout | Schema/handler hoặc retry-topic compatibility không đúng. | Test v1/v2 mixed-mode, monitoring và rollback có điều kiện. |
| `preStop` sleep làm hết grace period | Hook chiếm thời gian trước SIGTERM mà consumer vẫn poll. | Bỏ sleep vô nghĩa hoặc cài drain endpoint thật với budget rõ. |
| Rollback v1 không consume được event mới | v2/producer đưa breaking schema vào Kafka. | Expand-contract, dual compatibility, tránh phát breaking data trước thời điểm cho phép. |
| `maxUnavailable=0` nhưng message vẫn bị gián đoạn ngắn | Kubernetes đảm bảo Ready Pods, Kafka group vẫn rebalance. | Thiết kế SLO/lag budget, cooperative assignment khi tương thích. |

## 17. Khung lựa chọn giữa drain, fast stop và replay

Một hệ thống đáng tin cậy cần chọn được shutdown policy theo loại work:

| Loại consumer | Chính sách thường hợp lý | Điều kiện bắt buộc |
|---|---|---|
| Record ngắn, ghi DB transactional | `stopImmediate=false`, `AckMode.RECORD` hoặc mode được benchmark. | Idempotency, DB commit hoàn tất trước ack. |
| Record rất dài, deadline Pod ngắn | `stopImmediate=true` hoặc giảm poll size và làm xử lý có timeout. | Có thể replay record chưa commit, side effects idempotent. |
| Batch listener dùng bulk writes | Drain hết callback nếu có thể, timeout rõ. | Atomicity theo transaction thực tế, test batch failure. |
| Async worker/CompletableFuture | Custom in-flight drain protocol, kiểm tra version-specific semantics. | Không ack sớm; executor không bị đóng trước work đang chạy. |
| Kafka-to-Kafka transactional pipeline | Dùng Kafka transaction/EOS theo cấu hình đúng. | Transaction identity unique, broker/client compatible. |
| Consumer gọi payment/email/external API | Bảo vệ idempotency trước, stop policy sau. | Idempotency key được bên nhận xác nhận và reconciliation. |

Quyết định nào cũng cần cân bằng **thời gian drain tối đa**, tỷ lệ redelivery, độ trễ rollout, mức tăng consumer lag và chi phí xử lý duplicate. Grace period dài không thay thế correctness; replay an toàn thường thực tế hơn việc cố loại bỏ hoàn toàn khả năng duplicate.

## 18. Bài tập thực hành

### Bài 1 — Đo một rolling deployment có graceful shutdown

Tạo topic thử nghiệm sáu partitions, ba Pods `orders-consumer` với concurrency bằng hai và một producer phát message đều. Triển khai `RollingUpdate` với `maxSurge=1`, `maxUnavailable=0`, grace period 90 giây. Đo rebalance time, consumer lag và thời gian dừng từng Pod. Giải thích vì sao Kubernetes hoàn tất rollout vẫn cần kiểm tra business output.

### Bài 2 — So sánh `stopImmediate` hai giá trị

Viết listener dùng latch để giữ một record đang xử lý. Gửi 20 records, thử `stopImmediate=false` và `true` trong hai bộ test riêng. Đo thời gian stop, records xử lý trước shutdown và records được nhận lại sau restart cùng group. Không suy ra kết quả chỉ từ listener invocation count; đối chiếu committed offsets và business rows.

### Bài 3 — Crash giữa DB commit và Kafka offset commit

Tạo `OrderProcessingService` lưu business result và marker idempotency trong cùng transaction. Mô phỏng crash ở process test riêng sau khi DB commit nhưng trước offset commit; khởi động consumer thay thế. Chứng minh record có thể được redeliver nhưng database chỉ ghi một business result.

### Bài 4 — Tính ngân sách termination

Giả sử `max.poll.records=200`, mỗi record có thể mất 300 ms, commit+cleanup 8 giây, preStop 5 giây, framework shutdown khác 12 giây. Ước lượng budget tối thiểu với margin hợp lý. Phân tích điều gì xảy ra nếu một HTTP call có timeout 120 giây, và nên thay đổi poll size/stop policy/timeouts như thế nào.

### Bài 5 — Rebalance và readiness

Tạo group có sáu partitions, sáu consumer instances và thêm một surge Pod có hai consumers. Quan sát assignment khi tổng consumers lớn hơn partitions. Thử một readiness rule yêu cầu Pod phải được assign partition và giải thích nguy cơ rollout bị kẹt. Thiết kế readiness phù hợp hơn với mục tiêu của workload.

### Bài 6 — Rollback breaking schema

Thiết kế hai phiên bản consumer: v1 đọc event `v1`, v2 đọc được `v1` và `v2`. Lập kế hoạch nâng producer và database theo expand-contract để v1/v2 có thể cùng chạy lúc rollout. Mô phỏng v2 gặp lỗi rồi rollback; xác định lúc nào rollback về v1 còn an toàn và khi nào cần roll-forward.

## 19. Nguyên tắc ghi nhớ

1. **Kubernetes RollingUpdate không tự bảo đảm Kafka record-level correctness.** Nó điều khiển việc thay Pods, không kiểm soát business transaction và offset commit.
2. **SIGTERM phải tới JVM và Spring context phải được đóng.** `SIGKILL` không chạy shutdown hooks; luôn có phương án replay an toàn.
3. **Spring Kafka listener container dùng `SmartLifecycle`**, cần ngân sách shutdown phù hợp với thời gian xử lý poll batch.
4. **`stopImmediate=false` mặc định thường drain kết quả poll trước khi dừng; `true` ưu tiên dừng sau record hiện tại.** Hai chế độ cần kiểm thử với ack mode thực tế.
5. **`pause()` không giải phóng partitions.** Container vẫn poll để giữ group; `stop()` mới là đường dừng để group có thể phân phối lại.
6. **Business work phải bền vững trước khi ack/commit offset** nếu muốn tránh mất work; redelivery là điều phải dự kiến trong at-least-once.
7. **Idempotency quan trọng hơn cố loại bỏ hoàn toàn duplicate**, nhất là với database và APIs bên ngoài Kafka transactions.
8. **Readiness khác consumer assignment.** Surge Pod có thể Ready khi chưa được gán partitions; không thiết kế health gate khiến rollout tự kẹt.
9. **Grace period bao gồm `preStop` và nhiều shutdown phases.** Đo thời gian thật, có margin, đặt timeout cho các I/O calls.
10. **Cần kiểm thử active work, stop, rebalance, redelivery và rollback.** Không coi `kubectl rollout status` là phép kiểm chứng dữ liệu đã được xử lý đúng.

## 20. Tài liệu tham khảo chính thức

- [Spring Kafka Reference — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/3.3/kafka/container-props.html): `stopImmediate`, `shutdownTimeout`, `pauseImmediate`, `pollTimeout`, ack-related settings.
- [Spring Kafka Reference — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): `SmartLifecycle`, offset commits, `AckMode`, concurrency và static membership.
- [Spring Kafka Reference — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html): `pause()`, `resume()` và `isConsumerPaused()`.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retry, stopping error handler và recovery.
- [Spring Kafka Reference — Asynchronous Listener Return Types](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/async-returns.html): async completion/ack và giới hạn drain khi dừng container.
- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi Kafka transactions/EOS.
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): `spring.lifecycle.timeout-per-shutdown-phase` và web server shutdown.
- [Kubernetes Documentation — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling update, `maxSurge`, `maxUnavailable`, rollout availability.
- [Kubernetes Documentation — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): `preStop`, grace period, SIGTERM/SIGKILL, endpoint behavior.
- [Spring Kafka Reference — Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html): `@EmbeddedKafka` và integration testing.
- [Apache Kafka Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.records`, `max.poll.interval.ms`, `group.instance.id`, assignment strategy và commit behavior.


