# Thông điệp nằm ở ready vì listener chưa chạy hoặc bị hủy

Một triệu chứng rất thường gặp khi vận hành **Spring AMQP** là publisher đã gửi thành công, RabbitMQ Management hiện queue có **`messages_ready` tăng liên tục**, nhưng nghiệp vụ phía consumer không xử lý sự kiện nào. Đội phát triển dễ kết luận “RabbitMQ bị nghẽn” hoặc “message không route được”, trong khi nguyên nhân có thể đơn giản là **`@RabbitListener` chưa được khởi động**, đã bị dừng bởi ứng dụng, hoặc **consumer bị broker hủy** (*consumer cancellation*) sau khi queue bị xóa hay channel bị đóng.

Bài thuộc chương **Chẩn đoán sự cố** của module **SPRING_AMQP**. Ta sẽ kết hợp kiến thức `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, ACK/NACK, retry, dead-letter và quan sát hệ thống để phân biệt chính xác:

- Message đã nằm trong queue và đang **ready**.
- Message đã được giao cho consumer nhưng còn **unacknowledged**.
- Listener/container của Spring **đang chạy hay đã dừng**.
- Broker có consumer đăng ký trên **đúng queue và virtual host** hay không.
- Broker **hủy consumer**, đóng channel, mất connection hoặc queue mất khả dụng.
- Khi listener được khởi động lại, backlog được tiêu thụ ra sao và khi nào có thể phát sinh duplicate.

**Đích cần đạt:** Có một quy trình đọc metrics → kiểm tra topology/connection → xem lifecycle listener → xác định root cause → phục hồi có kiểm soát → xác minh backlog giảm; không dùng thao tác xóa/purge queue để che đi sự cố.

> Ví dụ hướng tới Java 17+, Spring Boot 3.x, Spring AMQP 3.x và RabbitMQ AMQP 0-9-1. Tên metric, log, một số thuộc tính container và hành vi phục hồi phụ thuộc phiên bản RabbitMQ/Spring AMQP; hãy đối chiếu phiên bản chạy thực tế khi vận hành.

## 1. Hiểu đúng ready, unacked và consumer count

### 1.1. Một message di chuyển qua những trạng thái nào?

```text
RabbitTemplate / publisher
          |
          v
     exchange + binding
          |
          v
     RabbitMQ queue
   +-------------------+
   | messages_ready    |  <-- message chưa được giao
   +-------------------+
          |
          | consumer đủ điều kiện nhận và có credit/prefetch
          v
   +-------------------+
   | unacknowledged    |  <-- đã delivery, broker còn chờ ACK
   +-------------------+
          |
          +--- ACK -------------> hoàn tất delivery
          |
          +--- NACK/requeue ----> có thể quay về ready
          |
          +--- reject/no requeue -> DLX hoặc drop theo cấu hình
          |
          +--- channel mất ------> có thể redeliver sau phục hồi
```

Các đại lượng RabbitMQ Management/CLI thường hiển thị:

| Chỉ số | Diễn giải | Không được suy diễn |
|---|---|---|
| `messages_ready` | Số message đang nằm trong queue, **sẵn sàng để broker giao** theo điều kiện queue/consumer | Không phải số message đã xử lý và không đo chính xác số giây chờ |
| `messages_unacknowledged` (unacked) | Delivery đã giao nhưng chưa có ACK | Không có nghĩa tất cả đang chạy trong method Java; một phần có thể ở buffer do prefetch |
| `messages` | Tổng `ready + unacked` | Không phân biệt backlog ở broker với in-flight ở consumer |
| `consumers` | Số consumer hiện được broker đăng ký trên **queue này** | Không bảo đảm mỗi consumer đều đang xử lý nhanh hoặc là Spring app mà bạn kỳ vọng |
| Publish rate | Tốc độ message vào exchange/queue | Không phải tốc độ business commit ở consumer |
| Deliver/get rate | Tốc độ broker giao message tới consumers | Không phải số nghiệp vụ xử lý thành công |
| Ack rate | Tốc độ consumer xác nhận delivery | Không chứng minh nội dung nghiệp vụ đúng nếu listener nuốt exception |

**Bằng chứng ban đầu mạnh nhất cho chủ đề bài này:** Trên **đúng queue/vhost**, `messages_ready > 0`, `consumers = 0` và publish rate vẫn tăng. Khi đó chưa có consumer đăng ký đang kéo message từ queue. Lúc này hãy kiểm tra listener không khởi tạo, dừng hoặc bị hủy, thay vì tăng `prefetch` hoặc tối ưu SQL ngay lập tức.

**Nhưng:** Nếu `consumers > 0` và `ready > 0`, không kết luận ngay rằng listener “bị hủy”. Có thể consumer đang bận, đã đạt giới hạn prefetch, bị block do DB hoặc có **Single Active Consumer** mà chỉ một consumer thực sự nhận delivery.

### 1.2. Ví dụ dữ liệu và diễn giải

| Ready | Unacked | Consumers | Nhận định ưu tiên |
|---:|---:|---:|---|
| 8.000 | 0 | 0 | Không có consumer đăng ký; kiểm tra lifecycle, queue/vhost, lỗi đăng ký |
| 8.000 | 10 | 1 | Consumer tồn tại nhưng capacity/ACK chậm hoặc prefetch đã đầy |
| 0 | 100 | 4 | Message đã được giao, đang chờ ACK; điều tra handler/DB/prefetch |
| 0 | 0 | 2 | Không có backlog quan sát được; nếu nghiệp vụ thiếu, điều tra publisher/routing/outbox |
| 3.000 | 0 | 2 | Có consumer nhưng delivery không tiến triển; kiểm tra consumer active, queue availability, channel flow |
| 200 | 0 | 0 | Có thể là DLQ/quarantine cố ý không có consumer, không nhất thiết là lỗi production |

Con số chỉ là minh họa. Đối chiếu **trend trong vài phút**, không chỉ một snapshot. Với queue đang có retry/requeue, ready có thể tăng giảm rất nhanh mà nghiệp vụ vẫn thất bại.

## 2. Sơ đồ chẩn đoán nhanh từ RabbitMQ

Khi thấy backlog tăng:

```text
RabbitMQ: messages_ready tăng?
         |
         v
Đúng vhost + đúng queue + queue còn tồn tại?
         |
       NO --> Sai cấu hình endpoint, tên queue,
         |    topology, quyền hoặc bạn đang xem nhầm queue
         |
        YES
         |
         v
Broker thấy consumers > 0?
         |
      +--+--------------------------+
      |                             |
     NO                            YES
      |                             |
      v                             v
Spring registry có listener?   unacked có cao không?
container isRunning()?              |
      |                         +---+---+
      v                         |       |
autoStartup, @EnableRabbit,     YES     NO
component scan, stop(),         |       |
broker basic.cancel             v       v
connection/vhost,               Handler/DB/  Kiểm tra active
permission, queue missing       prefetch/ACK  consumer, SAC,
      |                         recovery     network/queue
      v                             |
Khôi phục registration              v
      |                        Sức tiêu thụ thực
      v
RabbitMQ consumers > 0?
      |
      v
Deliver/ACK rate > 0 và ready giảm?
      |
      v
Xác minh DB/business effect + duplicate/DLQ
```

**Lưu ý:** `consumers=0` là **quan sát từ broker**. `container.isRunning()=true` là **trạng thái local của Spring**. Hai điều này có thể tạm thời khác nhau: container đang cố reconnect, queue không tồn tại, consumer bị cancel hoặc việc đăng ký chưa hoàn thành. Cần kết hợp cả hai phía mới kết luận.

## 3. Bước 1: xác nhận đúng queue và virtual host

Một lỗi hay bị bỏ qua là publisher gửi tới broker/vhost A, còn listener kết nối broker/vhost B, trong khi queue **cùng tên** đều tồn tại ở hai nơi.

### 3.1. Xem RabbitMQ Management

Trên trang queue cụ thể, ghi lại:

- Vhost và tên queue chính xác.
- Queue type (classic/quorum/stream), trạng thái và node/leader nếu có.
- `Ready`, `Unacked`, `Total`, consumer count.
- Publish, deliver/get, ack rates.
- Danh sách consumers, consumer tags, ACK mode, prefetch và connection/channel nếu giao diện cung cấp.
- Các bindings từ exchange nào, routing key nào.
- Queue có **Single Active Consumer** hoặc exclusive consumer không.

Nếu consumer count bằng 0, không nên vội “purge ready messages” vì điều đó sẽ **xóa backlog chưa xử lý**.

### 3.2. CLI read-only để lấy dữ liệu

Dùng CLI trên node/cluster được phép vận hành:

```bash
# Thống kê queue trong vhost "/" (thay bằng vhost thực tế).
rabbitmqctl list_queues -p / \
  name type messages_ready messages_unacknowledged consumers state

# Những consumers broker hiện biết trong vhost "/".
rabbitmqctl list_consumers -p /

# Connection metadata: xác minh user, vhost và trạng thái.
rabbitmqctl list_connections name peer_host user vhost state

# Kiểm tra exchange và binding được định nghĩa như mong muốn.
rabbitmqctl list_exchanges -p / name type
rabbitmqctl list_bindings -p / source_name destination_name routing_key
```

Khi xử lý sự cố cụ thể, dùng RabbitMQ Management API hoặc `rabbitmqctl list_consumers` để biết consumer thuộc connection/channel nào. Chú ý dữ liệu từ một node đang bị partition có thể chưa phản ánh đầy đủ trạng thái cluster.

**Queue có message ready nghĩa là ít nhất một đường routing đã đưa message vào queue đó.** Nếu business code không chạy, root cause thường là tiêu thụ hoặc bạn đang quan sát sai nơi; không thể chỉ từ ready mà kết luận mọi routing key/publisher khác đều đúng.

### 3.3. Đối chiếu Spring connection config

Ví dụ Spring Boot:

```yaml
spring:
  rabbitmq:
    addresses: rabbit-a.internal:5672,rabbit-b.internal:5672
    virtual-host: /orders
    username: orders-consumer
    password: REPLACE_FROM_SECRET_MANAGER
```

Khi dùng cùng cluster, `addresses` là các endpoints thay thế cho connect/reconnect, **không phải hai broker độc lập để fan-out**. Nếu ứng dụng có nhiều `ConnectionFactory`, xác minh đúng `containerFactory` được chỉ định cho listener.

Đừng log password/connection URI có credential. Tên broker logic, vhost, queue, connection factory và listener ID thường đủ để đối chiếu nguồn gây lỗi.

## 4. Bước 2: kiểm tra Spring @RabbitListener có được tạo và khởi chạy chưa

### 4.1. Những trường hợp listener không được đăng ký

Ví dụ listener:

```java
@Component
public class OrdersConsumer {

    private final OrderProcessingService orderService;

    public OrdersConsumer(OrderProcessingService orderService) {
        this.orderService = orderService;
    }

    @RabbitListener(
            id = "ordersCreatedListener",
            queues = "orders.created.work")
    public void consume(String eventJson) {
        orderService.process(eventJson);
    }
}
```

`OrderProcessingService` là service nghiệp vụ giả định được Spring đăng ký dưới dạng bean. Constructor injection giúp ví dụ thể hiện rõ dependency của listener.

Một số nguyên nhân khiến method **không trở thành consumer đang chạy**:

1. Class không nằm trong package được Spring component-scan, thiếu `@Component`/`@Bean` hoặc bị loại bởi `@Profile`/`@Conditional`.
2. Hạ tầng xử lý `@RabbitListener` chưa được bật/cấu hình đúng. Trong Spring thuần, thường dùng `@EnableRabbit`; Spring Boot có các cơ chế auto-configuration nhưng vẫn phải kiểm tra cách ứng dụng bootstrap annotation infrastructure.
3. `@RabbitListener` bị đặt trên object không phải bean được Spring quản lý hoặc app chỉ khởi tạo bằng `new`.
4. Không có `RabbitListenerContainerFactory` đúng tên khi chỉ định `containerFactory`.
5. Factory sử dụng `ConnectionFactory` sai broker/vhost hoặc dùng credentials thiếu quyền.
6. Queue không tồn tại khi container bắt đầu, broker từ chối consume, hoặc topology declaration thất bại.
7. Listener ID trùng hoặc cấu hình endpoint lỗi làm Spring context không khởi tạo thành công.
8. Startup bị tắt có chủ đích bằng `autoStartup=false` ở annotation/factory hoặc thông qua lifecycle control.

**Phân biệt:** Một exception xảy ra **bên trong listener method** thông thường được container xử lý theo error/ack/retry policy và **không tự hủy vĩnh viễn mọi consumer**. Nếu thấy consumer count về 0, phải tìm sự kiện lifecycle/channel/queue tương ứng chứ không mặc định do một exception nghiệp vụ bất kỳ.

### 4.2. autoStartup=false và listener bị dừng

Ví dụ listener được cố ý không tự khởi chạy:

```java
@Component
public class PausedOrdersConsumer {

    @RabbitListener(
            id = "ordersCreatedListener",
            queues = "orders.created.work",
            autoStartup = "false")
    public void onOrder(String payload) {
        // Logic ứng dụng; method không chạy trước khi start container.
    }
}
```

Hoặc trong cấu hình container factory:

```java
@Bean("ordersListenerFactory")
SimpleRabbitListenerContainerFactory ordersListenerFactory(
        ConnectionFactory connectionFactory) {

    SimpleRabbitListenerContainerFactory factory =
            new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setAutoStartup(false); // Chỉ khởi chạy thủ công.
    factory.setConcurrentConsumers(2);
    factory.setPrefetchCount(10);
    return factory;
}
```

Nếu áp dụng cả hai ví dụ trong cùng context, phải tránh tạo **hai listener có cùng ID**; hãy xem chúng là **hai cách cấu hình thay thế**. Trong ứng dụng có `@RabbitListener(..., containerFactory="ordersListenerFactory")`, một factory không auto-start có thể làm toàn bộ listeners dùng factory đó không chạy cho tới khi được start.

Các thuộc tính `spring.rabbitmq.listener.simple.auto-startup` hoặc `spring.rabbitmq.listener.direct.auto-startup` của Spring Boot cũng có thể ảnh hưởng **factory được Boot tự cấu hình**, tùy loại container. Không nên chỉ đọc YAML rồi kết luận cấu hình cuối cùng nếu ứng dụng có custom factories hoặc bean overrides.

### 4.3. Kiểm tra runtime bằng RabbitListenerEndpointRegistry

Spring AMQP cung cấp `RabbitListenerEndpointRegistry` cho các container được tạo từ endpoints khai báo bằng `@RabbitListener`:

```java
@Component
public class OrdersListenerStatus {

    private final RabbitListenerEndpointRegistry registry;

    public OrdersListenerStatus(RabbitListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isRunningLocally() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersCreatedListener");

        return container != null && container.isRunning();
    }

    public void startForControlledRecovery() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersCreatedListener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener ID không được đăng ký trong registry");
        }
        if (!container.isRunning()) {
            container.start();
        }
    }

    public void pauseByOperator() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersCreatedListener");
        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
```

Các import chính:

```java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;
import org.springframework.amqp.rabbit.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;
```

**Ý nghĩa thực tế:**

- `getListenerContainer(id) == null`: Endpoint ID không hiện diện trong registry. Kiểm tra component scan, condition/profile, `@RabbitListener` infrastructure và ID; đừng vội cố `start()`.
- `container.isRunning() == false`: Container local đang dừng. Xác minh đây là **pause có chủ đích** hay lỗi startup trước khi start.
- `container.isRunning() == true`: Container lifecycle đang chạy, **chưa chứng minh** broker đã chấp nhận `basic.consume` hoặc đang delivery. Vẫn phải đối chiếu consumer count trên queue/vhost.
- Registry chỉ bao phủ các listener containers nó quản lý. Một số containers tạo như **bean độc lập** hoặc tích hợp khác có thể không nằm trong registry; khi đó cần kiểm tra bean/lifecycle tương ứng.

**Cảnh báo:** Đưa `startForControlledRecovery()`/`pauseByOperator()` vào một endpoint quản trị production cần authentication, authorization, audit log và tránh thao tác từ lệnh không có quyền. Ví dụ chỉ minh họa API lifecycle, không khuyến khích mở public HTTP “start/stop listener”.

### 4.4. Spring Boot startup logs và profile

Kiểm tra log tại lúc startup, trước khi queue bắt đầu tăng ready:

- Spring application context có khởi tạo thành công không?
- Class chứa `@RabbitListener` có được tạo và profile đúng không?
- RabbitListenerEndpointRegistry có endpoint với ID mong đợi không?
- Factory đã chọn là simple hay direct listener container, và dùng connection factory nào?
- Container đã cố đăng ký consumer chưa? Có retry/recover liên tục không?
- Có lỗi credentials, vhost, certificate, hostname hoặc queue missing không?

Có thể bật DEBUG **tạm thời** ở package phù hợp để thu thập lifecycle logs:

```yaml
logging:
  level:
    org.springframework.amqp.rabbit.listener: DEBUG
    org.springframework.amqp.rabbit.connection: DEBUG
    org.springframework.amqp.rabbit.core.RabbitAdmin: DEBUG
```

Cẩn thận dung lượng log và thông tin nhạy cảm; không để DEBUG dài hạn cho luồng traffic cao. Các dòng log chính xác thay đổi theo Spring AMQP version.

## 5. Bước 3: xác định consumer bị ai hủy và khi nào

### 5.1. Cancel bởi ứng dụng khác cancel bởi broker

Ở AMQP 0-9-1, consumer được đăng ký qua `basic.consume`. Một consumer có thể biến mất vì:

| Nguồn | Tình huống | Thứ cần tìm |
|---|---|---|
| **Ứng dụng** | Gọi `container.stop()`, shutdown context, rolling deployment | Deployment events, lifecycle logs, registry.isRunning |
| **Broker** | Queue bị xóa; broker gửi asynchronous `basic.cancel` notification nếu client hỗ trợ | RabbitMQ logs, queue deletion audit, cancellation callback/event |
| **Broker/channel** | Channel đóng do lỗi protocol, permission hoặc consumer ack timeout | Channel.close reason, `404 NOT_FOUND`, `403 ACCESS_REFUSED`, `PRECONDITION_FAILED` |
| **Network** | Connection mất, heartbeat timeout, TLS/socket lỗi | Connection/shutdown logs, client reconnect |
| **Cluster/queue** | Quorum leader election hoặc queue tạm unavailable | Queue leader/quorum health, connection/consumer re-registration |
| **Exclusive consumer** | Có consumer khác giành quyền exclusive hoặc queue policy hạn chế | `RESOURCE_LOCKED`/`ACCESS_REFUSED` và danh sách consumers |
| **Application startup** | Chưa có container hoặc autoStartup bị tắt | Registry, bean conditions, factory config |

**Consumer bị broker hủy** không nhất thiết đồng nghĩa queue bị xóa. Nhưng **xóa một queue** có consumer sẽ khiến broker hủy những registrations liên quan. Nếu queue bị xóa, **nội dung queue cũ cũng mất**; khi queue được tạo lại với cùng tên, backlog mới nhìn thấy không phải là bằng chứng message cũ đã sống sót.

Trái lại, một client tự dừng consumer bằng `basic.cancel` hoặc đóng channel **không nhất thiết xóa queue durable**, vì vậy message đã ready có thể nằm nguyên trong queue và tiếp tục tích tụ.

### 5.2. Queue bị xóa trong lúc consumer đang chạy

```text
RabbitMQ                       Spring listener container
   |                                      |
   |<------------ basic.consume ----------|
   |------------- consume-ok ------------>|
   |                                      |
   |   operator deletes queue             |
   X  queue bị xóa                        |
   |------------- basic.cancel ---------->|
   |                                      |
   |                         mất đăng ký consumer
   |                         bắt đầu recovery theo policy
   |
   |   queue được tạo lại                 |
   |<---------- basic.consume -----------|
   |------------- consume-ok ------------>|
```

Trong sự cố này phải điều tra **ai đã xóa queue** (IaC rollout, operator, API, lifecycle auto-delete, temporary/exclusive queue). Không chỉ restart listener rồi bỏ qua nguyên nhân vì cùng tình huống có thể tái diễn.

**Đối với queue durable, không auto-delete**, việc dừng consumer thông thường **không xóa queue**. Nếu queue biến mất, hãy xem queue declaration, vhost, policies, loại queue và audit trail.

### 5.3. Missing queue lúc startup

Nếu listener subscribe `orders.created.work` nhưng queue chưa được declare:

- Broker có thể báo `404 NOT_FOUND` khi client cố consume/passive declare.
- Container có thể log missing queue, retry theo cấu hình hoặc không khởi động thành công; default chi tiết tùy container type và Spring AMQP version.
- `RabbitAdmin` có thể chưa chạy, cấu hình `spring.rabbitmq.dynamic=false`, auto-declaration bị vô hiệu hoặc service account không có quyền configure.
- Queue có thể được provision bằng IaC và deployment ứng dụng chạy **trước** bước tạo topology.
- Nếu ứng dụng dùng `queuesToDeclare`/`bindings`, kiểm tra admin khai báo lên **đúng broker/vhost**, đặc biệt môi trường nhiều `ConnectionFactory`.

Thuộc tính như `missingQueuesFatal` cho phép điều chỉnh hành vi khi queue thiếu, **không nên dùng để che lỗi topology**. Một hệ thống critical cần readiness/alert thể hiện listener chưa subscribe được, thay vì âm thầm “running” mà không có consumer.

### 5.4. Ack timeout hoặc lỗi protocol đóng channel

Nếu consumer đã nhận message nhưng không ACK quá thời hạn do broker policy/consumer timeout, RabbitMQ có thể đóng channel với `PRECONDITION_FAILED`. Các delivery chưa ACK được broker xử lý lại theo quy tắc tương ứng, thường trở về sẵn sàng/redelivery sau connection/channel recovery.

Dấu hiệu:

- Trước sự cố `messages_unacknowledged` tăng, lâu không ACK.
- Channel shutdown logs có lý do liên quan delivery acknowledgment timeout.
- Sau channel close, consumer count giảm hoặc thay đổi trong lúc container recovery.
- `messages_ready` tăng lại do redelivery, rồi có thể giảm khi consumer đăng ký lại.

**Không kết luận “listener chưa chạy từ đầu”** chỉ vì sau sự cố thấy ready và consumers=0. Xem timeline trước đó để phân biệt **never started** với **started then cancelled**.

## 6. Bước 4: kiểm tra quyền, queue type và lỗi connection

### 6.1. Sai credentials và virtual host

Một số lỗi phổ biến:

- User/password không hợp lệ hoặc credential đã được rotate mà app chưa reload.
- User không được phép truy cập vhost.
- App kết nối `/orders` trong khi queue được provision tại `/billing`.
- User thiếu quyền **read** queue, dẫn tới `basic.consume` thất bại; tài khoản provision topology có thể cần quyền **configure** tùy cơ chế triển khai.
- TLS CA/hostname sai; network firewall chặn port; DNS trỏ sai cluster hoặc sai môi trường.

Dù publisher hoạt động, consumer có thể thất bại vì **hai thành phần dùng account/vhost/connection factory khác nhau**. Hãy kiểm tra cả publisher và listener, không suy từ một service khỏe rằng service kia chắc chắn có quyền.

### 6.2. Quorum queue và leader election

Với quorum queue, consumer có thể tạm ngưng tiến triển khi queue bầu leader hoặc mất majority members. Một node vẫn còn TCP connectivity và RabbitMQ Management có thể vẫn truy cập, nhưng queue cụ thể không phục vụ delivery.

Kiểm tra riêng:

```bash
rabbitmq-diagnostics cluster_status
rabbitmq-queues quorum_status -p / orders.created.work
rabbitmq-diagnostics check_if_node_is_quorum_critical
```

Chỉ chạy `quorum_status` cho queue thực sự là **quorum**. Với classic queue, phân tích node giữ queue và tình trạng node/connection theo queue type. Không chữa lỗi mất quorum bằng cách tùy tiện xóa/declare lại queue, vì có nguy cơ mất dữ liệu.

### 6.3. Exclusive và Single Active Consumer

RabbitMQ có những chế độ giảm số consumer thực sự có thể nhận delivery:

- **Exclusive consumer:** Cấu hình một consumer độc quyền khiến consumer thứ hai bị từ chối nếu có tranh chấp. Lỗi thường xuất hiện lúc đăng ký, chứ không phải method Java vẫn chạy bình thường.
- **Single Active Consumer (SAC):** Queue có thể có **nhiều consumers đăng ký**, nhưng chỉ một consumer active được nhận delivery tại một thời điểm; những consumer khác standby. Nếu active consumer chậm, ready vẫn có thể tăng dù `consumers > 0`.
- **Prefetch limit:** Broker đã gửi đủ unacked deliveries tới consumer, sẽ không cấp thêm cho tới khi ACK; queue tiếp tục có ready.

Vì thế cần đọc **consumer count, active status, prefetch, unacked và deliver/ack rates cùng nhau**. Đừng chỉ nhìn số pod đang chạy.

## 7. Ví dụ cấu hình listener tránh nhầm đích

### 7.1. Topology được khai báo rõ

```java
@Configuration
public class OrderTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events");
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable("orders.created.work").build();
    }

    @Bean
    Binding ordersBinding(
            DirectExchange ordersExchange,
            Queue ordersQueue) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange).with("orders.created");
    }
}
```

Imports chính: `org.springframework.amqp.core.DirectExchange`, `Queue`, `QueueBuilder`, `Binding`, `BindingBuilder`, `org.springframework.context.annotation.Configuration` và `Bean`.

**Đừng dùng auto-declare để “sửa” một queue quan trọng mất tích mà chưa biết vì sao nó biến mất.** Trong ứng dụng production, có thể provision topology trước qua IaC, sau đó chỉ bật/tắt khai báo tự động theo chính sách vận hành. Với queue đã có, nếu đổi queue type/arguments không tương thích, broker trả lỗi `PRECONDITION_FAILED`; phải có migration plan, không restart vô hạn.

### 7.2. Listener container factory minh bạch

```java
@Configuration
@EnableRabbit
public class OrderListenerConfiguration {

    @Bean("ordersListenerFactory")
    SimpleRabbitListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {

        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(10);
        factory.setAutoStartup(true);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
```

Và listener:

```java
@Component
public class OrderCreatedConsumer {

    private final OrderProcessingService processingService;

    public OrderCreatedConsumer(OrderProcessingService processingService) {
        this.processingService = processingService;
    }

    @RabbitListener(
            id = "ordersCreatedListener",
            queues = "orders.created.work",
            containerFactory = "ordersListenerFactory")
    public void consume(String payload) {
        processingService.applyOnce(payload);
    }
}
```

Các imports liên quan: `org.springframework.amqp.rabbit.annotation.EnableRabbit`, `RabbitListener`, `org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory`, `org.springframework.amqp.rabbit.connection.ConnectionFactory`, `org.springframework.amqp.core.AcknowledgeMode`, `org.springframework.context.annotation.Bean`/`Configuration` và `org.springframework.stereotype.Component`.

Đây là cấu hình minh họa. Cần service `OrderProcessingService` thực sự được đăng ký và có phương thức `applyOnce`. `defaultRequeueRejected(false)` chỉ an toàn khi **có DLX/DLQ và retry policy được thiết kế**; nếu message bị reject không requeue mà không có DLX, nó có thể bị loại mất. Không dùng việc chỉnh ACK mode để che vấn đề container chưa được đăng ký.

### 7.3. Nếu có nhiều RabbitMQ brokers

Trong môi trường nhiều connection factories, listener phải chỉ rõ factory đúng:

```java
@RabbitListener(
        id = "ordersCreatedListener",
        queues = "orders.created.work",
        containerFactory = "ordersListenerFactory")
public void consume(String payload) {
    // Consumer thuộc ordersListenerFactory -> ordersConnectionFactory.
}
```

Kiểm tra `ordersListenerFactory` được inject `ordersConnectionFactory` của đúng cluster/vhost. Queue có cùng tên trên broker Audit sẽ không tự nhận event từ Orders. Nếu thiếu `containerFactory` và ứng dụng có default listener factory khác, listener có thể consume sai nơi dù không ném lỗi compile.

## 8. Recovery sau basic.cancel và connection loss

### 8.1. Một container “running” có thể đang retry

`SimpleMessageListenerContainer` và `DirectMessageListenerContainer` có những cơ chế phục hồi/giám sát consumer khác nhau. Khi broker cancel consumer hoặc connection mất, Spring thường có logic tạo lại consumer theo cấu hình; nhưng **không có bảo đảm mọi lỗi tự lành nếu nguyên nhân vẫn tồn tại**.

Vì vậy một container có `isRunning()=true` vẫn có thể tạm thời không có broker-side consumer khi:

- Queue chưa tồn tại hoặc chưa thể consume.
- App đang reconnect với node khác.
- Queue quorum tạm unavailable.
- Permission/credential chưa được sửa.
- Broker vừa gửi `basic.cancel` nhưng container chưa đăng ký lại.
- Consumer declarations liên tục gặp `404`/`403` hoặc inequivalent queue arguments.

Theo dõi **recovery attempts, thời gian không có consumer, mức tăng `messages_ready` và số lần listener failed/cancelled**. Không chỉ kiểm tra một lần ngay lúc application start.

### 8.2. Lifecycle events trong Spring

Spring AMQP có các application events liên quan listener container lifecycle và failures, ví dụ `ListenerContainerConsumerFailedEvent`; tùy container/phiên bản còn có sự kiện consumer started/terminated hoặc queue missing.

Một listener quan sát sự cố có thể dùng:

```java
@Component
public class RabbitConsumerFailureObserver {

    private static final Logger log =
            LoggerFactory.getLogger(RabbitConsumerFailureObserver.class);

    @EventListener
    public void onFailure(ListenerContainerConsumerFailedEvent event) {
        log.warn(
                "Rabbit consumer failed: reason={} fatal={} source={}",
                event.getReason(),
                event.isFatal(),
                event.getSource());
    }
}
```

Imports tiêu biểu: `org.springframework.context.event.EventListener`, `org.springframework.stereotype.Component`, `org.springframework.amqp.rabbit.listener.ListenerContainerConsumerFailedEvent`, `org.slf4j.Logger` và `org.slf4j.LoggerFactory`.

Event cho biết consumer/container có vấn đề, **không tự xác định đầy đủ** queue nào bị ảnh hưởng nếu một container nghe nhiều queues. Gắn listener ID, connection factory alias, queue/vhost (từ cấu hình/runtime metadata) vào structured logging khi có thể. Không ghi payload hoặc credentials trong logs.

### 8.3. Khi nào nên start lại bằng API?

Nếu listener bị **stop chủ đích** do maintenance/pause, có thể dùng `RabbitListenerEndpointRegistry.getListenerContainer(id).start()` sau khi có change authorization và đã xác nhận broker/queue khỏe.

Nếu lỗi là **thiếu queue hoặc quyền read**, chỉ gọi `start()` thường không sửa được. Khắc phục root cause trước, sau đó xác minh broker nhận `basic.consume` và `consumers` tăng.

Nếu queue vừa bị xóa, khôi phục topology **đúng định nghĩa** và xác minh dữ liệu mất/còn; không khẳng định ready messages cũ tự quay lại chỉ vì queue mới được tạo.

## 9. Đừng nhầm listener cancelled với listener chậm

Khi broker hiển thị `consumers > 0` mà `messages_ready` vẫn tăng:

```text
Queue ready=5000
    |
    +-- consumer #1: prefetch=20, unacked=20
    |                    |
    |                    +-- handler chờ DB lock
    |
    +-- consumer #2: prefetch=20, unacked=20
                         |
                         +-- handler gọi HTTP timeout
```

Cả hai consumers **đã đăng ký thành công**. Broker không thể giao thêm vì prefetch đã đầy và ACK không tới. Nếu chỉ xem ready, người vận hành dễ restart listener rồi tạo thêm redelivery, làm vấn đề tệ hơn.

Để phân biệt:

- `consumers=0`: ưu tiên điều tra **registration/lifecycle/cancellation**.
- `consumers>0, unacked cao`: ưu tiên điều tra **handler, DB, prefetch, ACK, thread pools**.
- `consumers>0, unacked thấp, ready cao`: kiểm tra consumer active, SAC/exclusive, consumer capacity, queue state, blocked connections, phân phối workload.
- `consumers>0, deliver rate cao, ACK rate thấp`: message đang được giao nhưng không hoàn thành, có thể có retry/requeue loop.
- `ready=0, unacked cao`: backlog đã chuyển sang in-flight; chưa phải xử lý xong.

**Một message từ `ready` sang `unacked` không chứng minh business method đã hoàn tất.** Việc tăng `prefetch` có thể làm ready giảm nhưng khiến nhiều message chờ ở buffer consumer hơn.

## 10. Thu thập bằng chứng: timeline trước và sau sự cố

Một bộ bằng chứng tốt cho incident:

| Thời điểm | Cần lưu | Lý do |
|---|---|---|
| Trước deployment/restart | Consumer count, ready/unacked, listener IDs | Có đang hoạt động bình thường? |
| Khi bắt đầu backlog | Publish/deliver/ACK rate, queue/vhost | Biết queue ngừng tiêu thụ từ lúc nào |
| Khi consumer biến mất | Application logs, broker cancellation/channel close | Tìm sự kiện lifecycle |
| Khi app reconnect | Connection factory endpoint, vhost, credentials status | Phân biệt sai broker với queue unavailable |
| Khi sửa cấu hình | Thay đổi profile, factory, topology, queue policy | Xác định nguyên nhân gốc được xử lý |
| Sau phục hồi | Consumer count, ready giảm, ACK tăng, business DB commit | Chứng minh thực sự xử lý backlog |

### 10.1. Structured log nên có gì?

Ví dụ minh họa:

```text
timestamp=2026-11-26T03:05:00Z
service=orders-consumer
listenerId=ordersCreatedListener
brokerAlias=orders-cluster
vhost=/orders
queue=orders.created.work
containerRunning=true
brokerConsumerCount=0
ready=14523
unacked=0
exceptionCategory=QUEUE_NOT_FOUND
recoveryAttempt=12
```

Đây là **sự kiện tổng hợp cần tự instrument/ghi nhận**, không phải một log line Spring tự phát ra nguyên dạng. Tương quan listener ID, queue và connection với broker-side event giúp tránh tìm sai container giữa hàng chục microservices.

Không log password, URI chứa credential, JWT, business payload nhạy cảm hay dữ liệu định danh khách hàng không cần thiết.

## 11. Các metric và alert dành riêng cho consumer registration

| Metric/alert | Khi nào có ý nghĩa? | Ghi chú |
|---|---|---|
| `rabbitmq_queue_messages_ready` hoặc metric tương đương | Ready backlog đang tăng | Kiểm tra tên metric và endpoint theo plugin/version |
| `rabbitmq_queue_consumers` hoặc `rabbitmq_detailed_queue_consumers` | Consumer count giảm về 0 | Tên series có thể khác theo Prometheus endpoint/config |
| `rabbitmq_queue_messages_unacked` | Phát hiện in-flight chờ ACK | Không nhầm với ready |
| `app.rabbit.listener.running` | Container local đang chạy/dừng | Chỉ quan sát lifecycle, không chứng minh broker registration |
| `app.rabbit.listener.registration.failures` | Queue missing, auth failures, cancelled/recover loops | Phát sinh từ events/logging ở ứng dụng |
| `app.rabbit.listener.recovery.attempts` | Container liên tục thử reconnect | Cần phân loại exception để tránh alert nhiễu |
| `app.rabbit.business.processed.total` | Nghiệp vụ thực sự commit | Không chỉ dựa vào consumer ACK |
| `app.rabbit.consumer.effective.lag` | Tuổi message từ nguồn đến business commit | Phải định nghĩa nguồn timestamp rõ ràng |

**Quan trọng:** RabbitMQ Prometheus plugin có những metric families/endpoint chi tiết; không mặc định mọi tên metric `rabbitmq_detailed_*` xuất hiện trên `/metrics` của mọi môi trường. Kiểm tra thực tế exposition endpoint và Prometheus scrape config.

### 11.1. Alert có ý nghĩa nghiệp vụ

Một alert có thể là:

> Queue `orders.created.work` có ready lớn hơn 100 trong 5 phút **và** consumer count bằng 0, trong khi publish rate vẫn dương.

Kết hợp điều kiện tránh báo nhầm khi queue cố ý tạm dừng vài giây trong rolling deployment. Tuy nhiên nếu queue rất quan trọng, **consumer count=0 liên tục** cũng có thể cần alert ngay cả khi chưa có message, vì hệ thống sẽ mất năng lực nhận sự kiện mới.

Nên có alert tách biệt:

- **Critical:** Critical queue không có consumer ngoài maintenance window.
- **Critical:** Queue có ready tăng + consumers=0.
- **Warning:** Consumer recovery loop hoặc broker cancels liên tục.
- **Warning:** Unacked cao + ACK rate thấp, vì đây là bottleneck khác.
- **Critical:** End-to-end business event age vượt SLO, dù RabbitMQ queue depth có vẻ thấp.

**Readiness/health caveat:** Spring Boot Rabbit health contributor thường tập trung vào kết nối hoặc một thao tác broker phù hợp, **không mặc định chứng minh mọi `@RabbitListener` đang đăng ký và xử lý đúng queue**. Cần bổ sung health logic cho critical listener hoặc metrics từ broker khi mục tiêu đó là bắt buộc.

## 12. Runbook khôi phục không làm mất message

### 12.1. Phân loại trước khi thao tác

| Trường hợp | Hành động đúng | Điều cần tránh |
|---|---|---|
| Listener `autoStartup=false` có chủ đích | Xác nhận change/maintenance đã kết thúc, start container có kiểm soát | Restart cả cluster RabbitMQ không cần thiết |
| Component scan/profile sai | Sửa deploy config/code, rollout đúng artifact | Purge queue để ready về 0 |
| Sai vhost/credentials | Sửa secret, permissions, endpoint rồi reconnect | Tăng prefetch/concurrency vô ích |
| Queue missing vì chưa provision | Restore topology đúng, xác minh quyền và dữ liệu cũ | Tạo queue cùng tên nhưng type/arguments khác |
| Queue bị xóa khi đang consume | Điều tra audit, recreate bằng quy trình được phê duyệt, đánh giá mất dữ liệu | Khẳng định backlog cũ sẽ tự phục hồi |
| Channel ack timeout | Điều tra handler/DB, timeout config, ACK mode; sau đó recovery | Tăng timeout vô hạn mà không chữa handler |
| Quorum queue unavailable | Khôi phục majority/leader theo runbook broker | Xóa/force-recreate queue tùy tiện |
| Consumers còn nhưng unacked cao | Tối ưu downstream, prefetch, retry/backpressure | Coi đây là lỗi listener “chưa chạy” |

### 12.2. Quy trình từng bước

1. **Giữ nguyên backlog:** Không purge, delete hay sửa queue arguments. Nếu queue là business-critical, đánh dấu incident và bảo vệ bằng chứng.
2. **Chụp số liệu:** Ready/unacked/consumers, queue type, vhost, publish/deliver/ack rates, logs lúc consumer count giảm.
3. **Kiểm tra local lifecycle:** Bean/listener ID, registry `isRunning()`, `autoStartup`, profiles, application pod status.
4. **Kiểm tra broker registration:** `list_consumers` trên đúng vhost; consumer tags, connection/channel, exclusive/SAC nếu có.
5. **Kiểm tra failure reason:** `basic.cancel`, `404` queue missing, `403` permission, `PRECONDITION_FAILED`, network/heartbeat, quorum leader.
6. **Sửa nguyên nhân gốc:** Provision topology, restore quyền, sửa factory/vhost, khôi phục cluster, hoặc start listener theo quy trình.
7. **Giới hạn tốc độ phục hồi:** Khi backlog lớn, tăng concurrency/prefetch từ từ, bảo vệ DB/HTTP downstream và sử dụng idempotency.
8. **Quan sát tiến triển:** Consumer count >0, deliver/ACK rates dương, ready giảm theo thời gian, unacked không bị kẹt kéo dài.
9. **Đối soát nghiệp vụ:** Event IDs đã commit, duplicate skips, DLQ và retry backlog, không chỉ queue depth.
10. **Đóng incident:** Ghi root cause, timeline, preventive action, alert và test regression.

### 12.3. Backlog sau khi listener chạy lại

Nếu listener đã ngừng trong 30 phút, có thể có hàng trăm nghìn message ready. Khi khôi phục:

- Không tăng `concurrentConsumers` lên cực lớn ngay lập tức; DB có thể bị connection starvation và queue lại chuyển thành unacked backlog.
- Dùng backpressure/rate limiting khi downstream có quota.
- Xem publish rate có cao hơn ACK rate hay không; nếu vẫn cao hơn, backlog tiếp tục tăng dù listener đã hoạt động.
- Giữ retry hữu hạn/backoff, phân loại poison messages để tránh một message hỏng làm container thất bại lặp lại.
- Consumer phải idempotent: các delivery chưa ACK trước sự cố có thể được broker giao lại sau reconnect.

**Một kết luận “đã phục hồi” phải dựa trên nghiệp vụ đã tiến triển**, không chỉ `isRunning()=true` hoặc ready giảm về 0 do purge.

## 13. Integration test mô phỏng listener chưa chạy

Unit test với Mockito chỉ cho biết app đã gọi `RabbitTemplate` hoặc method handler nào; nó **không thể chứng minh broker có consumer đăng ký hay ready backlog được tiêu thụ sau container.start()**. Vì vậy cần integration test trên RabbitMQ thật, ví dụ dùng Testcontainers.

### 13.1. Mô hình kiểm thử

```text
Spring Boot test -> RabbitTemplate -> direct exchange -> durable test queue
                                                 |
                                       listener autoStartup=false
                                                 |
                                   before start: ready=1, consumers=0
                                                 |
                               RabbitListenerEndpointRegistry.start()
                                                 |
                                   after start:  handled=1, ready=0
```

Các dependencies test cần có: Spring Boot AMQP, `spring-boot-starter-test`, Testcontainers RabbitMQ + JUnit Jupiter; có thể dùng Awaitility để chờ điều kiện bất đồng bộ. Ví dụ dùng Testcontainers 1.x; package container thay đổi ở Testcontainers 2.x.

### 13.2. Listener dành cho test

```java
@Component
public class TestOrdersListener {
    private final List<String> processed =
            new CopyOnWriteArrayList<>();

    @RabbitListener(
            id = "testOrdersListener",
            queues = "it.listener.orders",
            autoStartup = "false")
    public void handle(String body) {
        processed.add(body);
    }

    public List<String> processed() {
        return processed;
    }
}
```

Trong test, cần thêm topology riêng:

```java
@TestConfiguration
public class TestOrderTopology {

    @Bean
    Queue testQueue() {
        return QueueBuilder.durable("it.listener.orders").build();
    }

    @Bean
    DirectExchange testExchange() {
        return new DirectExchange("it.listener.events");
    }

    @Bean
    Binding testBinding(Queue testQueue, DirectExchange testExchange) {
        return BindingBuilder.bind(testQueue)
                .to(testExchange).with("created");
    }
}
```

Các class có `@Component`/`@TestConfiguration` phải được đưa vào context của integration test. Đảm bảo ứng dụng đang dùng một queue test **riêng**, không có service khác consume. Không chạy trên queue production.

### 13.3. Test start listener và giải phóng backlog

Các bước cốt lõi (đặt trong một test class có `@SpringBootTest`, RabbitMQ Testcontainer và `@DynamicPropertySource` kết nối đến mapped port):

```java
@Autowired RabbitTemplate template;
@Autowired RabbitAdmin admin;
@Autowired RabbitListenerEndpointRegistry registry;
@Autowired TestOrdersListener testListener;

@Test
void queuedMessageWaitsUntilListenerStarts() throws Exception {
    // Đảm bảo topology đã được khai báo và listener đang dừng.
    admin.initialize();

    MessageListenerContainer container =
            registry.getListenerContainer("testOrdersListener");
    assertThat(container).isNotNull();
    assertThat(container.isRunning()).isFalse();

    template.convertAndSend(
            "it.listener.events", "created", "ORDER-501");

    // Không dùng Thread.sleep. Chờ broker ghi nhận message ready.
    await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
        Map<String, Object> stats =
                admin.getQueueProperties("it.listener.orders");
        assertThat(stats).isNotNull();
        int ready = ((Number) stats.get(
                RabbitAdmin.QUEUE_MESSAGE_COUNT)).intValue();
        int consumers = ((Number) stats.get(
                RabbitAdmin.QUEUE_CONSUMER_COUNT)).intValue();

        assertThat(ready).isEqualTo(1);
        assertThat(consumers).isZero();
    });

    // Khôi phục consumer một cách có kiểm soát.
    container.start();

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
            assertThat(testListener.processed())
                    .containsExactly("ORDER-501"));

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
        Map<String, Object> stats =
                admin.getQueueProperties("it.listener.orders");
        assertThat(((Number) stats.get(
                RabbitAdmin.QUEUE_MESSAGE_COUNT)).intValue()).isZero();
    });

    container.stop();
}
```

**Chú ý kiểu dữ liệu:** Các giá trị trả từ `RabbitAdmin.getQueueProperties` là `Number`; ép sang `intValue()` trước khi dùng AssertJ `isEqualTo(...)` hoặc `isZero()` như đoạn kiểm thử. Phương thức này truy vấn queue bằng passive declaration và có thể trả `null` khi queue không tồn tại, vì vậy cần kiểm tra null trước khi đọc stats. Truy vấn chỉ phục vụ chẩn đoán/test có giới hạn; không gọi nó với tần suất cao trên đường xử lý mỗi message.

Dự án thực cần cleanup queue sau test, cô lập listener ID và tên queue để không bị xung đột khi CI chạy parallel. Có thể dùng suffix unique/queue properties hay một context riêng cho test. Khi container đã nhận delivery, verify danh sách processed an toàn thread bằng `CopyOnWriteArrayList`; nếu handler có DB transaction, thay bằng kiểm tra DB commit và idempotency.

### 13.4. Những chi tiết cần tránh trong integration test

- **Không** gọi `Thread.sleep(1000)` rồi assert readiness; dùng `Awaitility` hoặc polling có timeout.
- **Không** dùng `RabbitTemplate.receive(...)` để quan sát ready trên queue đang test lifecycle: lệnh này **tự lấy message** và làm sai số liệu test.
- **Không** dùng consumer thật khác cạnh tranh trên queue test.
- **Không** bắt buộc broker count thay đổi ngay lập tức: registration/delivery/ACK bất đồng bộ.
- **Không** test “stop listener” bằng xóa queue thật rồi giả định message cũ vẫn tồn tại.
- **Không** dùng một listener có `autoStartup=false` mà vẫn kỳ vọng broker `consumers=1` trước start.
- **Không** chỉ assert ready giảm: phải kiểm tra handler/business side effect để chứng minh message được xử lý chứ không bị purge/drop.

## 14. Kiểm thử broker cancel và recovery

### 14.1. Test broker-side consumer cancellation

Chạy trên **lab riêng**:

1. Tạo queue có tên cố định cho test, khởi chạy listener và chờ broker hiện `consumers=1`.
2. Tạm **xóa queue test** bằng API/broker control để tạo consumer cancellation.
3. Quan sát Spring logs/events: consumer nhận cancel hoặc registration failure, `consumers=0` (hoặc queue không còn tồn tại).
4. Xác định container đang retry/recover như thế nào theo version và cấu hình.
5. Khai báo lại queue với **đúng arguments**, binding và permissions.
6. Chờ consumer đăng ký lại và publish **một message mới**; xác minh handler nhận message.
7. Không khẳng định message cũ từ queue bị xóa đã được bảo toàn: deletion làm mất nội dung queue.

**Không thực hiện kịch bản này trên production** hoặc queue có dữ liệu thật. Nó kiểm tra khả năng ứng dụng **nhận tín hiệu cancel và recover**, không phải kiểm thử backup.

### 14.2. Test application-initiated stop/start

1. Có queue durable và listener chạy với ID cố định.
2. Gọi `registry.getListenerContainer(id).stop()` trong lab.
3. Xác minh broker consumer count giảm về 0.
4. Publish một message mới; nó trở thành `ready`.
5. Gọi `start()`; message được giao và ACK sau khi xử lý.
6. Đối chiếu thời điểm stop/start với application audit log, để phân biệt maintenance có chủ đích với broker cancel.

Dừng một listener không đồng nghĩa xóa durable queue. Nếu data bị mất sau stop/start, cần điều tra TTL, expiration, DLX, purge, queue auto-delete hoặc route khác.

### 14.3. Test permission và missing queue

Trong môi trường test:

- Chạy consumer bằng service account không có quyền read trên queue; xác minh lỗi đăng ký, broker consumer count=0 và log permissions.
- Chạy app trước khi provision queue; quan sát missing queue log và chính sách retry/fatal.
- Provision queue đúng type/vhost, cấp quyền cần thiết và xác minh consumer hoạt động.
- Cố ý dùng sai vhost và tạo queue cùng tên ở vhost khác để chứng minh phải đối chiếu cả vhost, không chỉ queue name.

Những test này ngăn nhóm phát triển chẩn đoán nhầm “RabbitMQ không deliver” khi consumer thực chất chưa subscribe được.

## 15. Tình huống tổng hợp: xử lý incident thực tế

Giả sử ngày triển khai mới, RabbitMQ hiển thị:

```text
vhost=/orders
queue=orders.created.work
messages_ready=24870
messages_unacknowledged=0
consumers=0
publish_rate=120 msg/s
deliver_rate=0 msg/s
ack_rate=0 msg/s
```

Spring Boot pod vẫn báo `UP` trên health endpoint. Operator nghĩ “ứng dụng khỏe, broker đang bị delay”.

Các bước chính xác:

1. Kiểm tra **RabbitMQ queue/vhost** trùng với Spring app config. Nếu vhost sai, sửa endpoint trước.
2. Dùng `RabbitListenerEndpointRegistry` thấy `ordersCreatedListener` có trong registry nhưng `isRunning()=false`.
3. Kiểm tra config deploy mới và phát hiện `spring.rabbitmq.listener.simple.auto-startup=false` trong profile production hoặc một operator gọi `stop()` nhưng chưa resume.
4. Xác minh đây không phải pause có chủ đích; sửa config/điều phối restart hoặc dùng controlled `start()`.
5. Chờ broker consumer count tăng (ví dụ lên 2 với `concurrentConsumers=2`) và deliver/ack rates phục hồi.
6. Đo ready trend: nếu rate ACK lớn hơn publish rate, backlog giảm dần; nếu không, cần capacity planning.
7. Theo dõi DB latency, unacked và DLQ; không tăng concurrency quá nhanh vì có thể làm DB quá tải.
8. Đối soát event IDs đã xử lý, duplicate skips và business state.

**Kết luận:** Pod “UP” hoặc `container.isRunning()` không đủ. Chỉ sự kết hợp **consumer registration trên broker + ACK throughput + business commit** mới xác nhận đường xử lý đã phục hồi.

### 15.1. Một incident trông giống nhưng nguyên nhân khác

```text
messages_ready=24870
messages_unacknowledged=40
consumers=2
publish_rate=120/s
deliver_rate=1/s
ack_rate=1/s
```

Ở đây listener **đã đăng ký**, nhưng broker có 40 delivery chưa ACK; nếu mỗi consumer `prefetch=20`, có thể cả hai đã đầy prefetch. Kiểm tra DB/HTTP call, lock contention, listener threads và timeout. Giải pháp **không** phải “bật @EnableRabbit” mà là xử lý bottleneck nghiệp vụ/downstream.

## 16. Những ngộ nhận phổ biến

| Nhận định sai | Điều đúng cần nhớ |
|---|---|
| “Ready tăng thì broker không route được.” | Message ready đã **ở trong queue**; cần kiểm tra consumer và đúng queue/vhost. |
| “Spring pod UP nghĩa là `@RabbitListener` đang consume.” | Health có thể chỉ kiểm tra kết nối, không bảo đảm broker registration. |
| “`isRunning()=true` nghĩa là broker consumers>0.” | Container có thể đang reconnect hoặc lỗi đăng ký. |
| “Consumers>0 thì ready không thể tăng.” | Prefetch đầy, handler chậm, SAC hoặc consumer capacity thấp vẫn tạo backlog. |
| “Unacked nghĩa là message đã xử lý xong.” | Đã delivery nhưng chưa có ACK, có thể vẫn đang xử lý/chờ buffer. |
| “Một exception trong listener luôn hủy consumer.” | Thường container tiếp tục và xử lý reject/requeue; phải xem lỗi lifecycle cụ thể. |
| “Đổi `prefetch=1000` sẽ làm listener đã dừng chạy lại.” | Prefetch không khởi tạo hay đăng ký consumer. |
| “Queue bị xóa rồi tạo lại cùng tên thì message cũ còn.” | Xóa queue có thể làm mất toàn bộ nội dung queue cũ. |
| “Không thấy consumer nghĩa là queue không tồn tại.” | Queue có thể vẫn tồn tại và tích lũy ready. |
| “Publisher và listener cùng queue name nên chắc dùng chung queue.” | Queue name nằm trong vhost/broker; có thể khác endpoint. |
| “Consumer cancelled đồng nghĩa mất mọi message trong queue durable.” | Cancel/stop consumer không tự xóa durable queue; **queue deletion** thì khác. |
| “Quorum leader election giống listener autoStartup=false.” | Một bên là broker queue availability, một bên là local lifecycle. |
| “Ready về 0 là incident giải quyết.” | Có thể do purge/reject; phải kiểm tra DB business commit/ACK và DLQ. |
| “Restart app liên tục sẽ tự chữa mọi lỗi.” | Permission/topology/quorum sai sẽ khiến recovery loop kéo dài. |

## 17. Câu hỏi tự kiểm tra

1. `messages_ready` khác `messages_unacknowledged` thế nào?
2. Nếu queue ready=5000, unacked=0, consumers=0, bước kiểm tra nào nên ưu tiên?
3. Tại sao phải xác minh virtual host dù tên queue ở publisher và listener giống nhau?
4. `RabbitListenerEndpointRegistry.getListenerContainer(id)` trả `null` nói lên điều gì?
5. Vì sao `container.isRunning()=true` chưa bảo đảm broker đã có consumer?
6. `autoStartup=false` có thể được đặt ở những vị trí nào?
7. Khi broker xóa queue đang có consumer, điều gì xảy ra với đăng ký consumer và dữ liệu queue?
8. Khi app stop consumer mà không xóa durable queue, các message mới được route tới queue ra sao?
9. Vì sao `consumers>0` mà `ready` vẫn có thể tăng?
10. Nếu channel bị đóng do consumer ACK timeout, vì sao ready có thể tăng trở lại?
11. `basic.cancel` khác với exception nghiệp vụ bên trong `@RabbitListener` ra sao?
12. Vì sao một RabbitMQ TCP health check hoặc Spring Boot health UP chưa đủ?
13. Nếu queue quorum mất majority, tăng listener concurrency có giải quyết được không?
14. Khi backlog lớn sau recovery, vì sao không nên tăng ngay prefetch/concurrency đến mức tối đa?
15. Một integration test tốt cho “listener chưa chạy” cần khẳng định ba điều kiện nào?
16. Những số liệu nào cho biết hệ thống **thực sự** đã phục hồi đường xử lý?

**Đáp án gợi ý:** (1) Chưa giao vs đã giao chưa ACK. (2) Broker consumer registration và local lifecycle. (3) Queue khác vhost là namespace khác. (4) Endpoint không được registry quản lý/đăng ký. (5) Có thể đang recover/chưa basic.consume thành công. (6) Annotation/factory/Boot config/lifecycle control. (7) Registration bị cancel; queue bị xóa thì dữ liệu queue cũ mất. (8) Có thể nằm ready trong durable queue. (9) Handler chậm, prefetch, SAC, capacity. (10) Unacked deliveries có thể được requeue/redeliver. (11) Cancel là sự kiện consumer lifecycle, không phải mọi business exception. (12) Không chứng minh critical queue đang được consume. (13) Không, phải khôi phục quorum. (14) Dễ gây DB overload và duplicate/retry. (15) Trước start: consumers=0 + ready>0; sau start: handler nhận, ready giảm. (16) Consumer count, deliver/ACK throughput, backlog trend, DB commits, DLQ và event ID reconciliation.

## 18. Tổng kết

Khi message nằm **ready** vì listener chưa chạy hoặc bị hủy, câu hỏi đầu tiên không phải “RabbitMQ có gửi nhanh không?”, mà là **broker có consumer thực sự đăng ký trên đúng queue/vhost hay không**. `messages_ready` khác `messages_unacknowledged`, và `container.isRunning()` của Spring khác **`consumers`** broker nhìn thấy. Ba tín hiệu này giúp phân biệt listener chưa khởi tạo, bị stop/cancel, mất connection với consumer đang chạy nhưng xử lý chậm.

Với **Spring AMQP**, hãy kiểm tra `@RabbitListener`, `RabbitListenerEndpointRegistry`, `autoStartup`, component scan, container factory, connection/vhost/permissions, queue topology và broker cancellation/channel shutdown logs. Sau khi khắc phục, không chỉ start listener rồi dừng điều tra: cần nhìn consumer count, deliver/ACK rates, ready trend, DB commit, duplicate và DLQ. Tránh xóa/purge backlog để “làm đẹp” dashboard.

**Nguyên tắc vận hành:** Một listener khỏe phải **tồn tại trong ứng dụng, đăng ký được với broker và tạo ra tiến triển nghiệp vụ**. Thiếu bất kỳ mắt xích nào, message vẫn có thể nằm ready dù Spring Boot pod và RabbitMQ node đều hiển thị UP.

### Tài liệu tham khảo

- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): queues, consumers, queue lifecycle và auto-delete/exclusive behavior.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer registration, cancellation, acknowledgments và prefetch.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ready/unacked, ACK/NACK, redelivery.
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring): queue depth, consumer counts, delivery/ack rates.
- [RabbitMQ — Prometheus Monitoring](https://www.rabbitmq.com/docs/prometheus): detailed metrics và integration với Prometheus.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener`, listener endpoints và container factory.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/simple-message-listener-container.html): startup/recovery, missing queues và container behavior.
- [Spring AMQP — Events](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer-events.html): consumer failure/recovery application events.

