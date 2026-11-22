# Trạng thái listener container

Trong Spring Kafka, **listener container** quản lý vòng đời Kafka consumer, các lần `poll()`, việc phân phối record đến listener, acknowledgement, commit offset và shutdown. Khi vận hành, câu hỏi “container đang chạy hay không?” thường là điểm bắt đầu để xác định service có còn khả năng đọc Kafka hay không.

Tuy nhiên, trạng thái container chỉ là **một phần** của sức khỏe hệ thống. Container có thể báo đang chạy nhưng consumer chưa tham gia group, chưa được gán partition, đang pause, liên tục retry một record lỗi hoặc không commit offset. Ngược lại, một container đang pause có chủ đích trong lúc downstream bảo trì có thể là trạng thái hợp lệ. Vì vậy, health/readiness cần kết hợp **lifecycle state**, **consumer group assignment**, **poll/processing progress**, **lag**, **lỗi gần đây** và **ý định vận hành**.

Bài học này trình bày cách đọc và điều khiển trạng thái listener container, sử dụng `KafkaListenerEndpointRegistry`, phân biệt container state với consumer/group health, tích hợp Spring Boot Actuator và Kubernetes readiness, quản lý startup/shutdown, kiểm thử và xây dựng runbook.

## 1. Listener container là gì?

Với `@KafkaListener`, Spring Kafka tạo endpoint và listener container để quản lý một hoặc nhiều Kafka consumers. Container đảm nhiệm công việc kỹ thuật xung quanh listener method:

- Khởi tạo Kafka consumer từ `ConsumerFactory`.
- Subscribe topic hoặc assign partition theo cấu hình.
- Tham gia consumer group và xử lý rebalance.
- Gọi `poll()` để lấy record.
- Chuyển record đến listener.
- Quản lý acknowledgement và offset commit theo `AckMode`.
- Áp dụng error handler, retry, recovery và transaction nếu được cấu hình.
- Dừng consumer và giải phóng tài nguyên khi lifecycle kết thúc.

Hai dạng container thường gặp:

| Loại | Vai trò |
|---|---|
| `KafkaMessageListenerContainer` | Quản lý một consumer và vòng đời xử lý của nó. |
| `ConcurrentMessageListenerContainer` | Container cha quản lý nhiều child containers/consumer threads theo `concurrency`. |

Khi dùng `@KafkaListener`, ứng dụng thường không trực tiếp tạo và quản lý từng `KafkaConsumer`. `KafkaListenerEndpointRegistry` quản lý các listener containers được đăng ký bởi annotation infrastructure, giúp ứng dụng tra cứu container theo listener ID.

### Một listener container không phải consumer group

Consumer group là khái niệm của Kafka broker/coordinator; listener container là đối tượng quản lý phía ứng dụng Spring. Một container có thể tạo nhiều consumer members. Nhiều containers có thể dùng cùng `group.id`, và một group còn có thể chứa consumers từ các pod/application instances khác nhau.

Vì thế, trạng thái container cục bộ không thể tự khẳng định toàn group đang khỏe mạnh.

## 2. Các trạng thái cần phân biệt

Trong vận hành, không nên chỉ có hai nhãn “UP/DOWN”. Cần tách ít nhất những khái niệm sau:

| Trạng thái | Ý nghĩa | Điều cần xác minh |
|---|---|---|
| Started/running | Container đã được start theo Spring lifecycle | Consumer thread có thực sự chạy và poll không? |
| Stopped | Container không còn chạy | Stop có chủ đích hay do lỗi? |
| Starting | Đang khởi tạo consumer/container | Đã join group và có assignment chưa? |
| Paused | Container hoặc partition được yêu cầu tạm dừng nhận record | Pause có chủ đích? Downstream đã sẵn sàng resume chưa? |
| Assigned | Consumer đang được giao một hoặc nhiều partition | Assignment hiện tại có phù hợp với workload không? |
| Idle | Container/partition không nhận record trong một khoảng thời gian | Topic không có traffic hay consumer không fetch được? |
| Non-responsive | Consumer không poll đúng nhịp mong đợi | Listener bị block, GC, deadlock hay I/O chậm? |
| Processing stalled | Record được nhận nhưng offset/processing không tiến | Poison pill, retry loop, downstream hoặc commit issue? |
| Degraded | Container chạy nhưng một phần chức năng/partition không đạt SLA | Có thể tiếp tục nhận traffic hay cần refuse readiness? |

`isRunning()` chỉ trả lời một câu hỏi về lifecycle của Spring container. Nó không thay thế các trạng thái còn lại.

## 3. Quan sát container bằng KafkaListenerEndpointRegistry

Spring Kafka cung cấp `KafkaListenerEndpointRegistry` để truy cập các listener containers được đăng ký qua `@KafkaListener`.

Ví dụ listener có ID ổn định:

~~~java
@Component
public class OrdersListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service")
    public void onMessage(OrderEvent event) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Tra cứu container từ registry:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

Các import chính gồm `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, `KafkaListener` và Spring component annotations. `OrderEvent` là kiểu dữ liệu do ứng dụng định nghĩa.

### Listener ID phải ổn định

Dùng ID tường minh giúp health indicator, management endpoint, log và runbook tham chiếu cùng một container. Tránh xây dựng health logic dựa vào việc lấy container đầu tiên từ registry, vì ứng dụng có thể có nhiều listeners.

`registry.getListenerContainer(id)` có thể trả về `null` nếu ID không tồn tại hoặc container chưa được đăng ký. Cần phân biệt “listener không được cấu hình” với “listener đã cấu hình nhưng đang stopped”; hai trường hợp này có ý nghĩa vận hành khác nhau.

### Liệt kê containers

Có thể lấy danh sách IDs và containers từ registry để hiển thị trạng thái:

~~~java
for (String id : registry.getListenerContainerIds()) {
    MessageListenerContainer container =
            registry.getListenerContainer(id);

    if (container != null) {
        log.info(
                "Kafka listener id={} running={}",
                id,
                container.isRunning());
    }
}
~~~

Đoạn code là quan sát cục bộ. Không log liên tục ở mỗi lần health check với tần suất cao; dùng metrics hoặc endpoint quản trị có rate phù hợp.

## 4. Running không có nghĩa đã sẵn sàng xử lý record

Container có thể đã được start nhưng vẫn đang:

- Tạo consumer và kết nối broker.
- Đang tham gia consumer group.
- Chờ coordinator hoàn tất rebalance.
- Chưa được gán partition vì group còn member khác hoặc số partition không đủ.
- Đang pause theo yêu cầu backpressure.
- Đang retry auth/authorization.
- Không nhận record vì topic không có traffic.
- Bị lỗi processing nhưng error handler vẫn giữ container hoạt động.

Một sơ đồ quyết định đơn giản:

~~~mermaid
flowchart TD
    A[Container isRunning?] -->|Không| B[Stopped / startup chưa hoàn tất]
    A -->|Có| C[Consumer có poll đúng nhịp?]
    C -->|Không| D[Non-responsive / thread bị block]
    C -->|Có| E[Partition assignment hợp lệ?]
    E -->|Không| F[Join group / rebalance / group config]
    E -->|Có| G[Đang pause có chủ đích?]
    G -->|Có| H[Paused theo policy]
    G -->|Không| I[Processing và offset có tiến?]
    I -->|Có| J[Healthy theo policy]
    I -->|Không| K[Retry / lag / commit / downstream]
~~~

Không phải mọi listener đều bắt buộc phải có partition assignment ngay lúc startup. Nếu concurrency lớn hơn partition count, một số child consumers có thể không được gán partition. Với một topic không có traffic, container vẫn có thể poll bình thường nhưng không xử lý record. Health policy cần hiểu thiết kế của group.

## 5. Concurrent container và trạng thái child consumers

Với `concurrency=3`, `ConcurrentMessageListenerContainer` có thể quản lý ba consumer threads. Parent container báo running không có nghĩa mọi child consumer đều đang có partition hoặc có throughput.

~~~text
ordersListener (parent)
  child-0: running, assigned P0/P1
  child-1: running, assigned P2
  child-2: running, no assignment (có thể bình thường)
~~~

Nếu topic chỉ có ba partitions và group có nhiều hơn ba consumers, một số consumers có thể không có assignment. Điều đó không tự động là lỗi. Nếu một child bất ngờ dừng trong khi các child khác còn chạy, parent state có thể không đủ để phản ánh degraded capacity.

Để đánh giá đúng:

- Biết listener ID và configured concurrency.
- Biết số partition và group membership dự kiến.
- Theo dõi rebalance/assignment events.
- Quan sát consumer poll và lag theo partition.
- Phân biệt child không có assignment hợp lệ với child không thể join group.
- Không tự tính “expected active children = concurrency” trong mọi topology.

Nếu cần trạng thái từng child, dùng các lifecycle/metrics APIs phù hợp phiên bản Spring Kafka. Tránh truy cập trực tiếp nội bộ của container hoặc thread để suy luận state nếu API public đã cung cấp tín hiệu cần thiết.

## 6. Pause và resume không giống stop và start

Spring Kafka hỗ trợ pause/resume listener container và, ở những phiên bản phù hợp, pause/resume theo partition. Pause thường dùng để backpressure hoặc bảo trì tạm thời.

| Hành động | Ý nghĩa |
|---|---|
| `start()` | Bắt đầu lifecycle container. |
| `stop()` | Dừng container và consumer theo lifecycle. |
| `pause()` | Tạm dừng nhận records theo cơ chế container; consumer vẫn có thể cần poll để duy trì membership. |
| `resume()` | Tiếp tục nhận records sau pause. |
| Pause một partition | Giảm/đình chỉ fetch từ partition được chọn, tùy API/version. |

Pause có thể là trạng thái **được kỳ vọng**. Nếu downstream database quá tải và ứng dụng chủ động pause, readiness có thể vẫn ACCEPTING_TRAFFIC nếu service còn khả năng xử lý request khác; hoặc có thể REFUSING_TRAFFIC nếu Kafka processing là chức năng bắt buộc của instance. Đây là quyết định theo SLA, không phải quy tắc chung.

### Kiểm tra pause state

Các phiên bản Spring Kafka cung cấp các API trạng thái pause trên listener container, ví dụ `isPauseRequested()` và `isContainerPaused()`. Cần kiểm tra API của version đang dùng; trạng thái pause request và trạng thái đã thực sự paused có thể khác nhau.

Không dùng pause state thay cho group membership. Một consumer có thể được assign partition nhưng đang paused; một consumer không có assignment có thể vẫn poll và ở trạng thái running.

### Không resume mù quáng

Trước khi resume:
1. Xác định ai yêu cầu pause và lý do.
2. Kiểm tra downstream đã phục hồi.
3. Xác nhận container đang chạy và lifecycle không stopping.
4. Dùng API container phù hợp thay vì gọi KafkaConsumer từ background thread.
5. Theo dõi lag/processing sau resume.

Resume quá sớm có thể đưa traffic trở lại một dependency vẫn đang quá tải.

## 7. Trạng thái container và consumer group assignment

Kafka group coordinator quyết định member nào sở hữu partition. Container local không tự biết toàn bộ group topology chỉ từ `isRunning()`.

Ví dụ:

~~~text
Group: orders-service

Pod A:
  ordersListener running
  P0, P1 assigned

Pod B:
  ordersListener running
  P2, P3 assigned

Pod C:
  ordersListener running
  no assignment (concurrency > partitions)
~~~

Ba container đều running. Pod C không xử lý record vì không có partition; điều đó có thể hoàn toàn đúng. Nếu Pod A bị mất assignment sau rebalance, nó vẫn có thể running trong khi partition chuyển sang Pod B.

Khi cần health theo group, kết hợp:
- Consumer group member count.
- Partition assignment.
- Rebalance count/duration.
- Committed offsets và lag.
- Container lifecycle.
- Poll/processing progress.

Có thể dùng Kafka AdminClient hoặc hệ thống metrics chuyên biệt để quan sát group từ một health/monitoring component độc lập. Không tạo một KafkaConsumer mới rồi subscribe vào cùng group chỉ để “kiểm tra health”, vì nó có thể tham gia group và gây rebalance.

## 8. Startup readiness: không đánh dấu ready quá sớm

Khi Spring Boot khởi động, application context có thể đã refresh và web server đã lắng nghe trong khi Kafka listener containers vẫn đang khởi tạo. Nếu readiness chuyển sang ACCEPTING_TRAFFIC quá sớm, load balancer có thể gửi traffic vào một instance mà Kafka processing chưa sẵn sàng.

Một startup policy cần quyết định:
- Listener nào là bắt buộc để instance phục vụ đúng chức năng?
- Có cần đợi container running hay cần đợi group assignment?
- Có cho phép instance ready khi topic không có traffic không?
- Nếu concurrency lớn hơn số partitions, có chấp nhận child không assignment?
- Kafka outage tạm thời có khiến pod chưa ready hay vẫn cho phép API phục vụ?
- Startup timeout bao lâu trước khi chuyển degraded/failed?

**Không đợi một business record đầu tiên để đánh dấu ready** nếu topic có thể không có traffic. Readiness nên dựa trên bằng chứng consumer đã khởi tạo/join group/đạt điều kiện kỹ thuật theo topology, không phải sự kiện ngẫu nhiên có message.

## 9. Spring Boot Availability và readiness state

Spring Boot có application availability states, thường dùng `ReadinessState.ACCEPTING_TRAFFIC` và `ReadinessState.REFUSING_TRAFFIC`. Có thể dùng `AvailabilityChangeEvent` để chuyển trạng thái ứng dụng khi Kafka listener bắt buộc không hoạt động.

Ví dụ minh họa một thành phần quản lý readiness:

~~~java
@Component
public class KafkaReadinessCoordinator {

    private final ApplicationContext applicationContext;
    private final KafkaListenerEndpointRegistry registry;

    public KafkaReadinessCoordinator(
            ApplicationContext applicationContext,
            KafkaListenerEndpointRegistry registry) {
        this.applicationContext = applicationContext;
        this.registry = registry;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC);
    }

    public boolean isRequiredListenerRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

Ví dụ dùng các API Spring Boot Availability và Spring Kafka registry. Các import chính gồm `ApplicationContext`, `AvailabilityChangeEvent`, `ReadinessState`, `KafkaListenerEndpointRegistry` và `MessageListenerContainer`.

Đoạn code chỉ minh họa điều khiển readiness; nó chưa tự đăng ký listener event, chưa kiểm tra group assignment và chưa quyết định khi nào được gọi `acceptTraffic()`. Trong production, cần một state coordinator chống race giữa startup, stop, retry và shutdown.

### Readiness là trạng thái của application instance

Một container có thể dừng trong khi application vẫn phục vụ endpoint khác. Nếu Kafka là chức năng cốt lõi của service, readiness có thể chuyển REFUSING_TRAFFIC. Nếu Kafka listener chỉ là một background feature không ảnh hưởng khả năng phục vụ API, có thể không nên làm cả pod unready.

Đặt policy theo **vai trò của listener** và SLA, không chuyển readiness cho mọi listener event mà không phân biệt.

## 10. Liveness không phải readiness

Spring Boot/Kubernetes thường tách:

- **Liveness:** process có còn sống và có thể tự tiếp tục không; thất bại có thể khiến orchestrator restart pod.
- **Readiness:** instance hiện có nên nhận traffic mới không; thất bại loại pod khỏi service endpoints nhưng không nhất thiết restart.
- **Startup probe:** cho ứng dụng thời gian khởi động trước khi liveness/readiness có hiệu lực theo cấu hình.

Không dùng Kafka outage ngắn làm liveness failure nếu container có thể tự retry và process vẫn khỏe. Nếu liveness probe restart pod mỗi khi broker mất kết nối, hệ thống có thể tạo restart storm, làm tăng rebalance và khiến phục hồi chậm hơn.

Readiness có thể REFUSING_TRAFFIC khi listener quan trọng không hoạt động, nhưng cần xem liệu pod vẫn có thể tiếp tục xử lý hoặc tự phục hồi mà không nhận HTTP traffic hay không.

### Cấu hình health groups minh họa

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaListener
        liveness:
          include: livenessState
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Property names/health group behavior phụ thuộc Spring Boot version và cấu hình Actuator. `kafkaListener` trong ví dụ là tên health contributor custom do ứng dụng đăng ký, không phải contributor mặc định được tạo tự động chỉ vì có Spring Kafka.

Không đưa Kafka broker connectivity vào liveness một cách mặc định. Nếu readiness group có custom contributor, phải xác định timeout, cache và cách phản ánh retry/paused/expected assignment.

## 11. Tạo HealthIndicator cho listener container

Có thể tạo custom `HealthIndicator` để phản ánh trạng thái listener bắt buộc:

~~~java
@Component("kafkaListener")
public class KafkaListenerHealthIndicator implements HealthIndicator {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerHealthIndicator(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Health health() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            return Health.down()
                    .withDetail("listener", "ordersListener")
                    .withDetail("reason", "not_registered")
                    .build();
        }

        if (!container.isRunning()) {
            return Health.outOfService()
                    .withDetail("listener", "ordersListener")
                    .withDetail("reason", "container_stopped")
                    .build();
        }

        return Health.up()
                .withDetail("listener", "ordersListener")
                .withDetail("running", true)
                .build();
    }
}
~~~

Ví dụ sử dụng Spring Boot Actuator `HealthIndicator`, `Health`. Trạng thái `DOWN`, `OUT_OF_SERVICE` và `UP` phải được ánh xạ vào readiness/liveness theo health group của ứng dụng. Không phải mọi deployment đều muốn một listener stopped làm toàn bộ actuator health trả DOWN.

### Giới hạn của health indicator đơn giản

Indicator trên chỉ kiểm tra:
- Listener ID có được đăng ký không.
- Container có báo running không.

Nó không xác minh:
- Consumer đã join group.
- Có partition assignment hợp lệ.
- Poll đang tiến.
- Consumer không pause.
- Listener xử lý thành công.
- Offset commit có tiến.
- Lag đang trong SLA.

Đừng đặt tên kết quả này là “Kafka processing healthy” nếu nó chỉ kiểm tra `isRunning()`. Có thể đặt tên chính xác hơn là “listener container lifecycle running”.

## 12. Health policy nhiều điều kiện

Một policy cho listener quan trọng có thể kết hợp các tín hiệu:

~~~text
READY khi:
  container được đăng ký
  AND container đang running
  AND không có stop ngoài ý muốn
  AND consumer poll không vượt ngưỡng non-responsive
  AND trạng thái pause phù hợp policy
  AND assignment đạt điều kiện thiết kế (nếu cần)
  AND lag không vượt SLA (nếu policy yêu cầu)
~~~

Không phải mọi điều kiện đều cần có ở mọi service. Ví dụ:
- Một listener không có traffic vẫn có thể ready.
- Một consumer không có partition do concurrency lớn hơn partition count có thể bình thường.
- Một listener chủ động pause để maintenance có thể không ready theo chính sách.
- Lag tăng trong burst traffic không nhất thiết yêu cầu pod unready nếu service vẫn phục hồi trong SLA.

### Không gọi Kafka broker từ mỗi health probe

Health endpoint có thể được gọi nhiều lần mỗi giây bởi orchestrator. Nếu mỗi lần probe thực hiện nhiều AdminClient requests, việc health check có thể làm tăng tải broker và tạo thêm failure khi broker đang quá tải.

Nên:
- Dùng trạng thái lifecycle/metrics đã có.
- Thu thập group/lag bằng monitor độc lập theo chu kỳ hợp lý.
- Cache kết quả bên ngoài request health.
- Đặt timeout hữu hạn và không block consumer thread.
- Trả health với timestamp/freshness để phân biệt stale observation.

Health indicator nên đọc state đã được tổng hợp, không phải khởi chạy một workflow kiểm tra nặng mỗi lần HTTP GET.

## 13. Listener container lifecycle và SmartLifecycle

Spring Kafka listener containers tham gia Spring lifecycle. Các thuộc tính liên quan có thể gồm:
- `autoStartup`: container có tự khởi động cùng application context không.
- `phase`: thứ tự start/stop tương đối trong lifecycle.
- `shutdownTimeout`: thời gian chờ shutdown theo container properties ở những phiên bản hỗ trợ.
- `missingTopicsFatal`: chính sách khi topic cấu hình chưa tồn tại trong một số cấu hình/version.
- `stop()` callback: cho phép phối hợp hoàn tất shutdown bất đồng bộ theo API lifecycle.

Những thuộc tính cụ thể và vị trí cấu hình cần đối chiếu version Spring Kafka/Boot.

### autoStartup=false

Một listener có thể được cấu hình không tự start:

~~~java
@KafkaListener(
        id = "manualOrdersListener",
        topics = "orders.events",
        autoStartup = "false")
public void handle(OrderEvent event) {
    // Xử lý.
}
~~~

Khi đó container được đăng ký nhưng không tự khởi động cùng context. Health indicator chỉ kiểm tra “đã đăng ký” sẽ có thể báo sai. Nếu listener manual-start là thiết kế có chủ đích, health policy phải biết khi nào nó cần chạy và ai chịu trách nhiệm start.

### Khởi động theo điều kiện

Có thể dùng registry để start listener khi một điều kiện ứng dụng đã sẵn sàng:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("manualOrdersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

Chỉ gọi thao tác này từ lifecycle coordinator phù hợp. Không start lại trong mọi health request hoặc event callback. Nếu nhiều component cùng điều khiển một container, cần một state machine duy nhất để tránh race.

## 14. Shutdown có kiểm soát

Khi application nhận yêu cầu dừng, container cần kết thúc theo lifecycle để consumer đóng đúng cách. Một quy trình điển hình:

1. Đánh dấu instance đang shutdown.
2. Chuyển readiness sang REFUSING_TRAFFIC nếu service không còn nhận workload.
3. Yêu cầu listener containers stop theo lifecycle.
4. Cho record đang xử lý hoàn tất trong thời gian cho phép hoặc rollback theo policy.
5. Commit/abort Kafka transaction đúng cấu hình.
6. Dừng worker phụ trợ và chờ in-flight work theo giới hạn.
7. Xác nhận container stopped.
8. Đóng application context.

Không lấy `isRunning()` ngay sau khi gọi `stop()` làm bằng chứng mọi consumer thread đã cleanup xong nếu stop API thực hiện bất đồng bộ/có callback. Dùng stop callback/lifecycle signals hoặc trạng thái cuối phù hợp với phiên bản.

### Shutdown timeout

Nếu timeout quá ngắn, record đang xử lý có thể bị ngắt và giao lại sau restart. Nếu timeout quá dài, pod có thể vượt thời gian termination grace period của orchestrator. Hãy đo listener p99, retry/backoff và downstream shutdown behavior để chọn giới hạn hợp lý.

Không giữ container dừng vô hạn để chờ một external call không timeout. Mọi I/O trong listener cần timeout hữu hạn và có recovery policy.

## 15. Tương tác với consumer rebalance

Khi container dừng, consumer rời group hoặc mất heartbeat; coordinator có thể rebalance partition cho các member còn lại. Khi container chỉ pause, nó có thể vẫn duy trì membership/poll theo cơ chế của client. Khi container running nhưng không responsive, group có thể coi member mất tiến triển và chuyển partition.

Các event/callback liên quan:
- `ConsumerStartedEvent` / `ConsumerStoppedEvent`: lifecycle consumer.
- `ContainerStoppedEvent`: lifecycle container.
- `onPartitionsAssigned`: partition mới được giao.
- `onPartitionsRevoked`: partition chuẩn bị bị thu hồi.
- `onPartitionsLost`: consumer đã mất ownership.
- `NonResponsiveConsumerEvent`: poll không phản hồi như kỳ vọng.

Đừng suy ra assignment chỉ từ start/stop event. Khi readiness phụ thuộc partition ownership, cần nguồn trạng thái group/assignment thích hợp.

### Rebalance không luôn là container restart

Một consumer có thể bị revoke và assigned partition mới trong khi container vẫn running. Nếu mỗi rebalance làm readiness chuyển DOWN rồi UP, hệ thống có thể tạo readiness flapping. Cần dùng grace window hoặc đánh giá assignment state sau khi rebalance hoàn tất.

## 16. Non-responsive và container đang running

Một container có thể `isRunning()=true` nhưng consumer thread bị block lâu trong listener hoặc downstream call. Trong trường hợp đó, liveness/readiness dựa trên isRunning có thể báo UP trong khi message processing đã ngừng.

Spring Kafka cung cấp cơ chế quan sát non-responsive consumer, thường liên quan `monitorInterval` và `noPollThreshold` trong container properties. Event `NonResponsiveConsumerEvent` có thể giúp phát hiện consumer không poll đúng nhịp.

~~~java
factory.getContainerProperties().setMonitorInterval(10);
factory.getContainerProperties().setNoPollThreshold(3.0);
~~~

Đoạn minh họa cần xác nhận các setter và đơn vị của version Spring Kafka. `monitorInterval` thường là chu kỳ monitor theo giây; `noPollThreshold` là hệ số so sánh với khoảng poll dự kiến trong cơ chế framework. Không sao chép giá trị mà không kiểm tra API/version.

### Điều tra non-responsive

- Listener gọi HTTP/DB không timeout.
- `Thread.sleep` hoặc blocking retry trên consumer thread.
- Deadlock/lock contention.
- Stop-the-world GC hoặc CPU starvation.
- Batch quá lớn hoặc xử lý một record quá lâu.
- Transaction kéo dài, producer send chờ quá lâu.
- Error handler backoff giữ poll thread.
- Network/broker operation bị treo.

Khi consumer non-responsive, tăng readiness grace period có thể tránh false positive trong thời gian ngắn, nhưng không sửa nguyên nhân listener bị block.

## 17. Health và lag: cần đọc cùng nhau

Một container running có thể không theo kịp producer. Lag là khoảng cách giữa vị trí log và tiến độ consumer group, theo loại offset được sử dụng trong phép đo.

Ví dụ:

~~~text
orders.events partition 0:
  end offset       = 50,000
  committed offset = 49,900
  lag              = 100

partition 1:
  end offset       = 80,000
  committed offset = 20,000
  lag              = 60,000
~~~

Container có thể running và vẫn xử lý P0 bình thường trong khi P1 bị kẹt. Một health indicator chỉ kiểm tra parent container không thấy vấn đề này.

Khi đánh giá lag:
- Theo dõi từng partition, không chỉ tổng.
- Xem xu hướng lag tăng/giảm, không chỉ một snapshot.
- Phân biệt producer traffic burst với processing stall.
- Kiểm tra retry/DLT và committed offsets.
- Không tự động chuyển pod unready khi lag tạm tăng nếu instance vẫn có khả năng bắt kịp theo SLA.

Nếu service yêu cầu mỗi partition phải được xử lý trong một deadline, dùng lag/record age threshold cụ thể theo workload.

## 18. Health khi topic không có traffic

Một topic có thể không có record trong thời gian dài nhưng consumer vẫn hoạt động tốt. `ListenerContainerIdleEvent` và `ListenerContainerPartitionIdleEvent` có thể phát để quan sát idle; đó không tự động là lỗi container.

Không dùng điều kiện “không có record trong 60 giây” làm liveness failure nếu topic không bảo đảm traffic liên tục. Readiness cần dựa vào:
- Container lifecycle và consumer poll health.
- Group membership/assignment theo yêu cầu.
- Pause state và expected maintenance.
- Lỗi auth/ACL và nonresponsive signals.
- Lag hoặc business freshness khi có dữ liệu đầu vào.

Nếu topic có contract heartbeat hoặc SLA freshness, có thể cảnh báo khi thiếu dữ liệu theo business rule; đó là **source/data freshness health**, không nhất thiết là listener container health.

## 19. Tạo readiness policy với state machine

Để tránh health flapping, dùng state machine hoặc coordinator quản lý trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> READY: Container started và startup checks đạt
    STARTING --> DEGRADED: Quá startup deadline
    READY --> DEGRADED: Listener lỗi/non-responsive/lag vượt SLA
    DEGRADED --> READY: Poll/processing ổn định qua recovery window
    READY --> REFUSING: Intentional shutdown hoặc listener bắt buộc stopped
    DEGRADED --> REFUSING: Không thể nhận workload an toàn
    REFUSING --> STOPPED: Container lifecycle kết thúc
    STOPPED --> STARTING: Có lệnh start mới
~~~

Đây là mô hình vận hành đề xuất, không phải enum trạng thái built-in của Spring Kafka.

Một policy tốt cần:
- **Startup grace period:** tránh báo unhealthy khi listener đang join group.
- **Failure threshold:** không chuyển degraded chỉ vì một lỗi transient.
- **Recovery window:** yêu cầu ổn định một khoảng trước khi accept traffic lại.
- **Intent flag:** phân biệt stop có chủ đích với stop ngoài ý muốn.
- **Expected assignment:** biết partition count/concurrency/topology.
- **Pause policy:** pause có thể là degraded hoặc expected maintenance.
- **Stale data detection:** không dùng metrics cũ để kết luận healthy.
- **Single owner:** chỉ một coordinator cập nhật readiness.

## 20. Kiểm thử trạng thái container

Nên kiểm thử riêng lifecycle state, group/assignment behavior và readiness mapping. Ví dụ các scenario:

| Scenario | Container expectation | Readiness expectation |
|---|---|---|
| Application vừa khởi động | Có thể chưa running/join group | STARTING/REFUSING trong grace period |
| Listener started, group ổn định | Running | READY nếu listener là bắt buộc |
| Topic không có record | Running, poll bình thường | READY |
| Consumer pause có chủ đích | Running nhưng paused | Theo pause policy |
| Listener stopped ngoài ý muốn | Stopped | DEGRADED hoặc REFUSING |
| Consumer non-responsive | Có thể vẫn báo running | DEGRADED/REFUSING sau threshold |
| Rebalance ngắn | Container vẫn running | Giữ READY hoặc grace window |
| Rolling shutdown | Stop có chủ đích | REFUSING |
| Listener manual-start chưa được start | Registered nhưng stopped | Theo startup policy, thường chưa READY nếu bắt buộc |

### Kiểm thử registry và HealthIndicator

Có thể dùng unit test với registry/container mock để xác nhận:
- Listener ID không tồn tại trả trạng thái phù hợp.
- Container stopped không bị đánh dấu UP.
- Container running được đánh giá theo policy.
- Pause intentional không bị phân loại nhầm.
- Một listener optional không làm toàn application unready.

Với integration test, dùng Kafka broker test/Embedded Kafka tương thích:
1. Khởi động Spring context.
2. Đợi container bắt đầu.
3. Xác minh registry trả đúng listener ID.
4. Đợi group assignment theo topology test.
5. Publish record và xác nhận listener xử lý.
6. Stop container và xác minh readiness đổi theo policy.
7. Start lại và xác minh readiness chỉ phục hồi sau điều kiện cần thiết.
8. Test concurrency và rebalance để tránh giả định mọi child luôn có assignment.

Không cần gửi record để kiểm tra readiness nếu topic có thể không có traffic; assignment/poll health thường là tín hiệu phù hợp hơn.

## 21. Actuator endpoint và bảo vệ thông tin

Actuator health có thể hiển thị trạng thái tổng hợp. Trong production:
- Chỉ expose endpoints cần thiết.
- Kiểm soát quyền truy cập và network.
- Không để health details tiết lộ broker hostnames, group topology hoặc lỗi bảo mật chi tiết cho public endpoint.
- Dùng health groups riêng cho liveness/readiness.
- Tránh thực hiện network checks đồng bộ quá nặng trong mỗi probe.
- Đặt timeout cho custom health checks.
- Tránh để exception từ health contributor làm actuator endpoint treo.

Nếu health details cần thiết cho đội vận hành, có thể giới hạn chi tiết cho authorized/internal view, còn Kubernetes probe chỉ cần HTTP status và state ngắn gọn.

## 22. Monitoring và metrics cho listener state

Một bộ metric vận hành có thể bao gồm:

| Metric logic | Ý nghĩa |
|---|---|
| `listener_container_running` | Trạng thái lifecycle hiện tại của listener. |
| `listener_container_paused` | Container đang paused hay không. |
| `listener_start_total` / `listener_stop_total` | Số lần start/stop event được ghi nhận. |
| `listener_nonresponsive_total` | Số sự kiện consumer không poll phản hồi. |
| `listener_assignment_partitions` | Số partition đang được assign theo listener/member. |
| `consumer_lag` | Backlog theo group/topic/partition. |
| `listener_processing_rate` | Tốc độ listener xử lý record. |
| `listener_processing_duration` | Latency listener. |
| `listener_rebalance_total` | Số lần rebalance được quan sát. |
| `listener_last_success_timestamp` | Thời điểm gần nhất có xử lý thành công, nếu có traffic. |

Các tên trên là metric logic; tên export cụ thể tùy Micrometer, Spring Kafka và registry. Tránh gắn event ID, offset, customer ID làm metric labels. Dùng topic/group/listener/environment và partition khi cardinality phù hợp.

### Last successful processing không thay thế poll health

Nếu topic không có traffic, timestamp lần xử lý thành công có thể cũ nhưng consumer vẫn poll bình thường. Do đó cần phân biệt:
- Last successful poll (nếu có nguồn đo).
- Last record received.
- Last listener success.
- Last committed offset advancement.
- Last business event applied.

Mỗi mốc trả lời câu hỏi khác nhau.

## 23. Runbook: Container stopped ngoài ý muốn

1. Xác định listener ID, application instance, group ID và thời điểm stop.
2. Kiểm tra `ConsumerStoppedEvent` reason và exception gốc.
3. Xác nhận stop có phải deployment/manual stop không.
4. Kiểm tra Kafka broker connectivity, authentication/authorization và consumer group.
5. Đối chiếu transaction/producer fencing nếu listener dùng Kafka transaction.
6. Xác định partition được giao lại cho member nào.
7. Kiểm tra committed offsets và record có thể được redeliver.
8. Sửa nguyên nhân trước khi restart; dùng backoff nếu lỗi có thể phục hồi.
9. Xác nhận container started, consumer poll, assignment và lag phục hồi.

Không reset offset chỉ vì container dừng.

## 24. Runbook: isRunning=true nhưng listener không xử lý record

1. Kiểm tra consumer có non-responsive event hoặc poll interval bất thường không.
2. Kiểm tra group assignment; container có thể running nhưng chưa được giao partition.
3. Kiểm tra pause state ở cấp container/partition.
4. So sánh broker end offset và committed offset.
5. Kiểm tra listener đang retry poison pill hoặc bị downstream block.
6. Xem deserialize errors, error handler và DLT recovery.
7. Kiểm tra transaction abort/fencing và commit failures.
8. Đo listener duration, GC, CPU và thread state.
9. Chỉ đánh dấu healthy khi processing/poll progress đáp ứng policy.

## 25. Runbook: Readiness flapping khi rebalance

1. Dựng timeline container lifecycle, rebalance callbacks và readiness changes.
2. Xác định readiness có bị phụ thuộc trực tiếp vào một assignment callback nhất thời không.
3. Kiểm tra group protocol và cooperative/eager rebalance.
4. Thêm startup/rebalance grace window phù hợp SLA.
5. Phân biệt container running với partition ownership tạm thời.
6. Không chuyển REFUSING_TRAFFIC chỉ vì một lần partition revoke.
7. Kiểm tra lag/processing có thực sự mất tiến độ hay không.
8. Xác nhận readiness ổn định trong rolling deploy/scale test.

## 26. Runbook: Container paused nhưng health báo UP

1. Xác định pause có chủ đích hay do backpressure/stuck recovery.
2. Kiểm tra pause scope: toàn container hay partition cụ thể.
3. Đọc owner/reason và thời gian đã pause.
4. Kiểm tra downstream đã phục hồi và có thể nhận traffic chưa.
5. Xác định policy: pause intentional có được READY hay phải REFUSING.
6. Resume bằng container API khi đủ điều kiện.
7. Theo dõi lag và listener processing sau resume.
8. Cập nhật health indicator để phản ánh pause theo policy, không chỉ `isRunning()`.

## 27. Runbook: Container running nhưng group không có assignment

1. Xác nhận listener đã subscribe đúng topic/group.
2. Kiểm tra topic tồn tại và partition count.
3. Kiểm tra group members, static member ID và rebalance state.
4. Xác định concurrency có lớn hơn số partition không; child không assignment có thể bình thường.
5. Kiểm tra ACL join group/read topic và broker logs.
6. Kiểm tra partition đã bị assign cho member khác chưa.
7. Không tạo consumer probe tham gia cùng group để kiểm tra.
8. Nếu listener bắt buộc phải có assignment, đặt health condition theo topology; nếu không, chỉ kiểm tra poll/lifecycle.

## 28. Runbook: Shutdown quá lâu hoặc record bị redeliver

1. Kiểm tra thời gian termination grace period của orchestrator.
2. Đối chiếu listener processing p99, retry backoff và downstream timeouts.
3. Kiểm tra container shutdown timeout/phase và stop callback.
4. Xác định in-flight records khi container nhận stop.
5. Kiểm tra Kafka transaction commit/abort và committed offsets.
6. Nếu record được redeliver, xác nhận business idempotency.
7. Đặt timeout hữu hạn cho external I/O và worker pools.
8. Thử rolling shutdown trong staging với record đang xử lý.
9. Xác minh pod kết thúc trong giới hạn mà không làm mất business outcome.

## 29. Runbook: Health endpoint chậm hoặc làm tăng tải Kafka

1. Kiểm tra health indicator có gọi AdminClient hoặc broker network request mỗi lần probe không.
2. Đo endpoint latency và số lần probe.
3. Tách metrics/group sampling khỏi HTTP request path.
4. Cache kết quả group/lag với timestamp và timeout hữu hạn.
5. Dùng container lifecycle state cho check nhẹ.
6. Đặt stale-data policy để không báo UP từ cache quá cũ.
7. Giới hạn details và log volume.
8. Kiểm tra readiness/liveness không cùng kích hoạt restart loop khi broker outage.

## 30. Bảng kiểm soát trạng thái listener container

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Registry | Listener ID có được đăng ký đúng không? | `KafkaListenerEndpointRegistry` và endpoint IDs. |
| Lifecycle | Container có running/stopped đúng kỳ vọng? | `isRunning()`, start/stop events. |
| Concurrency | Parent/child consumers có được hiểu đúng? | Config concurrency, child metrics. |
| Assignment | Consumer có partition ownership phù hợp? | Rebalance events/group assignment. |
| Pause | Container/partition có pause theo policy? | Pause state, owner và reason. |
| Poll health | Consumer có tiếp tục poll đúng nhịp? | Nonresponsive events, poll metrics. |
| Processing | Listener success/failed attempts và latency ra sao? | Micrometer metrics/logs. |
| Offset | Committed offset và lag có tiến theo SLA? | Group offsets, lag per partition. |
| Readiness | Listener nào thực sự bắt buộc để instance nhận traffic? | Readiness policy và health group. |
| Liveness | Kafka outage có gây restart storm không? | Probe config và incident history. |
| Startup | Có grace period chờ listener/group setup? | Startup/readiness state transitions. |
| Shutdown | In-flight work/transaction được xử lý thế nào? | Stop callback, timeout, commit/abort. |
| Recovery | Restart có backoff, ownership rõ ràng? | Lifecycle coordinator và retry budget. |
| Observability | Health/metrics có phân biệt idle, paused, nonresponsive và stopped? | Dashboard, alerts và runbooks. |

**Kết luận:** Trạng thái listener container là nền tảng cho health và readiness của Spring Kafka, nhưng **running không đồng nghĩa processing healthy**. Hãy dùng `KafkaListenerEndpointRegistry` để xác định đúng container, phân biệt parent/child concurrency, pause, assignment, poll health, processing progress và committed offsets. Readiness nên phản ánh vai trò của listener đối với service và có grace/recovery windows; liveness không nên restart pod chỉ vì Kafka tạm thời mất kết nối. Khi health indicator chỉ đọc trạng thái lifecycle nhẹ, kết hợp group/lag metrics được thu thập độc lập và có runbook cho stop/rebalance/shutdown, hệ thống sẽ tránh được false positive, readiness flapping và restart storm.
