# Dừng ứng dụng an toàn khi có thao tác cấp phát đang chạy

Service broker có thể đang xử lý nhiều yêu cầu provision, update, bind hoặc deprovision khi phiên bản ứng dụng cần được triển khai lại, scale down hoặc dừng vì sự cố hạ tầng. Nếu process bị kết thúc đột ngột, request đang xử lý có thể mất response, worker có thể bỏ dở bước gọi provider và trạng thái trong database có thể không phản ánh đúng tài nguyên thật.

Graceful shutdown (dừng ứng dụng có kiểm soát) giúp broker ngừng nhận công việc mới, hoàn tất hoặc bàn giao công việc đang chạy, đóng kết nối theo đúng thứ tự và cho phép instance mới tiếp tục phục vụ. Với SPRING_CLOUD_SERVICE_BROKER, cần phân biệt hai việc: drain các HTTP request đang mở và drain các operation bất đồng bộ đã được chấp nhận. HTTP request có thể kết thúc trong vài giây, trong khi một thao tác tạo database ở provider có thể kéo dài nhiều phút. Dừng web server êm ái không tự động bảo đảm worker operation được bảo toàn.

## 1. Vì sao cần graceful shutdown?

Một broker thường chạy nhiều replica sau load balancer hoặc trong Kubernetes/Cloud Foundry. Khi deploy phiên bản mới, nền tảng có thể thay thế một replica trong khi các replica khác vẫn phục vụ. Replica sắp dừng cần rời khỏi traffic và bàn giao công việc đang sở hữu.

Nếu process bị kill ngay:

- Nền tảng có thể nhận timeout dù provider đã tạo tài nguyên thành công.
- Broker có thể đã gửi lệnh đến provider nhưng chưa lưu provider resource ID hoặc job ID.
- Worker có thể đang giữ lease khiến operation bị kẹt cho đến khi lease hết hạn.
- Message có thể bị mất nếu queue acknowledgement diễn ra trước khi kết quả được lưu bền vững.
- Database connection pool bị đóng trong khi transaction hoặc callback còn đang dùng.
- Replica mới có thể nhận retry và tạo tài nguyên trùng nếu operation không idempotent.
- Nền tảng có thể tiếp tục gọi replica đã bắt đầu shutdown nếu readiness/routing chưa cập nhật.

Graceful shutdown không thể biến một lời gọi provider không thể rollback thành transaction nguyên tử. Mục tiêu là giữ operation state bền vững, tránh nhận thêm việc khi đang thoát và bảo đảm công việc chưa hoàn tất có thể được replica khác tiếp tục.

## 2. Phân biệt HTTP request và background operation

Đây là ranh giới quan trọng nhất khi thiết kế shutdown cho broker.

| Loại công việc | Thời gian thường gặp | Cách bảo toàn khi shutdown |
|---|---|---|
| GET catalog | Ngắn | Hoàn tất request đang mở hoặc đóng kết nối |
| Request provision đồng bộ | Có thể kéo dài | Drain trong giới hạn; nếu không thể hoàn tất thì phải có recovery/idempotency |
| Request provision trả 202 | Ngắn ở HTTP; operation kéo dài ở nền | Lưu operation bền vững trước response, worker có thể bàn giao |
| Poll provider job | Ngắn mỗi lần gọi | Lưu provider job ID, trạng thái và next_poll_at |
| Update/deprovision async | Có thể kéo dài nhiều phút | Persist state, lease và checkpoint; replica khác tiếp tục |
| Queue consumer | Liên tục | Ngừng nhận message mới, xử lý hoặc trả message chưa hoàn tất về queue |

Khi broker trả HTTP 202 Accepted, nền tảng đã nhận operation ID và có thể polling last_operation sau đó. Việc HTTP request đã kết thúc không có nghĩa operation đã hoàn tất. Operation phải được lưu trong database hoặc kho bền vững trước khi trả 202.

Không nên giữ một HTTP request mở trong toàn bộ thời gian provider tạo tài nguyên nếu OSB request đã chấp nhận xử lý bất đồng bộ. Hãy tách tiếp nhận operation khỏi worker thực hiện operation.

## 3. Trình tự shutdown tổng thể

Một quy trình shutdown an toàn có thể gồm các bước:

1. Nhận tín hiệu dừng hoặc lệnh drain từ nền tảng triển khai.
2. Đánh dấu replica đang ở trạng thái DRAINING.
3. Chuyển readiness thành không sẵn sàng để load balancer ngừng gửi traffic mới.
4. Từ chối có kiểm soát các mutation request mới nếu chúng vẫn đến replica trong thời gian routing hội tụ.
5. Cho các HTTP request đã được chấp nhận hoàn tất trong thời hạn cho phép.
6. Ngừng scheduler/poller và không claim operation mới.
7. Chờ worker đang chạy đến checkpoint an toàn hoặc lưu tiến độ và nhả lease.
8. Trả message chưa xử lý về queue hoặc để visibility timeout/lease hết hạn theo cơ chế đã thiết kế.
9. Đóng kết nối provider, queue và database theo thứ tự phụ thuộc.
10. Kết thúc process trước khi termination grace period hết hạn.

~~~mermaid
flowchart TD
    A[Nhận SIGTERM hoặc lệnh drain] --> B[Đánh dấu replica DRAINING]
    B --> C[Readiness = DOWN]
    C --> D[Ngừng nhận mutation mới]
    D --> E[Drain HTTP request đang mở]
    E --> F[Ngừng claim operation và message mới]
    F --> G[Hoàn tất hoặc checkpoint worker đang chạy]
    G --> H[Nhả lease / trả message chưa xử lý]
    H --> I[Đóng provider, queue và database clients]
    I --> J[Process thoát trước deadline]
~~~

Thứ tự chi tiết phụ thuộc kiến trúc. Ví dụ, nếu worker cần database để checkpoint, không được đóng connection pool trước khi worker hoàn tất bàn giao.

## 4. Trạng thái DRAINING và admission control

Chỉ đổi readiness thành DOWN có thể chưa đủ. Load balancer và service discovery cần thời gian cập nhật; trong khoảng đó replica vẫn có thể nhận request mới. Broker nên có một cờ lifecycle nội bộ để biết replica đã bắt đầu drain.

Một mô hình đơn giản:

| Trạng thái | Readiness | Request mới | Worker claim |
|---|---|---|---|
| STARTING | DOWN | Chưa nhận | Không |
| READY | UP | Nhận theo policy | Có |
| DRAINING | DOWN | Từ chối mutation mới hoặc chỉ cho phép request được chọn | Không claim mới |
| STOPPED | DOWN | Không nhận | Không |

Trong DRAINING, broker cần quyết định rõ endpoint nào còn phục vụ. Có thể tiếp tục trả health/liveness, metric và một số GET read-only nếu chúng an toàn. Các thao tác thay đổi trạng thái như provision, update, bind, unbind và deprovision nên được chuyển sang replica khác hoặc trả lỗi tạm thời phù hợp nếu request đến sau khi drain bắt đầu.

Nếu request bị từ chối vì replica đang drain, dùng status tạm thời như 503 Service Unavailable và không tạo side effect. Không trả 202 nếu operation chưa được ghi bền vững. Nền tảng có thể retry request đến replica khác; do đó handler và persistence vẫn phải idempotent.

## 5. Graceful shutdown trong Spring Boot

Spring Boot hỗ trợ graceful shutdown cho embedded web server. Khi bật, server ngừng nhận request mới ở mức connector và cho các request đang hoạt động thời gian hoàn tất theo timeout của lifecycle phase.

Ví dụ cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Giá trị 45 giây chỉ là ví dụ. Cần chọn timeout dựa trên thời gian drain thực tế và termination grace period của nền tảng. Nếu ứng dụng dùng Spring Boot phiên bản cũ hoặc server/container khác, cần xác minh hỗ trợ và hành vi của phiên bản đang chạy.

Graceful shutdown của web server chỉ quản lý request đang mở. Nó không tự biết operation provision nào đã được ghi, worker nào đang giữ lease hoặc queue message nào cần trả lại. Phần worker lifecycle phải được thiết kế riêng.

## 6. Readiness và liveness trong Spring Boot Actuator

Readiness trả lời câu hỏi: replica có nên nhận traffic nghiệp vụ mới không? Liveness trả lời câu hỏi: process còn hoạt động và không bị kẹt đến mức cần restart không?

Khi bắt đầu drain:

- Readiness phải chuyển DOWN để replica bị loại khỏi traffic.
- Liveness thường vẫn UP trong thời gian drain; nếu liveness chuyển DOWN ngay, orchestrator có thể restart/kill process trước khi drain xong.
- Khi shutdown hoàn tất, process thoát bình thường.

Spring Boot Actuator có thể cung cấp readiness/liveness health groups khi bật probe support. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Ứng dụng có thể tích hợp trạng thái DRAINING vào readiness indicator hoặc health contributor. Cần bảo đảm endpoint health được expose và probe path phù hợp với nền tảng. Không nên để một readiness check phụ thuộc provider API đang tạm lỗi nếu điều đó khiến tất cả replica đồng loạt bị loại khỏi traffic mà broker vẫn có thể xử lý các request khác.

## 7. Quản lý worker bằng lifecycle rõ ràng

Worker xử lý operation async nên có vòng đời độc lập với HTTP server. Khi shutdown bắt đầu, worker cần:

- Ngừng nhận operation mới.
- Ngừng poll hoặc claim queue message mới.
- Cho operation đang chạy đến checkpoint an toàn.
- Persist trạng thái hiện tại và next action.
- Nhả lease hoặc lock có thời hạn.
- Không acknowledge message trước khi kết quả đã được ghi bền vững.
- Đóng client provider sau khi không còn request đang dùng.

Có thể dùng Spring SmartLifecycle để điều phối component bắt đầu và dừng theo phase. Ví dụ minh họa:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class OperationWorkerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);
    private final OperationWorker worker;

    public OperationWorkerLifecycle(OperationWorker worker) {
        this.worker = worker;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            worker.startClaiming();
        }
    }

    @Override
    public void stop(Runnable callback) {
        running.set(false);
        worker.stopClaimingAndDrain()
                .doFinally(signal -> callback.run())
                .subscribe();
    }

    @Override
    public void stop() {
        running.set(false);
        worker.stopClaiming();
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là skeleton để giải thích lifecycle callback, không phải worker production hoàn chỉnh. Implementation thực tế cần timeout cho drain, xử lý lỗi, giới hạn số operation đang chạy và bảo đảm callback chỉ được gọi sau khi worker đã bàn giao hoặc kết thúc. Không được gọi subscribe tùy tiện nếu worker không quản lý subscription và cancellation một cách rõ ràng.

## 8. Ngừng nhận công việc mới trước khi chờ công việc cũ

Một lỗi phổ biến là chỉ đợi executor kết thúc nhưng scheduler vẫn tiếp tục gửi job mới vào executor. Điều này có thể khiến shutdown không bao giờ hoàn tất.

Nên tách hai thao tác:

1. Stop intake: dừng scheduler, queue listener hoặc poller tạo công việc mới.
2. Drain active work: đợi các operation đã claim hoàn tất hoặc checkpoint.

Ví dụ pseudocode:

~~~java
public Mono<Void> stopClaimingAndDrain() {
    acceptingNewJobs.set(false);
    scheduler.pause();
    queueConsumer.pause();

    return activeOperations.awaitCheckpointOrCompletion(drainTimeout)
            .then(leaseManager.releaseOwnedLeases())
            .then(queueConsumer.stop());
}
~~~

Nếu worker có nhiều loại công việc, có thể dừng claim theo thứ tự: mutation job trước, reconciliation job sau hoặc ngược lại tùy policy. Không để job repair/reconciliation quan trọng bị bỏ mặc nếu nó đang xử lý một resource ở trạng thái không xác định.

## 9. Operation state phải được lưu trước khi thực hiện provider call

Một operation async cần có record bền vững trước khi broker trả 202. Ví dụ:

~~~text
operation_id
service_instance_id
operation_type
state = ACCEPTED
request_fingerprint
provider_job_id = null
attempt_count = 0
next_attempt_at
lease_owner = null
lease_until = null
created_at
updated_at
~~~

Khi worker claim operation, nó cập nhật lease và trạng thái thực thi. Khi provider trả job ID, broker lưu job ID ngay. Khi provider hoàn tất, broker xác minh resource và chuyển state sang terminal.

Nếu process dừng, replica khác đọc record này và tiếp tục. Không lưu trạng thái operation chỉ trong memory, local queue hoặc Reactor Context vì những dữ liệu đó mất khi process thoát.

## 10. Checkpoint và bàn giao operation

Checkpoint là điểm mà worker đã lưu đủ thông tin để một worker khác tiếp tục mà không phải đoán bước trước đã thành công hay chưa.

Ví dụ một workflow provision:

| Bước | Dữ liệu cần lưu trước khi có thể bàn giao |
|---|---|
| Đã nhận request | broker operation ID, fingerprint, instance ID, normalized parameters |
| Đã gửi lệnh provider | idempotency key, provider account/region, request reference nếu có |
| Provider đã nhận job | provider job ID và trạng thái provider |
| Provider tạo resource | provider resource ID, metadata và version |
| Resource sẵn sàng | observed state, endpoint/reference cần trả cho nền tảng |
| Hoàn tất | terminal state, safe description, completed_at |

Nếu shutdown xảy ra giữa hai checkpoint, worker mới phải xác định được bước nào đã hoàn tất. Ví dụ, nếu provider đã tạo database nhưng broker chưa lưu response, worker cần truy vấn provider bằng idempotency key hoặc broker tag trước khi gửi lệnh tạo lại.

Checkpoint không nhất thiết lưu toàn bộ response provider. Chỉ lưu các dữ liệu nghiệp vụ đủ để tiếp tục và audit, đồng thời lọc secret.

## 11. Lease, lock và tránh hai worker cùng xử lý

Trong môi trường nhiều replica, operation đang chạy có thể được worker A giữ lease. Khi A shutdown, worker B chỉ nên claim sau khi A đã nhả lease hoặc lease hết hạn.

Một lease có thể gồm:

- operation ID.
- worker/replica ID.
- lease expiry time.
- optimistic version.
- heartbeat/last renewed time.

Quy tắc:

- Lease có thời hạn; không dùng lock vĩnh viễn.
- Worker gia hạn lease khi vẫn hoạt động và còn quyền sở hữu.
- Worker chỉ cập nhật operation nếu lease owner và version còn đúng.
- Khi shutdown, worker nhả lease sau checkpoint.
- Nếu process bị kill -9, lease tự hết hạn để worker khác tiếp quản.
- Worker mới phải kiểm tra provider state trước khi lặp side effect.

Không giải phóng lease ngay khi nhận SIGTERM nếu worker vẫn đang gọi provider và chưa lưu kết quả. Làm vậy có thể khiến replica mới thực hiện cùng operation đồng thời.

## 12. Queue consumer và message acknowledgement

Nếu broker dùng RabbitMQ, Kafka hoặc một queue khác, cần xác định thời điểm message được acknowledge/commit offset.

Nguyên tắc tổng quát:

- Chỉ acknowledge sau khi operation state hoặc checkpoint đã được lưu bền vững.
- Khi shutdown, pause intake trước khi chờ message đang xử lý.
- Message chưa bắt đầu có thể được trả lại queue hoặc không commit offset.
- Message đang xử lý phải hoàn tất checkpoint hoặc được redeliver sau timeout.
- Consumer phải idempotent vì redelivery là hành vi bình thường.
- Dead-letter queue phải giữ message lỗi không thể retry theo policy.

Với Kafka, việc commit offset và ghi kết quả database là hai hệ thống riêng trừ khi dùng transaction/integration đặc biệt. Cần thiết kế inbox/deduplication để xử lý lại message an toàn. Với RabbitMQ, manual acknowledgement và requeue có thể giúp bàn giao, nhưng message redelivery vẫn yêu cầu handler idempotent.

Không dùng memory queue làm nơi duy nhất lưu operation. Khi pod bị xóa, mọi task chưa được persist sẽ mất.

## 13. Xử lý request đồng bộ đang chạy khi nhận shutdown

Provision đồng bộ có thể đang chờ provider trong khi SIGTERM đến. Có ba lựa chọn:

1. Chờ request hoàn tất trong giới hạn shutdown timeout.
2. Nếu request có thể chuyển thành async theo hợp đồng đã thỏa thuận, persist operation và trả response phù hợp trước khi drain; không thể tự đổi semantics sau khi request đã bắt đầu nếu nền tảng không hỗ trợ.
3. Nếu không thể hoàn tất trước deadline, đóng kết nối có kiểm soát và dựa vào idempotency/reconciliation khi nền tảng retry.

Không được trả success chỉ để kết thúc request nhanh nếu provider chưa hoàn tất. Cũng không nên giữ process vô thời hạn vì một provider call bị treo.

Đặt timeout cho HTTP client provider nhỏ hơn thời gian drain còn lại, dùng cancellation đúng cách và lưu trạng thái không xác định nếu không biết provider đã thực hiện side effect hay chưa.

## 14. Timeout và thứ tự shutdown

Tổng thời gian shutdown phải được chia thành ngân sách:

| Giai đoạn | Ví dụ ngân sách |
|---|---:|
| Đánh dấu DRAINING và cập nhật readiness | 3 giây |
| Chờ routing/load balancer loại replica | 5 giây |
| Drain HTTP request | 15 giây |
| Worker checkpoint và nhả lease | 20 giây |
| Đóng queue/provider/database clients | 5 giây |
| Dự phòng | 7 giây |
| Tổng ví dụ | 55 giây |

Các con số chỉ để minh họa. Thời gian thực tế phải phù hợp với timeout của provider, số request đang mở và termination grace period của nền tảng. Nếu từng phase có timeout riêng, tổng thời gian cần nhỏ hơn giới hạn process termination.

Đóng database pool quá sớm làm worker không thể checkpoint. Đóng provider client trước khi request đang chạy kết thúc có thể tạo trạng thái không xác định. Hãy xác định dependency graph và thứ tự stop component thay vì dựa vào thứ tự ngẫu nhiên.

## 15. Cấu hình Kubernetes cho graceful termination

Kubernetes gửi tín hiệu SIGTERM đến process trong container khi Pod bị terminate, sau đó chờ hết terminationGracePeriodSeconds trước khi force kill. Hook preStop, nếu cấu hình, chạy trong khoảng grace period và kết thúc trước khi SIGTERM được gửi. Vì vậy thời gian hook cũng tiêu thụ ngân sách shutdown.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: service-broker
  template:
    metadata:
      labels:
        app: service-broker
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: broker
          image: example/service-broker:1.4.0
          ports:
            - name: http
              containerPort: 8080
          lifecycle:
            preStop:
              httpGet:
                path: /internal/lifecycle/drain
                port: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
~~~

Đây là cấu hình minh họa. Endpoint drain phải được bảo vệ, chỉ cho phép kubelet hoặc mạng quản trị gọi. Nếu dùng preStop HTTP hook, ứng dụng nên đánh dấu DRAINING ngay khi nhận request và trả kết quả sau khi trạng thái đã được kích hoạt; không cần chờ toàn bộ operation provider kéo dài trong hook.

terminationGracePeriodSeconds phải lớn hơn tổng thời gian preStop và shutdown phases. Nếu hết grace period, kubelet có thể gửi SIGKILL và process không có cơ hội chạy cleanup.

## 16. Readiness propagation và Pod termination

Khi Pod bắt đầu terminate, Kubernetes cập nhật EndpointSlice và các proxy/load balancer dần ngừng định tuyến traffic mới đến endpoint đó. Việc cập nhật không nhất thiết tức thời ở mọi thành phần.

Vì vậy:

- Đánh dấu readiness DOWN trước khi bắt đầu drain dài.
- Có thể dùng preStop để kích hoạt drain sớm.
- Admission control trong ứng dụng vẫn cần bảo vệ khoảng thời gian routing chưa hội tụ.
- Không tắt liveness ngay khi drain bắt đầu.
- Đặt maxUnavailable và maxSurge phù hợp trong rolling update để luôn có đủ replica phục vụ.
- Không đặt readiness phụ thuộc worker backlog bằng 0 nếu backlog không thể drain hết trong thời gian rollout; cần phân biệt khả năng nhận request mới với việc còn operation nền.

## 17. Triển khai trên Cloud Foundry

Trên Cloud Foundry, ứng dụng chạy trong container do Diego quản lý. Khi deploy, restart hoặc scale down, platform sẽ thay thế hoặc dừng instance theo lifecycle của foundation. Chi tiết thời gian stop và routing drain phụ thuộc cấu hình/phiên bản foundation.

Broker nên:

- Bật graceful shutdown của Spring Boot embedded server.
- Có readiness/admission state nếu tích hợp health check hoặc router phù hợp.
- Không phụ thuộc vào local disk hoặc memory để giữ operation.
- Persist provider job ID và operation state vào database dùng chung.
- Dùng queue/lease để replica mới tiếp quản job.
- Kiểm tra stop timeout và hành vi route drain của foundation đang chạy.
- Triển khai rolling update với đủ capacity để replica còn lại tiếp tục nhận request.

Không giả định Cloud Foundry tự chờ mọi provider operation hoàn tất trước khi dừng app. Một operation đã được chấp nhận phải có khả năng tiếp tục từ state store dù process cũ đã kết thúc.

## 18. Không để deployment đồng thời làm mất operation

Trong rolling deployment, replica cũ và replica mới có thể cùng tồn tại. Cả hai phải đọc/ghi cùng schema và operation format trong khoảng chuyển tiếp.

Các yêu cầu:

- Schema migration tương thích ngược trong giai đoạn rollout.
- Message payload có version hoặc backward-compatible.
- Worker mới có thể đọc operation được tạo bởi phiên bản cũ.
- Worker cũ không ghi đè field hoặc state mới mà nó không hiểu.
- Feature flag không thay đổi semantics giữa hai replica đang chạy.
- Lease/optimistic locking bảo vệ cập nhật cạnh tranh.
- Không chạy migration phá hủy trong lúc replica cũ còn hoạt động.

Nếu đổi operation state machine, hãy dùng expand-migrate-contract: thêm field mới, deploy code đọc cả hai dạng, backfill, chuyển producer/consumer rồi mới bỏ field cũ ở release sau.

## 19. Idempotency và crash recovery

Graceful shutdown giảm xác suất mất việc nhưng không loại bỏ crash, node failure hoặc SIGKILL. Vì vậy mọi operation quan trọng vẫn cần idempotency.

Một request provision nên có fingerprint ổn định từ instance ID, service ID, plan ID và parameters đã canonicalize. Khi retry:

- Nếu operation đã thành công, trả kết quả đã lưu theo OSB contract.
- Nếu operation đang chạy, trả cùng operation ID.
- Nếu provider đã nhận job nhưng broker chưa lưu job ID, tra cứu theo idempotency key hoặc broker tag trước khi gửi lại.
- Nếu trạng thái không xác định, chuyển sang RECONCILING thay vì tạo resource mới ngay.

Không tạo idempotency key mới mỗi lần worker restart. Key phải gắn với operation nghiệp vụ, không gắn với process hoặc attempt.

## 20. Shutdown trong khi deprovision hoặc unbind

Không chỉ provision mới cần được bảo vệ. Deprovision và unbind cũng có side effect quan trọng:

- Unbind có thể đang thu hồi database user hoặc token.
- Deprovision có thể đang xóa database, network hoặc backup policy.
- Nếu process dừng giữa chừng, broker cần biết tài nguyên nào đã bị xóa và bước nào còn lại.

Worker phải checkpoint từng bước hoặc dùng provider operation ID để tiếp tục polling. Không đánh dấu binding REVOKED hoặc instance DEPROVISIONED trước khi provider xác nhận hoặc reconciliation chứng minh kết quả.

Nếu shutdown xảy ra khi provider đã xóa tài nguyên nhưng broker chưa commit, worker mới cần truy vấn resource/job state. Xử lý DELETE phải idempotent để lần chạy tiếp theo không gây lỗi nghiêm trọng khi resource đã biến mất.

## 21. Ví dụ admission gate trong Spring

Một gate đơn giản có thể chặn mutation mới khi ứng dụng đang drain:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class BrokerAdmissionGate {

    private final AtomicBoolean draining = new AtomicBoolean(false);

    public void beginDrain() {
        draining.set(true);
    }

    public void requireAcceptingMutations() {
        if (draining.get()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Broker instance is draining");
        }
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

Gate cần được gọi ở ranh giới request mutation trước khi tạo side effect. Nếu dùng reactive stack, không block event loop. Nếu có nhiều loại endpoint, chỉ chặn mutation; health, metrics và các endpoint vận hành được bảo vệ có thể vẫn hoạt động trong drain.

Trong môi trường nhiều replica, gate này chỉ áp dụng cho một process. Nó không thay thế idempotency, database lock hoặc cluster-wide admission control.

## 22. Ví dụ kiểm tra operation worker đã drain

Worker có thể theo dõi số operation đang được claim và đợi chúng đến checkpoint:

~~~java
public interface ActiveOperationRegistry {
    int activeCount();

    Mono<Void> awaitSafeCheckpoint(Duration timeout);
}

public Mono<Void> drainWorker() {
    stopClaimingNewOperations();
    pausePollers();

    return activeOperationRegistry.awaitSafeCheckpoint(Duration.ofSeconds(20))
            .onErrorResume(TimeoutException.class, error ->
                    checkpointAndReleaseLeases());
}
~~~

Đây là pseudocode. Khi timeout, chỉ được release lease sau khi đã persist checkpoint và bảo đảm worker cũ không tiếp tục side effect. Nếu không thể xác nhận an toàn, để lease hết hạn tự nhiên và worker mới chỉ claim sau khi hết hạn. Không xóa lease cưỡng bức trong khi request provider vẫn có thể hoàn tất ở process cũ.

## 23. Xử lý timeout khi shutdown không đủ thời gian

Một provider call có thể kéo dài hơn termination grace period. Không thể bảo đảm process chờ vô hạn. Cần thiết kế timeout và recovery:

- Đặt provider HTTP timeout hữu hạn.
- Dùng provider async job nếu API hỗ trợ.
- Persist operation và provider reference trước khi chờ lâu.
- Dùng cancellation khi client hỗ trợ, nhưng không giả định cancel HTTP request sẽ hủy side effect ở provider.
- Khi timeout, lưu state UNKNOWN hoặc RECONCILING.
- Nhả lease chỉ sau khi đã lưu trạng thái không xác định và worker cũ không còn quyền cập nhật.
- Replica mới truy vấn provider để xác định kết quả.
- Phát cảnh báo nếu operation không thể được đối soát.

Nếu provider đã tiếp nhận lệnh, việc đóng socket không đồng nghĩa lệnh bị hủy. Broker phải xem kết quả là không xác định cho đến khi provider xác nhận.

## 24. Quan sát graceful shutdown

Log và metric cần cho biết replica đang ở giai đoạn nào:

- Thời điểm nhận SIGTERM hoặc drain request.
- Thời điểm readiness chuyển DOWN.
- Số HTTP request còn mở.
- Số worker operation đang active.
- Số message chưa xử lý và queue lag.
- Số lease do replica sở hữu.
- Số operation đã checkpoint, nhả lease hoặc hết thời gian drain.
- Thời gian đóng provider/database clients.
- Exit code và thời gian shutdown thực tế.

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| broker_shutdown_total | Số lần shutdown theo kết quả |
| broker_shutdown_duration_seconds | Thời gian drain và đóng process |
| broker_inflight_http_requests | Request đang mở |
| broker_active_operations | Operation worker đang xử lý |
| broker_owned_leases | Lease đang do replica giữ |
| broker_operation_recovery_total | Operation được replica mới tiếp quản |
| broker_shutdown_forced_total | Số lần process bị force kill hoặc drain timeout |

Không đưa tenant ID, instance ID hoặc secret vào metric label vì cardinality và bảo mật. Có thể dùng correlation ID trong log có kiểm soát để truy vết từng operation.

## 25. Kiểm thử graceful shutdown

Kiểm thử cần chứng minh replica dừng mà operation không bị mất:

| Tình huống | Kết quả mong đợi |
|---|---|
| Shutdown khi không có request | Readiness DOWN, process thoát bình thường |
| Shutdown khi GET catalog đang mở | Request hoàn tất trong timeout |
| Shutdown khi mutation mới đến sau DRAINING | Request không tạo side effect và được chuyển sang replica khác/retry |
| Shutdown khi provision async đang chạy | Operation record vẫn tồn tại và replica mới tiếp tục |
| Shutdown khi provider call đang chờ | Kết quả được checkpoint hoặc chuyển RECONCILING |
| Shutdown khi worker giữ lease | Lease được nhả an toàn hoặc hết hạn |
| Shutdown khi queue message chưa bắt đầu | Message vẫn có thể được xử lý lại |
| Shutdown khi message đang xử lý | Không mất message; redelivery không tạo side effect trùng |
| SIGKILL trước khi drain xong | Lease expiry và idempotency phục hồi operation |
| Rolling deployment nhiều replica | Replica mới đọc được operation do replica cũ tạo |
| Shutdown khi unbind/deprovision | Provider state được đối soát, không báo hoàn tất giả |
| Hết termination grace period | Có metric/alert và recovery path cho operation chưa xong |

Có thể dùng integration test với Testcontainers cho database/queue, provider stub có khả năng delay và test process lifecycle. Để kiểm tra tín hiệu SIGTERM thực tế, chạy ứng dụng trong container test và gửi tín hiệu dừng, sau đó xác minh database/queue vẫn chứa đủ operation state.

## 26. Checklist triển khai

- [ ] Bật graceful shutdown cho embedded server và đặt timeout phù hợp.
- [ ] Readiness chuyển DOWN khi bắt đầu drain; liveness không bị tắt quá sớm.
- [ ] Có admission gate để từ chối mutation mới trên replica đang drain.
- [ ] Operation async được persist trước response 202.
- [ ] Worker dừng claim job mới trước khi drain job đang active.
- [ ] Có checkpoint, lease expiry và optimistic locking.
- [ ] Queue consumer pause intake và acknowledgement sau khi persist kết quả.
- [ ] Provider client timeout nhỏ hơn ngân sách shutdown còn lại.
- [ ] Không giả định đóng HTTP connection sẽ hủy provider side effect.
- [ ] Database/secret/queue clients chỉ đóng sau khi worker đã bàn giao.
- [ ] Kubernetes terminationGracePeriodSeconds đủ lớn cho preStop và shutdown phases.
- [ ] Cloud Foundry stop/routing behavior đã được xác minh trên foundation thực tế.
- [ ] Schema và message tương thích trong rolling deployment.
- [ ] Có metric cho in-flight request, active operation, lease và forced shutdown.
- [ ] Đã kiểm thử restart, SIGTERM, SIGKILL, provider timeout và redelivery.

## 27. Trình tự triển khai cho service broker

Khi xây dựng graceful shutdown cho SPRING_CLOUD_SERVICE_BROKER, có thể thực hiện theo trình tự:

1. Tách HTTP request lifecycle khỏi operation worker lifecycle.
2. Bảo đảm provision/update/deprovision async được lưu bền vững trước khi trả 202.
3. Thêm trạng thái DRAINING, readiness indicator và admission gate.
4. Bật Spring Boot graceful shutdown và cấu hình timeout theo ngân sách thực tế.
5. Thiết kế worker stop-intake, checkpoint, lease release và queue acknowledgement.
6. Bảo đảm provider calls có timeout, idempotency key và recovery cho kết quả không xác định.
7. Cấu hình Kubernetes preStop/termination grace period hoặc xác minh stop behavior của Cloud Foundry.
8. Kiểm tra tương thích schema/message trong rolling deployment.
9. Thêm metric/log và cảnh báo cho drain timeout, forced kill và operation recovery.
10. Diễn tập shutdown khi provision, update, unbind và deprovision đang chạy.

Graceful shutdown chỉ an toàn khi broker có thể rời khỏi traffic mà không bỏ mất trạng thái nghiệp vụ. Spring Boot giúp drain HTTP request; readiness và admission control ngăn nhận việc mới; operation store, worker lease, checkpoint và idempotency giúp replica khác tiếp tục công việc đã được chấp nhận. Kết hợp các cơ chế này giúp deployment và scale down không biến một thao tác cấp phát đang chạy thành tài nguyên mồ côi hoặc operation bị treo.
