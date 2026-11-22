# Tách readiness và liveness

Một ứng dụng Spring Boot có thể vẫn chạy trong JVM nhưng không còn phục vụ được yêu cầu mới. Ngược lại, ứng dụng có thể tạm thời không kết nối được Kafka hoặc database trong khi process vẫn hoạt động bình thường và có khả năng tự phục hồi. Nếu chỉ có một health check chung rồi dùng kết quả đó cho mọi quyết định, hệ thống dễ phản ứng sai: restart liên tục khi dependency bên ngoài gặp sự cố, hoặc tiếp tục gửi traffic tới một instance thực sự không thể phục vụ.

**Readiness** và **liveness** trả lời hai câu hỏi khác nhau:

- **Readiness:** instance có sẵn sàng nhận traffic hoặc công việc mới theo hợp đồng của service không?
- **Liveness:** process còn sống và có khả năng tiếp tục hoạt động, hay cần được khởi động lại để phục hồi?

Trong Spring Boot, hai trạng thái này được biểu diễn qua `ApplicationAvailability`, `ReadinessState` và `LivenessState`, đồng thời có thể được expose bằng Actuator health groups cho Kubernetes. Với Spring Kafka, cần hiểu thêm một điểm quan trọng: **Kubernetes readiness probe không tự động điều khiển Kafka consumer group**. Nếu một worker cần tạm ngừng consume khi dependency không sẵn sàng, ứng dụng phải có cơ chế pause/stop listener container được thiết kế riêng.

## 1. Vì sao phải tách hai trạng thái?

Giả sử service xử lý đơn hàng bằng Spring Kafka:

~~~text
Kubernetes
   |
   +---- liveness probe
   |         |
   |         v
   |    JVM / process có còn hoạt động?
   |
   +---- readiness probe
             |
             v
       Service có thể nhận công việc mới?
             |
             v
       Spring Kafka listener
             |
       +-----+------+
       |            |
       v            v
   PostgreSQL     Kafka
~~~

Có hai tình huống:

**Tình huống A — process bị deadlock.** JVM vẫn tồn tại nhưng các thread quan trọng không còn tiến triển. Instance không thể phục hồi bằng cách chờ dependency; cần restart. Đây là vấn đề của **liveness**.

**Tình huống B — Kafka broker tạm thời unavailable.** JVM vẫn xử lý HTTP endpoint khác, quản lý tài nguyên và có thể kết nối lại khi broker phục hồi. Nếu liveness phụ thuộc trực tiếp vào Kafka, Kubernetes có thể restart toàn bộ Pods dù nguyên nhân nằm ngoài ứng dụng. Đây thường là vấn đề **dependency health/readiness**, không tự động là liveness failure.

| Trạng thái | Câu hỏi | Hành động điều phối thường gặp |
|---|---|---|
| Readiness `UP` | Instance có thể nhận công việc mới? | Được giữ trong endpoints nhận traffic |
| Readiness `DOWN` | Instance tạm thời không nên nhận công việc mới? | Bị loại khỏi Service endpoints |
| Liveness `UP` | Process còn hoạt động? | Không cần restart vì probe |
| Liveness `DOWN` | Process không thể tiếp tục hoạt động? | Kubernetes có thể restart container sau ngưỡng thất bại |
| Startup chưa thành công | Ứng dụng còn đang khởi động? | Startup probe trì hoãn readiness/liveness probes |

Readiness và liveness không phải hai tên khác nhau cho cùng một phép ping. Mỗi trạng thái phải gắn với một **hợp đồng vận hành rõ ràng**.

## 2. Readiness: khả năng nhận traffic hoặc công việc mới

Readiness trả lời liệu instance có đủ điều kiện để nhận công việc mới tại thời điểm kiểm tra không.

Một service HTTP có thể chưa ready khi:

- Chưa hoàn tất khởi tạo cache hoặc cấu hình bắt buộc.
- Đang thực hiện graceful shutdown.
- Một dependency bắt buộc cho toàn bộ endpoint không khả dụng.
- Ứng dụng chủ động từ chối traffic trong thời gian bảo trì.
- Một trạng thái nội bộ khiến instance không thể thực hiện đúng hợp đồng service.

Một worker Spring Kafka có thể cần readiness policy khác:

- Listener bắt buộc chưa được start.
- Dependency bắt buộc để xử lý mọi record chưa sẵn sàng.
- Consumer đang ở trạng thái dừng có chủ đích.
- Worker đang thực hiện chuyển giao hoặc shutdown có trật tự.

Nhưng **readiness không đồng nghĩa consumer đã được Kafka assign partition**. Consumer có thể đã start nhưng chưa nhận assignment; cũng có thể không có partition vì số consumer trong group lớn hơn số partition. Nếu business contract yêu cầu assignment, đó là một điều kiện riêng cần theo dõi.

Readiness nên phản ánh khả năng phục vụ theo chức năng service cung cấp, không chỉ sự tồn tại của các bean trong Spring context.

## 3. Liveness: khả năng process tiếp tục hoạt động

Liveness tập trung vào tình trạng bên trong process. Câu hỏi là: nếu tiếp tục để instance chạy, nó có khả năng tự phục hồi và tiến triển không?

Các trường hợp có thể cần liveness failure:

- Deadlock nội bộ hoặc thread pool quan trọng bị kẹt không thể phục hồi.
- Một lỗi nghiêm trọng làm ứng dụng không thể tiếp tục hoạt động đúng.
- Một trạng thái nội bộ không thể được sửa bằng retry hoặc reconnect.
- Ứng dụng phát hiện invariant nội bộ bị phá vỡ và chính sách vận hành yêu cầu restart.

Những tình huống sau **không tự động là liveness failure**:

- Kafka broker đang bảo trì hoặc mất kết nối tạm thời.
- PostgreSQL tạm thời từ chối connection.
- Một downstream HTTP service timeout.
- Consumer group đang rebalance.
- Topic không có record mới.
- Một partition đang idle.
- Consumer lag tăng nhưng process vẫn poll và xử lý.
- DLT publish tạm thời thất bại.

Nếu một dependency bên ngoài unavailable, restart JVM thường không sửa được dependency. Nó có thể làm mất cache, tạo connection churn, tăng consumer group rebalances và gây thêm tải lên hệ thống đang gặp sự cố.

## 4. Spring Boot ApplicationAvailability

Spring Boot cung cấp `ApplicationAvailability` để truy vấn hai trạng thái chính:

- `LivenessState`: `CORRECT` hoặc `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC`.

Ví dụ:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public void report() {
        LivenessState liveness = availability.getLivenessState();
        ReadinessState readiness = availability.getReadinessState();

        // Gửi trạng thái vào log/diagnostic theo nhu cầu.
    }
}
~~~

`ApplicationAvailability` là nguồn trạng thái trong Spring ApplicationContext. Nó không tự kiểm tra Kafka hoặc database mỗi lần gọi. Trạng thái thay đổi qua các application availability events, thường được publish bởi Spring Boot trong quá trình lifecycle hoặc bởi ứng dụng theo chính sách riêng.

| Enum | Ý nghĩa |
|---|---|
| `LivenessState.CORRECT` | Ứng dụng được xem là còn có thể hoạt động |
| `LivenessState.BROKEN` | Ứng dụng không thể tiếp tục hoạt động theo đánh giá nội bộ |
| `ReadinessState.ACCEPTING_TRAFFIC` | Sẵn sàng nhận traffic/công việc |
| `ReadinessState.REFUSING_TRAFFIC` | Tạm thời không nhận traffic/công việc mới |

## 5. Thay đổi readiness và liveness bằng AvailabilityChangeEvent

Spring Boot cho phép ứng dụng publish `AvailabilityChangeEvent` để chuyển trạng thái.

Ví dụ service bắt đầu shutdown có trật tự và từ chối traffic mới:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceCoordinator {

    private final ApplicationContext context;

    public MaintenanceCoordinator(ApplicationContext context) {
        this.context = context;
    }

    public void stopAcceptingNewWork() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeAcceptingWork() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Khi ứng dụng phát event, Spring Boot cập nhật trạng thái readiness mà health indicator tương ứng sử dụng. Các thành phần khác cũng có thể lắng nghe availability event để phối hợp hành động.

Liveness có thể được chuyển trạng thái tương tự:

~~~java
AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
~~~

và khi một trạng thái có thể phục hồi theo chính sách ứng dụng:

~~~java
AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
~~~

**Cẩn thận với `BROKEN`:** khi liveness probe phản ánh trạng thái này, Kubernetes có thể restart container. Không dùng nó như một cảnh báo chung cho Kafka outage hoặc database timeout.

Việc publish `REFUSING_TRAFFIC` cũng không tự dừng Kafka consumer. Nó cập nhật availability state của Spring Boot; cơ chế listener container phải được điều khiển riêng nếu service là worker consume-only.

## 6. Actuator health groups cho liveness và readiness

Spring Boot Actuator có thể expose hai health groups:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Cấu hình cơ bản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

`livenessState` và `readinessState` là các health contributors gắn với `ApplicationAvailability`.

Response minh họa:

~~~json
{
  "status": "UP"
}
~~~

Khi ứng dụng chuyển sang `REFUSING_TRAFFIC`, readiness group có thể trả status không healthy (thường là `OUT_OF_SERVICE` theo health mapping mặc định). Liveness vẫn có thể `UP`.

Status HTTP cụ thể phụ thuộc health status mapping và cấu hình endpoint. Trong Kubernetes, probe chủ yếu đánh giá HTTP success/failure theo mã phản hồi; vì vậy cần kiểm tra response code thực tế thay vì chỉ nhìn chuỗi status trong JSON.

### 6.1. Đưa dependency vào readiness group

Nếu service không thể thực hiện chức năng chính khi database unavailable, có thể đưa database health vào readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Tương tự, có thể thêm `kafka` nếu việc kết nối Kafka là điều kiện cần thiết để instance nhận công việc mới theo hợp đồng của service.

Không đưa mọi dependency vào readiness theo mặc định. Nếu một dependency chỉ phục vụ một endpoint phụ, việc dependency đó lỗi không nhất thiết khiến toàn bộ instance phải bị loại khỏi traffic.

### 6.2. Tách health group theo capability

Với service có nhiều chức năng, có thể expose các góc nhìn riêng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
        kafkaConnectivity:
          include: kafka
~~~

`kafkaConnectivity` giúp người vận hành xem trạng thái Admin connectivity mà không buộc readiness của toàn service phải phụ thuộc Kafka. Tên group là ví dụ; cần đảm bảo contributor ID thực tế khớp cấu hình.

Health groups là cách phân loại kết quả quan sát. Chúng không tự điều khiển listener lifecycle hoặc Kafka consumer group.

## 7. Kubernetes xử lý startup, readiness và liveness như thế nào?

Kubernetes cung cấp ba loại probe thường dùng:

| Probe | Mục tiêu | Khi thất bại |
|---|---|---|
| `startupProbe` | Ứng dụng đã hoàn thành giai đoạn khởi động chưa? | Container bị xem là chưa start thành công; các probe khác được trì hoãn |
| `readinessProbe` | Container có nên nhận traffic từ Service không? | Pod bị đánh dấu NotReady và bị loại khỏi endpoints phù hợp |
| `livenessProbe` | Container có cần restart để phục hồi không? | Sau số lần thất bại cấu hình, kubelet restart container |

~~~text
Container starts
      |
      v
Startup probe succeeds?
      |
      +---- No -> tiếp tục chờ / hết ngưỡng thì restart
      |
      v
Startup complete
      |
      +---- Readiness probe -> nhận traffic hay không
      |
      +---- Liveness probe  -> giữ process hay restart
~~~

`startupProbe` hữu ích cho ứng dụng khởi động lâu, chẳng hạn phải load cấu hình, warm cache hoặc khởi tạo nhiều Spring beans. Khi startup probe chưa thành công, Kubernetes chưa dùng readiness/liveness để đánh giá container theo cách thông thường.

### 7.1. Cấu hình probes trong Deployment

Ví dụ:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: payment-worker
      image: example/payment-worker:latest
      ports:
        - name: http
          containerPort: 8080

      startupProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 30

      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3

      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 2
~~~

Các giá trị chỉ minh họa, cần điều chỉnh theo startup time và SLO. `failureThreshold × periodSeconds` giúp ước lượng khoảng thời gian trước khi Kubernetes coi probe thất bại liên tục, nhưng còn có `timeoutSeconds`, `initialDelaySeconds` và thời điểm thực tế của lần probe.

Readiness failure không restart container. Liveness failure có thể dẫn tới restart. Đặt nhầm Kafka dependency vào liveness có thể khiến toàn bộ replicas restart khi Kafka cluster đang bảo trì.

### 7.2. Additional probe paths trên main port

Ở các phiên bản Spring Boot hỗ trợ, có thể bật additional paths:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Điều này có thể expose `/livez` và `/readyz` trên main application port. Nó hữu ích khi management server chạy port riêng: probe trên management port có thể vẫn trả lời dù main server port bị lỗi.

Kiểm tra chính xác khả năng và path theo Spring Boot version đang dùng. Không giả định mọi version có cùng defaults.

## 8. Kafka connection health không phải liveness

Một Kafka health indicator thường kiểm tra khả năng giao tiếp với cluster qua Kafka Admin API. Nếu broker không reachable, contributor có thể trả `DOWN`.

Nhưng điều đó không chứng minh JVM bị hỏng:

~~~text
Kafka cluster outage
      |
      +---- KafkaHealthIndicator = DOWN
      |
      +---- JVM / Spring context vẫn hoạt động
      |
      +---- Kafka client có thể retry/reconnect
      |
      +---- Liveness nên vẫn UP
~~~

Nếu đưa Kafka health vào liveness, Kubernetes có thể restart mọi Pods. Khi broker phục hồi, các Pods đồng loạt tạo kết nối, khởi động consumer và tham gia rebalance, gây thêm áp lực lên cluster.

Thông thường:
- Liveness tập trung vào khả năng tự phục hồi của process.
- Readiness có thể xét Kafka nếu service thực sự không thể nhận công việc khi Kafka unavailable.
- Kafka connectivity được quan sát riêng bằng health component/metrics.
- Consumer progress được đánh giá bằng assignment, lag, processing rate và error rate.

## 9. Readiness của HTTP service và readiness của Kafka worker khác nhau

Đây là điểm quan trọng khi áp dụng Kubernetes cho Spring Kafka.

Với HTTP API, Kubernetes readiness failure thường loại Pod khỏi Service endpoints. Request mới không được load balancer gửi tới instance đó.

Với Kafka consumer, broker **không dùng Kubernetes readiness** để phân phối partition. Kafka group coordinator dựa trên consumer membership, subscription, heartbeat và rebalance protocol.

~~~text
HTTP workload:
  Readiness DOWN
      |
      v
  Pod bị loại khỏi Service endpoints

Kafka workload:
  Readiness DOWN
      |
      v
  Kafka broker vẫn thấy consumer member
      |
      v
  Consumer vẫn có thể tiếp tục poll/process
~~~

Vì vậy, nếu consumer worker không thể xử lý record do dependency database unavailable, chỉ chuyển readiness sang `REFUSING_TRAFFIC` **không tự động ngừng consume**.

Cần một chính sách riêng để điều khiển listener container nếu yêu cầu là dừng nhận công việc mới trong thời gian dependency không sẵn sàng.

## 10. Điều khiển Kafka listener khi worker không ready

Spring Kafka cung cấp `KafkaListenerEndpointRegistry` để tìm các containers được tạo bởi `@KafkaListener`. Từ đó ứng dụng có thể điều khiển lifecycle hoặc pause/resume theo policy.

Ví dụ quản lý pause/resume:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ConsumerWorkGate {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerWorkGate(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

`pause()` là yêu cầu tạm ngừng delivery theo container API; container vẫn có thể tiếp tục polling để duy trì consumer group membership. Chi tiết thời điểm pause có hiệu lực và callback phụ thuộc loại container/version.

| Thao tác | Mục đích | Hệ quả group |
|---|---|---|
| `pause()` | Tạm ngừng giao record cho listener | Container có thể tiếp tục poll và duy trì membership |
| `resume()` | Cho phép listener nhận record lại | Tiếp tục xử lý theo assignment hiện tại nếu còn hợp lệ |
| `stop()` | Kết thúc container lifecycle | Consumer đóng và rời group, có thể gây rebalance |
| `start()` | Khởi động lại container | Consumer tham gia group và có thể trigger rebalance |

Không gọi pause/stop trực tiếp bên trong một health indicator. Health check nên quan sát và trả status; một coordinator riêng quyết định action sau khi áp dụng threshold, debounce và recovery policy.

### 10.1. Không pause ngay sau một lỗi database đơn lẻ

Nếu một query tạm timeout trong vài trăm millisecond, pause toàn bộ consumer có thể gây dao động không cần thiết. Một policy thực tế có thể:

1. Đếm số lần lỗi dependency liên tiếp.
2. Đánh giá thời gian lỗi và khả năng retry.
3. Khi vượt threshold, chuyển readiness sang `REFUSING_TRAFFIC` nếu phù hợp.
4. Với consumer worker, pause listener nếu việc tiếp tục consume có nguy cơ làm lỗi/rollback liên tục.
5. Tiếp tục theo dõi dependency bằng health check bounded.
6. Khi dependency phục hồi ổn định, resume listener và chuyển readiness về `ACCEPTING_TRAFFIC`.

Phải tránh tạo vòng lặp: pause khiến consumer không xử lý, nhưng không có worker nào kiểm tra dependency để resume. Health coordinator nên độc lập với listener đang pause.

### 10.2. Khi nào nên stop thay vì pause?

Pause phù hợp khi muốn tạm dừng delivery nhưng giữ consumer group membership. Stop phù hợp khi cần giải phóng consumer và partition ownership, chẳng hạn shutdown hoặc maintenance dài.

Stop có thể tạo rebalance, làm partition chuyển sang instance khác. Nếu các instances khác cũng không thể xử lý do cùng dependency outage, việc stop đồng loạt có thể chỉ chuyển backlog sang nơi khác.

## 11. Chọn dependency nào đưa vào readiness?

Không phải dependency nào cũng nên nằm trong readiness group.

| Dependency | Câu hỏi để quyết định |
|---|---|
| PostgreSQL | Service có thể trả lời/tiếp nhận request chính nếu DB unavailable không? |
| Kafka | Service có cần publish/consume để hoàn thành hợp đồng của request mới không? |
| Redis/cache | Cache lỗi có thể fallback sang nguồn chính hay không? |
| External payment API | Có thể nhận request và queue để xử lý sau không? |
| Schema Registry | Consumer/producer có thể tiếp tục với schema cache hiện tại không? |
| DLT topic | Publish DLT failure có làm service không thể bảo toàn record lỗi không? |

Một dependency có thể quan trọng nhưng không nhất thiết phải làm toàn bộ service unready. Ví dụ API có thể nhận lệnh và ghi vào database/outbox ngay cả khi Kafka tạm unavailable; nếu vậy, loại Pod khỏi readiness có thể làm mất khả năng tiếp nhận yêu cầu mà vẫn có thể bảo toàn qua outbox.

Ngược lại, nếu một endpoint bắt buộc gọi payment gateway đồng bộ và không có fallback, readiness có thể phản ánh khả năng phục vụ endpoint đó — nhưng health group thường ở cấp instance, không phải per-endpoint. Cần cân nhắc degraded mode hoặc tách capability/service.

## 12. Dependency outage và cascading failure

Giả sử Kafka outage ảnh hưởng toàn bộ worker replicas:

~~~text
Kafka outage
    |
    +---- readiness check Kafka = DOWN trên mọi Pod
    |
    +---- tất cả Pod NotReady
    |
    +---- nếu liveness cũng phụ thuộc Kafka:
              |
              v
          restart storm
              |
              v
          connection/rebalance churn
              |
              v
          Kafka recovery khó hơn
~~~

Readiness DOWN có thể hữu ích để ngăn HTTP traffic tới instance không phục vụ được. Nhưng nếu mọi replica đều unready, cần hiểu hậu quả với upstream: load balancer có thể không còn endpoint nào và bắt đầu trả 503.

Một số cách giảm tác động:
- Có degraded mode rõ ràng, ví dụ API nhận lệnh và lưu outbox.
- Chỉ đưa dependency bắt buộc vào readiness.
- Dùng retry/backoff và circuit breaker theo policy.
- Tách readiness của HTTP API khỏi trạng thái consumer worker khi capability khác nhau.
- Tránh restart toàn bộ Pods do dependency outage.
- Alert về dependency health độc lập với liveness.

## 13. Graceful shutdown và readiness

Khi Pod bị terminate, ứng dụng nên ngừng nhận traffic mới trước khi đóng tài nguyên.

~~~text
SIGTERM / shutdown signal
          |
          v
Readiness -> REFUSING_TRAFFIC
          |
          v
Kubernetes cập nhật endpoints
          |
          v
Spring lifecycle stop listener containers
          |
          v
In-flight work hoàn tất theo policy
          |
          v
Đóng DB / producer / executor / context
          |
          v
Process exit
~~~

Thứ tự và thời gian thực tế phụ thuộc Spring lifecycle phases, termination hooks và cấu hình ứng dụng. Kubernetes endpoint propagation không đồng nghĩa mọi request mới biến mất tức thì; nên có khoảng chờ/connection draining thích hợp.

Với Kafka listener:
- Container stop cần ngân sách đủ để hoàn tất xử lý hiện tại theo chính sách.
- Kafka offset chỉ commit khi ack/transaction semantics cho phép.
- Nếu process bị `SIGKILL`, record chưa commit có thể redelivery.
- Business side effects cần idempotency.
- Không dùng readiness event làm bằng chứng record đã commit.

`terminationGracePeriodSeconds`, Spring lifecycle timeout và Kafka container shutdown timeout phải được phối hợp.

## 14. Availability state và custom health indicator

Availability state biểu diễn ý định và trạng thái của ứng dụng; `HealthIndicator` kiểm tra một thành phần hoặc capability.

Ví dụ custom readiness indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersProcessing")
public class OrdersProcessingHealthIndicator implements HealthIndicator {

    private final ProcessingGate gate;

    public OrdersProcessingHealthIndicator(ProcessingGate gate) {
        this.gate = gate;
    }

    @Override
    public Health health() {
        if (gate.isAcceptingWork()) {
            return Health.up()
                    .withDetail("acceptingWork", true)
                    .build();
        }

        return Health.outOfService()
                .withDetail("acceptingWork", false)
                .withDetail("reason", gate.reason())
                .build();
    }
}
~~~

`ProcessingGate` là abstraction do ứng dụng định nghĩa, không phải Spring Kafka API. Nó có thể tổng hợp trạng thái database dependency, maintenance mode hoặc listener coordinator.

Có thể thêm contributor vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,ordersProcessing
~~~

Tránh thực hiện một network call không giới hạn ngay trong mỗi lần `health()`. Nếu cần kiểm tra dependency, dùng timeout hữu hạn và cân nhắc cache kết quả gần nhất với tuổi dữ liệu rõ ràng.

## 15. Không nhầm Kafka health với Kafka processing readiness

Kafka health indicator có thể kiểm tra Admin connectivity nhưng không đảm bảo producer/consumer capability. Một service có thể có:

~~~text
Kafka Admin health: UP
Producer write:      DENIED
Consumer read:       OK
Listener assignment: empty
Database:             UP
~~~

Tách các tín hiệu:

| Tín hiệu | Mục đích |
|---|---|
| Kafka cluster connectivity | AdminClient có giao tiếp với cluster không? |
| Producer capability | Producer có thể ghi vào topic bắt buộc không? |
| Consumer capability | Consumer có thể join group/fetch dữ liệu không? |
| Listener readiness | Container đã start và có trạng thái phù hợp không? |
| Assignment | Consumer đang sở hữu partition nào? |
| Processing health | Record có được xử lý đúng latency/error SLO không? |

Với canary produce/consume, nên dùng topic riêng, event ID riêng, cleanup/retention và lịch synthetic monitoring thay vì gắn trực tiếp vào liveness.

## 16. Readiness trong ứng dụng có nhiều listeners

Một service có thể có:
- `orders-listener`: bắt buộc cho nghiệp vụ chính.
- `analytics-listener`: optional, lỗi không làm mất khả năng xử lý order.
- `audit-listener`: cần chạy nhưng có thể có backlog được chấp nhận trong thời gian ngắn.

Một readiness state duy nhất ở cấp application cần có policy tổng hợp:

~~~text
orders-listener:    READY
analytics-listener: STOPPED (optional)
audit-listener:     READY
        |
        v
Application readiness: ACCEPTING_TRAFFIC
~~~

Nếu listener bắt buộc không ready, ứng dụng có thể chuyển sang `REFUSING_TRAFFIC`. Nhưng đối với worker-only application, readiness HTTP không ảnh hưởng trực tiếp Kafka assignment. Nếu cần dừng chỉ một listener, dùng registry để điều khiển đúng listener ID, không stop toàn bộ context.

Cần định nghĩa rõ listener nào critical, listener nào optional, một listener stop có làm API unready không, khi nào pause/stop và ai chịu trách nhiệm resume.

## 17. Health check không nên blocking hoặc gây side effect

Health endpoint có thể được gọi bởi nhiều probes và monitoring systems. Một check chờ Kafka Admin request vô thời hạn có thể làm cạn request threads.

Một health indicator tốt cần:
1. Timeout hữu hạn.
2. Không tạo Kafka producer/consumer mới ở mỗi lần gọi.
3. Không gửi business events hoặc commit offsets.
4. Không chạy query scan nặng.
5. Không expose credentials/topology nhạy cảm.
6. Có metric/log cho duration và failure.
7. Không biến lỗi telemetry thành liveness failure.

Nếu health result được cache, cần thể hiện độ tuổi kết quả và policy khi cache quá cũ. Cache `UP` quá lâu có thể che giấu outage; không cache thì probe quá thường xuyên có thể tạo tải.

## 18. Security của Actuator endpoints

Health endpoint có thể lộ broker hostnames/cluster ID, topic names, consumer group details và exception metadata.

Production configuration nên giới hạn exposure và details:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Nếu kubelet cần truy cập probe path, bảo đảm cấu hình security cho phép health probe nội bộ nhưng không công khai details cho mọi client. Có thể dùng management port riêng, network policy và authentication phù hợp kiến trúc.

Không trả SASL JAAS config, password, tokens hoặc raw client properties trong health details.

## 19. Integration test cho readiness và liveness

Test cần xác nhận cả ApplicationAvailability, Actuator group và policy tích hợp.

### 19.1. Kiểm tra trạng thái mặc định

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AvailabilityHealthIT {

    @Autowired
    MockMvc mvc;

    @Test
    void applicationStartsReadyAndAlive() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Test cần expose Actuator health groups trong test configuration. Tùy version/management port, path và response có thể khác.

### 19.2. Readiness chuyển sang REFUSING_TRAFFIC

~~~java
@Autowired
ApplicationContext context;

@Test
void readinessCanRefuseTrafficWhileLivenessRemainsUp() throws Exception {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC);

    mvc.perform(get("/actuator/health/readiness"))
            .andExpect(status().isServiceUnavailable());

    mvc.perform(get("/actuator/health/liveness"))
            .andExpect(status().isOk());
}
~~~

Imports gồm `AvailabilityChangeEvent` và `ReadinessState`. Test giả định status mapping mặc định và health group chỉ chứa readiness state; nếu thêm custom indicators, kết quả tổng hợp phải được điều chỉnh theo policy.

### 19.3. Test consumer worker pause/resume

Với Kafka Testcontainers hoặc Embedded Kafka:

1. Start listener container và chờ assignment.
2. Gửi record, xác nhận listener nhận.
3. Coordinator pause listener.
4. Gửi thêm record và xác nhận listener không dispatch chúng trong thời gian pause.
5. Xác nhận container vẫn giữ trạng thái lifecycle phù hợp theo phiên bản.
6. Resume listener và xác nhận backlog được xử lý.
7. Kiểm tra offset/duplicate semantics.
8. Dừng container và cleanup group/topic.

Không chỉ test HTTP readiness DOWN rồi giả định Kafka consumer tự dừng. Phải kiểm tra riêng hành động pause/stop đã được coordinator thực hiện.

### 19.4. Test Kubernetes policy

Integration tests có thể xác nhận HTTP status/path, còn behavior restart/endpoint removal cần kiểm tra trong môi trường Kubernetes hoặc qua manifest validation. Cần xác nhận readiness failure không restart container, liveness failure mới kích hoạt restart theo threshold, startup probe trì hoãn hai probe còn lại, Kafka outage không làm liveness DOWN và shutdown có đủ termination grace period.

## 20. Các sai lầm thường gặp

- **Dùng một health endpoint cho cả readiness và liveness:** dễ restart khi dependency ngoài lỗi.
- **Đưa Kafka vào liveness:** broker outage có thể gây restart storm.
- **Cho rằng readiness DOWN tự dừng Kafka listener:** Kubernetes không điều khiển Kafka group qua readiness.
- **Dùng readiness để chứng minh consumer đã được assign partition:** assignment là trạng thái riêng.
- **Dùng consumer start event làm bằng chứng ready:** consumer có thể start nhưng chưa có partition hoặc không xử lý được record.
- **Đưa mọi dependency vào readiness:** một dependency optional có thể loại cả service khỏi traffic.
- **Không định nghĩa listener critical/optional:** một listener phụ dừng có thể làm cả app unready không cần thiết.
- **Pause listener nhưng không có cơ chế resume:** worker bị kẹt vĩnh viễn sau dependency recovery.
- **Stop mọi consumer khi dependency outage:** gây rebalance và chuyển backlog sang replicas khác dù chúng cũng không xử lý được.
- **Gọi network check không timeout trong HealthIndicator:** health endpoint có thể treo.
- **Dùng liveness để chữa lỗi ACL:** restart không sửa credentials/permissions.
- **Không phối hợp startupProbe:** ứng dụng khởi động chậm bị liveness kill trước khi ready.
- **Coi HTTP 200 của management port là app main port khỏe:** management server có thể vẫn sống trong khi main server bị lỗi.
- **Không kiểm thử shutdown/redelivery:** record in-flight có thể được giao lại sau restart.
- **Trả health details công khai:** lộ cluster topology và exception metadata.

## 21. Checklist thiết kế production

Trước khi triển khai readiness/liveness cho service Spring Kafka, hãy xác định:

1. Readiness phản ánh capability nào: HTTP traffic, Kafka consume, Kafka produce hay tất cả?
2. Liveness chỉ phản ánh lỗi process có thể cần restart chưa?
3. Kafka/database outage có được giữ ngoài liveness không?
4. Dependency nào thực sự bắt buộc để phục vụ workload chính?
5. Listener nào critical, listener nào optional?
6. Readiness failure có ảnh hưởng gì tới Kubernetes Service endpoints?
7. Với worker-only service, ai sẽ pause/stop listener khi dependency không sẵn sàng?
8. Ai sẽ resume listener sau khi dependency phục hồi?
9. Pause hay stop phù hợp với yêu cầu group membership và rebalance?
10. StartupProbe có đủ ngân sách cho Spring context và Kafka initialization không?
11. Liveness/readiness timeout và failure thresholds có tránh flapping không?
12. Health indicators có timeout hữu hạn và không tạo side effects không?
13. Actuator details có được bảo vệ không?
14. Graceful shutdown có phối hợp readiness, listener stop, transaction và termination grace period không?
15. Integration tests có chứng minh readiness và liveness tách biệt?
16. Kafka worker tests có xác nhận pause/resume thực tế, không chỉ HTTP status?
17. Consumer lag, assignment, retry/DLT và processing latency có dashboard riêng không?

**Tách readiness và liveness** giúp Spring Boot/Kubernetes phản ứng đúng với hai loại vấn đề: instance chưa thể nhận công việc mới và process không còn khả năng tiếp tục hoạt động. Với Spring Kafka, cần thêm một ranh giới quan trọng: readiness HTTP không tự dừng consumer hoặc thay đổi partition assignment. Hãy dùng Actuator availability states để biểu diễn trạng thái ứng dụng, Kubernetes probes để điều phối Pod, và listener container APIs để kiểm soát việc consume theo policy riêng. Giữ dependency outage ngoài liveness trừ khi có bằng chứng process cần restart; đồng thời định nghĩa rõ capability, pause/resume, shutdown và recovery để tránh restart storm, backlog chuyển vòng hoặc record bị xử lý sai.

