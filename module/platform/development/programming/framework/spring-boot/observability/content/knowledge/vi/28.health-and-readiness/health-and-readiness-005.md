# Startup state trong Spring Boot

Khi một instance Spring Boot vừa khởi động, process có thể đã mở port nhưng ứng dụng chưa chắc sẵn sàng phục vụ request. Bean có thể còn đang khởi tạo, cache chưa warm, schema check chưa hoàn tất hoặc kết nối tới dependency thiết yếu chưa được xác minh. Nếu load balancer gửi traffic quá sớm, người dùng có thể nhận lỗi dù container đã ở trạng thái running. **Startup state** mô tả giai đoạn ứng dụng đi từ khởi tạo đến sẵn sàng nhận traffic, giúp Spring Boot, Actuator và orchestrator phối hợp đúng thời điểm.

Trong module **SPRING_BOOT_OBSERVABILITY**, startup state thuộc chương **Health và readiness**, liên kết health endpoint, liveness/readiness, metrics, logs và tracing. Bài tập trung vào application availability state của Spring Boot: lifecycle events, ApplicationAvailability, LivenessState và ReadinessState, readiness transitions, warm-up/initialization, asynchronous startup, Kubernetes probes, graceful shutdown, kiểm thử và troubleshooting.

## Mục tiêu học tập

1. Mô tả các giai đoạn khởi động của Spring Boot application.
2. Phân biệt process running với application ready.
3. Sử dụng ApplicationAvailability để đọc liveness/readiness state.
4. Hiểu các AvailabilityChangeEvent và trạng thái LivenessState/ReadinessState.
5. Điều khiển readiness trong quá trình warm-up và startup tasks.
6. Tích hợp startup/readiness probes của Kubernetes.
7. Tránh block startup hoặc nhận traffic trước khi dependency thiết yếu sẵn sàng.
8. Kết hợp readiness với graceful shutdown và traffic draining.
9. Kiểm thử startup transitions và các tình huống khởi động lỗi.

## 1. Startup state là gì?

Startup state là trạng thái vận hành của application trong quá trình chuyển từ process vừa chạy tới instance có thể nhận traffic. Trong Spring Boot, application availability được biểu diễn qua các state như liveness và readiness. Những state này cho phép các thành phần bên ngoài hỏi đúng câu hỏi:

- Process/application còn hoạt động hay đã rơi vào trạng thái cần restart?
- Instance đã sẵn sàng nhận request chưa?
- Instance đang warm-up, từ chối traffic hay đang shutdown?

Port mở hoặc JVM tồn tại không đồng nghĩa application ready. Tương tự, health endpoint trả UP ở một thời điểm không thay thế readiness policy của ứng dụng.

### 1.1. Các giai đoạn khởi động thường gặp

~~~mermaid
flowchart TD
    Start["JVM process starts"] --> Context["Spring ApplicationContext refresh"]
    Context --> Beans["Create beans and infrastructure"]
    Beans --> Started["ApplicationStartedEvent"]
    Started --> Runners["ApplicationRunner / CommandLineRunner"]
    Runners --> Ready["ApplicationReadyEvent"]
    Ready --> Accept["Readiness: ACCEPTING_TRAFFIC"]
    Accept --> Serve["Serve requests"]
    Serve --> Stop["Shutdown begins"]
    Stop --> Refuse["Readiness: REFUSING_TRAFFIC"]
    Refuse --> Drain["Drain in-flight requests"]
    Drain --> Exit["Process exits"]
~~~

Đây là sơ đồ khái quát. Các lifecycle events có thứ tự và semantics cụ thể trong Spring Boot; ứng dụng cần phân biệt context refresh, runner completion và readiness transition.

### 1.2. Process state, liveness và readiness

| Khái niệm | Câu hỏi | Hành động thường gặp |
| --- | --- | --- |
| Process running | JVM/container còn chạy? | Runtime/container status |
| Liveness | Application có thể tiếp tục hoạt động? | Restart nếu probe thất bại |
| Readiness | Instance có nên nhận traffic? | Add/remove khỏi service endpoints |
| Startup probe | Ứng dụng đã qua giai đoạn khởi động? | Tạm hoãn liveness/readiness checks |

Không dùng một tín hiệu duy nhất để đại diện mọi trạng thái. Kubernetes có thể thấy process running trong khi readiness vẫn false.

## 2. ApplicationAvailability trong Spring Boot

Spring Boot cung cấp ApplicationAvailability để đọc trạng thái availability hiện tại của application. Các state quan trọng:

- LivenessState: CORRECT hoặc BROKEN.
- ReadinessState: ACCEPTING_TRAFFIC hoặc REFUSING_TRAFFIC.

Ví dụ đọc trạng thái:

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

        // Send these states to an internal diagnostic logger if needed.
    }
}
~~~

ApplicationAvailability phản ánh state được publish trong application context. Nó không chủ động ping mọi dependency và không tự quyết định readiness theo nghiệp vụ.

### 2.1. LivenessState

CORRECT cho biết application không báo trạng thái broken. BROKEN cho biết application đang ở trạng thái không thể tiếp tục bình thường và có thể cần restart.

Không chuyển liveness thành BROKEN chỉ vì database hoặc remote API tạm thời unavailable. Nếu mọi replica cùng restart do một dependency chung, sự cố có thể nặng hơn.

### 2.2. ReadinessState

REFUSING_TRAFFIC biểu thị instance chưa nên nhận traffic. ACCEPTING_TRAFFIC biểu thị instance có thể nhận traffic theo readiness policy.

Trong quá trình startup, Spring Boot quản lý readiness transition theo lifecycle. Ứng dụng có thể phát AvailabilityChangeEvent để chuyển state khi có bước khởi tạo riêng cần hoàn tất hoặc khi bắt đầu shutdown.

## 3. Lifecycle events và thời điểm sẵn sàng

Một số Spring Boot events thường gặp:

| Event | Thời điểm | Dùng cho |
| --- | --- | --- |
| ApplicationStartingEvent | Startup rất sớm | Listener trước ApplicationContext |
| ApplicationEnvironmentPreparedEvent | Environment đã chuẩn bị | Environment-level setup |
| ApplicationContextInitializedEvent | Context được khởi tạo trước refresh | Context initializers/listeners |
| ApplicationPreparedEvent | Context chuẩn bị refresh | Setup trước bean creation |
| ApplicationStartedEvent | Context refresh hoàn tất | Startup work trước runners |
| ApplicationReadyEvent | Runners đã hoàn tất | Ứng dụng sẵn sàng theo lifecycle |
| ApplicationFailedEvent | Startup thất bại | Ghi nhận lỗi startup |

Readiness state thường chuyển sang ACCEPTING_TRAFFIC sau khi application ready event được xử lý. Không đồng nhất ApplicationStartedEvent với ApplicationReadyEvent: runner có thể còn chạy sau event started.

### 3.1. ApplicationRunner và CommandLineRunner

Runners phù hợp cho công việc cần hoàn tất trong startup sequence, ví dụ validate startup configuration hoặc nạp dữ liệu nhỏ bắt buộc:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class StartupValidationConfiguration {
    @Bean
    ApplicationRunner startupValidation() {
        return args -> {
            // Validate required configuration and local invariants.
        };
    }
}
~~~

Runner đồng bộ kéo dài startup. Chỉ đặt ở đây công việc thực sự cần hoàn tất trước khi application được xem là ready. Không tải hàng triệu records hoặc chạy migration dài không kiểm soát trong runner nếu có phương án triển khai tốt hơn.

### 3.2. ApplicationReadyEvent

Có thể lắng nghe ApplicationReadyEvent để thực hiện hành động sau startup lifecycle:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Emit a startup-completed log or trigger non-blocking work.
    }
}
~~~

Listener chạy khi application đã tới ready event. Nếu công việc này là điều kiện bắt buộc trước traffic, không nên đặt nó thành tác vụ nền fire-and-forget rồi giả định readiness sẽ tự chờ. Hãy thiết kế readiness transition rõ ràng.

## 4. Điều khiển ReadinessState bằng AvailabilityChangeEvent

Ứng dụng có thể phát AvailabilityChangeEvent để thông báo thay đổi state. Ví dụ một startup coordinator đặt instance ở trạng thái từ chối traffic trong khi warm-up:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class StartupReadinessCoordinator {
    private final ApplicationEventPublisher events;

    public StartupReadinessCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void beginWarmup() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void completeWarmup() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Đây là API điều khiển state; cần gọi ở lifecycle boundary phù hợp. Nếu gọi completeWarmup quá sớm, instance có thể nhận traffic trước khi thực sự sẵn sàng. Nếu quên chuyển về ACCEPTING_TRAFFIC, pod sẽ ở trạng thái not ready dù application khỏe.

### 4.1. Chỉ readiness hay cả liveness?

Warm-up thông thường nên ảnh hưởng readiness, không phải liveness. Application vẫn sống trong lúc cache nạp hoặc index warm-up. Nếu warm-up thất bại vĩnh viễn và process không thể phục hồi, policy có thể chuyển liveness BROKEN, nhưng cần xác định rõ điều kiện và tránh phản ứng với lỗi dependency tạm thời.

### 4.2. Trạng thái phải có owner

Một coordinator hoặc lifecycle component nên chịu trách nhiệm chuyển state. Tránh nhiều bean độc lập cùng phát event readiness theo các điều kiện khác nhau khiến state thay đổi qua lại. Nếu nhiều bước bắt buộc, dùng một startup coordinator tổng hợp kết quả.

## 5. Startup warm-up và initialization strategy

Startup work thường thuộc một trong các nhóm:

| Công việc | Chiến lược phù hợp |
| --- | --- |
| Validate config/schema compatibility | Hoàn tất trước ready nếu bắt buộc |
| Load small reference data | Runner hoặc initialization component |
| Warm critical cache | Readiness remains refusing đến khi xong |
| Preload large dataset | Background warm-up có readiness policy |
| Optional analytics connection | Không nhất thiết block readiness |
| External service discovery | Timeout/retry giới hạn, degraded mode nếu có |

### 5.1. Warm-up đồng bộ

Đồng bộ phù hợp khi công việc ngắn, bắt buộc và có timeout. Nó kéo dài startup time; Kubernetes startupProbe phải có budget tương ứng.

### 5.2. Warm-up bất đồng bộ

Nếu warm-up chạy nền, ứng dụng phải giữ readiness ở REFUSING_TRAFFIC cho tới khi hoàn tất. Ví dụ:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class CacheWarmup {
    private final ThreadPoolTaskExecutor executor;
    private final StartupReadinessCoordinator readiness;

    public CacheWarmup(
            ThreadPoolTaskExecutor executor,
            StartupReadinessCoordinator readiness
    ) {
        this.executor = executor;
        this.readiness = readiness;
    }

    @EventListener
    public void startWarmup(ApplicationReadyEvent event) {
        readiness.beginWarmup();
        CompletableFuture.runAsync(this::loadCriticalCache, executor)
                .whenComplete((ignored, error) -> {
                    if (error == null) {
                        readiness.completeWarmup();
                    }
                    // On failure, remain refusing traffic and report the failure.
                });
    }

    private void loadCriticalCache() {
        // Load only the data required before serving traffic.
    }
}
~~~

Ví dụ minh họa flow, nhưng cần kiểm tra lifecycle timing của listener và readiness state trong Spring Boot version đang dùng. Nếu readiness đã tự chuyển ACCEPTING_TRAFFIC trước khi listener chạy, có một khoảng ngắn instance có thể nhận traffic. Với warm-up bắt buộc, hãy điều khiển state từ sớm hơn trong startup lifecycle hoặc dùng startup orchestration phù hợp, rồi kiểm thử race bằng integration test.

Không nuốt exception trong whenComplete. Ghi lỗi, phát alert hoặc chuyển state theo policy. Nếu warm-up có retry, giới hạn thời gian và số lần.

### 5.3. Retry và timeout

Dependency startup checks cần timeout rõ. Retry phải có backoff và giới hạn; không retry liên tục vô hạn làm startup không kết thúc. Phân biệt dependency bắt buộc với optional để chọn fail-fast, remain-not-ready hoặc degraded mode.

## 6. Kubernetes startup, liveness và readiness probes

Kubernetes cung cấp ba probe types:

- startupProbe: xác định container đã hoàn tất startup hay chưa;
- livenessProbe: xác định container có cần restart hay không;
- readinessProbe: xác định pod có nhận traffic không.

Ví dụ manifest:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 2
~~~

Đây là cấu hình minh họa. Cần điều chỉnh port, initial delays, period, timeout và failure threshold theo startup duration, traffic và failure detection budget. Startup probe cho phép ứng dụng khởi động lâu hơn mà chưa bị liveness probe restart.

### 6.1. Management port riêng

Nếu Actuator chạy trên management port riêng, Kubernetes probe phải trỏ tới port đó. Xác minh service/container network và security rules. Không dùng path đúng nhưng port không thể truy cập từ kubelet.

### 6.2. Probe semantics

Readiness failure thường loại pod khỏi Service endpoints nhưng không restart container. Liveness failure có thể restart container. Startup failure sau budget có thể khiến container bị restart. Chọn endpoint/group đúng cho từng loại để tránh readiness failure gây restart hoặc liveness failure do dependency ngoài.

## 7. Graceful shutdown và traffic draining

Startup state có chiều ngược lại khi application dừng. Trước khi process thoát, instance cần ngừng nhận request mới, cho request đang xử lý hoàn tất trong giới hạn và đóng resources.

Spring Boot hỗ trợ graceful shutdown cho embedded web servers theo cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Khi shutdown bắt đầu, readiness có thể chuyển sang REFUSING_TRAFFIC để instance được rút khỏi routing. Cần phối hợp termination grace period của Kubernetes với Spring lifecycle timeout và thời gian drain của load balancer.

### 7.1. Shutdown sequence

~~~mermaid
sequenceDiagram
    participant K8s as Kubernetes
    participant App as Spring Boot
    participant LB as Load balancer
    participant Requests
    K8s->>App: SIGTERM
    App->>App: Begin graceful shutdown
    App->>LB: Readiness becomes REFUSING_TRAFFIC
    LB->>LB: Remove instance from new routing
    Requests->>App: In-flight requests complete
    App->>App: Close beans and resources
    App-->>K8s: Process exits
~~~

Thời gian propagation của readiness change và load balancer endpoint update không bằng 0. Có thể cần preStop/drain strategy phù hợp nền tảng. Tránh sleep cố định tùy tiện nếu không hiểu termination sequence và grace period.

### 7.2. Background tasks khi shutdown

Task queue in-memory có thể mất task khi process bị terminate. Dùng durable messaging/job storage nếu task cần bảo đảm. Executor cần ngừng nhận task mới, xử lý task đang chạy trong timeout và ghi nhận task bị cancel/reject.

## 8. Observability cho startup state

Startup state cũng cần được quan sát, không chỉ được dùng làm probe.

Các tín hiệu hữu ích:

| Tín hiệu | Mục đích |
| --- | --- |
| Application startup duration | Phát hiện startup chậm |
| Warm-up duration | Đo thời gian chuẩn bị cache/index |
| Readiness transition timestamp | Biết instance mất bao lâu mới nhận traffic |
| Startup failure count | Theo dõi startup failures |
| Probe status | Theo dõi liveness/readiness theo thời gian |
| Logs theo lifecycle event | Điều tra bước startup/shutdown |
| Trace cho startup task | Phân tích dependency call trong warm-up |

### 8.1. Startup metrics

Spring Boot có thể ghi nhận application startup steps khi dùng cơ chế startup tracking phù hợp. Có thể xem startup information qua Actuator startup endpoint nếu được cấu hình/expose, nhưng không expose endpoint này công khai nếu không cần.

Custom warm-up nên có Observation với operation name ổn định như startup.cache-warmup và low-cardinality tags như cache.name hoặc outcome. Không gắn host/user/data IDs động vào metric tags.

### 8.2. Log state transitions

Ghi log khi bắt đầu warm-up, hoàn tất, thất bại, chuyển readiness và bắt đầu shutdown. Log cần có service identity và thời gian; nếu startup task có trace context thì correlation fields giúp liên kết dependency calls. Không log credentials hoặc toàn bộ configuration.

## 9. Bảo vệ và thiết kế dependency policy

Readiness có thể ảnh hưởng traffic toàn cluster. Cần xác định dependency nào thực sự bắt buộc:

- database bắt buộc cho mọi request chính;
- cache có thể fallback;
- analytics có thể buffer;
- optional API có thể degraded;
- broker có thể cần cho một nhóm use cases nhưng không phải tất cả.

Không biến mọi dependency failure thành global readiness failure. Nếu instance vẫn có thể phục vụ một phần traffic, cân nhắc degraded mode và routing policy. Nếu readiness chỉ có một bit cho nhiều endpoint khác nhau, cần bổ sung metrics/dependency health groups để vận hành có đủ thông tin.

### 9.1. Tránh readiness flapping

Nếu indicator chập chờn, pod liên tục chuyển ready/not-ready gây dao động traffic. Dùng timeout, hysteresis hoặc consecutive probe thresholds ở orchestrator phù hợp; cache health results nếu phù hợp; tránh dependency checks quá nhạy hoặc retry storm.

### 9.2. Không dùng liveness để restart do dependency outage

Liveness nên tập trung vào khả năng process tự phục hồi. External dependency outage thường cần retry/circuit breaker/degraded mode, không phải restart hàng loạt application instances.

## 10. Kiểm thử startup state

Cần test state transitions, event ordering, readiness endpoint và graceful shutdown behavior.

### 10.1. Test ApplicationAvailability

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StartupAvailabilityTest {
    @Autowired
    ApplicationAvailability availability;

    @Test
    void applicationBecomesReadyAfterContextStartup() {
        assertThat(availability.getReadinessState())
                .isEqualTo(ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Test này giả định không có startup coordinator cố ý giữ readiness ở REFUSING_TRAFFIC. Nếu ứng dụng có warm-up, test phải chờ/trigger completion theo contract thay vì giả định ready ngay sau context startup.

### 10.2. Test AvailabilityChangeEvent

Dùng ApplicationEventPublisher để phát REFUSING_TRAFFIC/ACCEPTING_TRAFFIC và xác minh ApplicationAvailability phản ánh state mới. Kiểm tra event source và ordering để tránh nhiều coordinator ghi đè state của nhau.

### 10.3. Test readiness endpoint

Gọi readiness health group trước, trong và sau warm-up. Xác minh status/HTTP response phản ánh state dự kiến. Test cần chạy với Actuator health probes enabled và group configuration giống production.

### 10.4. Test warm-up failure và timeout

Giả lập dependency chậm hoặc thất bại. Xác minh:
- readiness vẫn refusing khi công việc bắt buộc chưa hoàn tất;
- timeout/retry không vô hạn;
- failure được log/metric;
- process không tự chuyển liveness BROKEN nếu policy không yêu cầu;
- sau recovery, readiness chuyển accepting theo đúng điều kiện.

### 10.5. Test graceful shutdown

Dùng embedded server hoặc lifecycle test để xác minh readiness chuyển refusing khi shutdown bắt đầu, request đang chạy có thời gian hoàn tất và process đóng trong giới hạn. Không assert timing tuyệt đối quá chặt vì CI có jitter.

## 11. Troubleshooting startup state

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Pod nhận traffic trước warm-up | Readiness chuyển accepting quá sớm | Điều khiển state từ lifecycle boundary sớm hơn |
| Pod mãi NOT READY | Không publish ACCEPTING_TRAFFIC hoặc warm-up kẹt | Kiểm tra coordinator, timeout và logs |
| Startup probe thất bại | Budget thấp hoặc app startup chậm | Đo startup duration và tăng budget hợp lý |
| Liveness restart loop | Liveness phụ thuộc external dependency | Tách liveness khỏi readiness |
| ApplicationReadyEvent nhưng warm-up chưa xong | Warm-up chạy async fire-and-forget | Giữ readiness refusing tới completion |
| Startup task block quá lâu | Runner đồng bộ hoặc dependency timeout dài | Giới hạn timeout và chuyển work phù hợp |
| Readiness flapping | Dependency check chập chờn | Timeout, cache, thresholds và degraded mode |
| Readiness không đổi sau event | Event không được publish đúng context hoặc state bị ghi đè | Kiểm tra ApplicationEventPublisher và event ordering |
| Shutdown mất request | Traffic chưa drain hoặc grace period ngắn | Phối hợp readiness, LB drain và termination grace |
| Background task mất khi restart | Queue chỉ lưu trong memory | Dùng durable queue/job store |
| Startup metrics thiếu | Startup tracking chưa bật/expose | Kiểm tra Actuator startup support |
| Health endpoint đúng nhưng probe fail | Port/path/security/network sai | Kiểm tra kubelet reachability và HTTP mapping |

### 11.1. Quy trình điều tra

1. Xem application logs từ process start tới ApplicationReadyEvent.
2. Đọc ApplicationAvailability liveness/readiness state.
3. Kiểm tra readiness group và HTTP status.
4. Xem startup/warm-up Observation và duration.
5. Xác minh dependency timeout/retry và failure policy.
6. Kiểm tra Kubernetes startup/liveness/readiness probe path, port và thresholds.
7. Nếu pod restart, xác định probe nào thất bại.
8. Với shutdown, đối chiếu SIGTERM, readiness transition, load balancer drain và grace period.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Startup lifecycle được hiểu rõ | Event ordering được ghi nhận |
| Process và readiness tách biệt | Pod running chưa đồng nghĩa ready |
| ApplicationAvailability được kiểm tra | Liveness/Readiness states quan sát được |
| Warm-up có owner | Một coordinator quản lý transitions |
| Readiness giữ refusing tới khi sẵn sàng | Integration test xác minh |
| Dependency policy rõ | Mandatory/optional được phân loại |
| Startup probe có budget | Dựa trên startup duration thực |
| Liveness không phụ thuộc dependency ngoài | Không restart storm |
| Readiness endpoint được expose đúng | Path/port/security phù hợp |
| Warm-up có timeout/retry giới hạn | Không startup vô hạn |
| Shutdown graceful | Readiness refusing và traffic draining |
| Background tasks có durability | Không mất task quan trọng |
| Startup telemetry có ích | Duration, transition, error và logs |
| Tests đủ lifecycle | Ready, failure, timeout, shutdown |

## 13. Bài thực hành: giữ instance unready trong lúc warm-up

**Bối cảnh:** order-service chạy trên Kubernetes. Khi process khởi động, ứng dụng cần nạp reference data và warm cache trước khi nhận traffic. Hiện pod chuyển Ready ngay sau khi Spring context refresh, khiến request đầu tiên chậm hoặc lỗi.

**Nhiệm vụ:**

1. Bật Actuator health probes và xác minh readiness/liveness paths.
2. Đọc ApplicationAvailability trong startup lifecycle.
3. Xác định bước warm-up bắt buộc và optional.
4. Thiết kế StartupReadinessCoordinator sở hữu state transitions.
5. Giữ ReadinessState ở REFUSING_TRAFFIC trong thời gian warm-up.
6. Chỉ chuyển ACCEPTING_TRAFFIC sau khi critical warm-up hoàn tất.
7. Đặt timeout/retry có giới hạn và ghi nhận warm-up failure.
8. Giữ LivenessState CORRECT khi dependency tạm thời lỗi nhưng process vẫn có thể phục hồi.
9. Cấu hình Kubernetes startupProbe/readinessProbe/livenessProbe theo port/path thật.
10. Kiểm tra readiness transition và traffic routing qua integration test.
11. Kiểm tra graceful shutdown chuyển về REFUSING_TRAFFIC và drain requests.
12. Tạo dashboard/log view cho startup duration, warm-up duration và readiness transitions.

**Kết quả mong đợi:** startup state transitions rõ ràng, readiness không mở quá sớm, probes phù hợp, warm-up có timeout, graceful shutdown và test lifecycle.

## 14. Ghi nhớ

Startup state mô tả việc application chuyển từ process vừa chạy tới instance sẵn sàng nhận traffic. Spring Boot cung cấp ApplicationAvailability cùng LivenessState và ReadinessState để biểu diễn tình trạng này. ApplicationStartedEvent và ApplicationReadyEvent đánh dấu các mốc lifecycle khác nhau; runner đồng bộ có thể kéo dài startup, còn warm-up bất đồng bộ cần readiness policy riêng.

Giữ readiness ở REFUSING_TRAFFIC cho tới khi công việc bắt buộc hoàn tất; dùng liveness cho tình trạng process có thể tiếp tục chạy. Kubernetes startupProbe bảo vệ giai đoạn khởi động, readinessProbe điều khiển traffic và livenessProbe quyết định restart. Khi shutdown, chuyển sang refusing traffic và phối hợp draining/grace period. Quan sát startup duration, warm-up, state transitions và failures bằng metrics/logs/traces; kiểm thử cả startup failure, timeout, readiness và shutdown.

**Tài liệu tham khảo:**
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)

