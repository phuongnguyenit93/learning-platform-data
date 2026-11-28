# Ranh giới giữa event flow trong ứng dụng và cơ chế tác vụ bền vững

Một service broker thường kết hợp hai kiểu xử lý. Bên trong một tiến trình Spring, các thành phần có thể phát event để thông báo thay đổi, phối hợp bước xử lý hoặc nối các publisher bằng Reactor. Ở cấp độ vòng đời dịch vụ, broker lại phải thực hiện những công việc kéo dài như provision database, thay đổi plan, tạo binding hay deprovision tài nguyên. Những công việc này cần tồn tại qua restart, retry và nhiều replica.

Hai kiểu xử lý có mục đích khác nhau. Event flow trong ứng dụng giúp các thành phần giao tiếp trong phạm vi runtime; durable task/workflow ghi nhận một yêu cầu nghiệp vụ để có thể tiếp tục sau khi tiến trình dừng. Nếu dùng một Spring application event hoặc một Reactor sink trong bộ nhớ làm hàng đợi duy nhất cho provision, broker có thể trả lời platform rằng operation đã được nhận nhưng mất công việc khi process crash.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, ranh giới này đặc biệt quan trọng vì Open Service Broker API (OSB API) quy định vòng đời provision, update, bind, unbind và deprovision; Spring Cloud Open Service Broker (SCOSB) cung cấp service abstraction và request/response model; còn ứng dụng broker chịu trách nhiệm lưu trạng thái và điều phối tác vụ tới provider.

Bài học này phân biệt event, command và durable operation; giải thích giới hạn của Spring ApplicationEvent và Reactor; thiết kế transactional outbox, queue và worker; tổ chức state machine, retry, idempotency và recovery; đồng thời chỉ ra cách kết hợp các cơ chế trong một broker Spring.

## 1. Hai loại flow giải quyết hai bài toán

**Event flow trong ứng dụng** là luồng thông báo hoặc phối hợp giữa các thành phần đang chạy trong một ứng dụng. Ví dụ, sau khi một binding được lưu thành công, service có thể phát event để cập nhật metric hoặc làm mới cache. Các thành phần tham gia thường nằm trong cùng process hoặc cùng runtime.

**Durable task** là một yêu cầu nghiệp vụ đã được ghi nhận bền vững và phải được xử lý cho đến khi đạt kết quả cuối cùng hoặc được đưa vào trạng thái cần can thiệp. Ví dụ, yêu cầu provision một database phải tiếp tục được xử lý kể cả khi pod broker bị restart hoặc queue consumer tạm thời không hoạt động.

| Tiêu chí | Event flow trong ứng dụng | Durable task/workflow |
|---|---|---|
| Mục tiêu | Thông báo hoặc phối hợp trong runtime | Hoàn tất một công việc nghiệp vụ |
| Nơi lưu | Thường ở bộ nhớ hoặc message nội bộ | Database bền vững và/hoặc durable broker |
| Vòng đời | Thường gắn với process hiện tại | Độc lập với vòng đời một process |
| Restart | Event chưa xử lý có thể mất | Có thể phục hồi từ trạng thái đã lưu |
| Retry | Tùy executor hoặc code gọi | Có policy, attempt, backoff và kết quả rõ ràng |
| Theo dõi | Log, metric hoặc trace | Operation ID, state, history và endpoint polling |
| Đảm bảo | Thường best-effort trong runtime | Thiết kế để chịu lỗi và xử lý lại an toàn |
| Ví dụ | Làm mới cache sau khi binding đổi | Provision database và theo dõi tới khi thành công |

Không phải mọi event đều cần durable. Một event chỉ dùng để cập nhật cache có thể được tái tạo từ database sau restart. Nhưng một yêu cầu tạo tài nguyên bên ngoài có side effect và cần được platform theo dõi thì phải có bản ghi bền vững.

## 2. Phân biệt command, event và operation

Ba khái niệm thường xuất hiện cùng nhau nhưng không đồng nghĩa:

- **Command** diễn đạt điều cần hệ thống thực hiện, ví dụ ProvisionInstance hoặc RotateBindingCredential.
- **Event** diễn đạt điều đã xảy ra, ví dụ InstanceProvisionRequested, ProviderResourceCreated hoặc BindingActivated.
- **Operation** là bản ghi vòng đời của một lần thực thi nghiệp vụ, có ID, trạng thái, thời điểm, lỗi và liên kết tới instance.

Ví dụ một yêu cầu provision:

~~~mermaid
flowchart LR
    A["Platform gửi provision request"] --> B["Command: ProvisionInstance"]
    B --> C["Operation được lưu"]
    C --> D["Event: InstanceProvisionRequested"]
    D --> E["Worker thực hiện provider call"]
    E --> F["Event: ProviderResourceCreated"]
    F --> G["Operation: SUCCEEDED"]
    G --> H["Instance: READY"]
~~~

Command có thể bị từ chối trước khi tạo operation nếu request sai schema, caller không có quyền hoặc instance ID xung đột. Khi command được chấp nhận để xử lý bất đồng bộ, broker tạo operation bền vững và liên kết mọi event/work item phát sinh với operation đó.

Event thường là một sự kiện bất biến: nó ghi lại một việc đã xảy ra tại một thời điểm. Không sửa một event cũ từ requested thành succeeded; hãy phát event mới hoặc cập nhật operation state. Operation là mô hình trạng thái hiện tại của một công việc, còn event history có thể lưu các mốc đã xảy ra để audit và điều tra.

## 3. Spring ApplicationEvent phù hợp ở đâu?

Spring cung cấp **ApplicationEventPublisher** để một bean thông báo event cho các listener trong application context. Cách dùng này hữu ích khi các thành phần cần tách rời nhau nhưng vẫn hoạt động trong cùng một ứng dụng.

Ví dụ, sau khi một binding được kích hoạt, service phát event nội bộ:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BindingActivationService {

    private final BindingRepository bindingRepository;
    private final ApplicationEventPublisher eventPublisher;

    public BindingActivationService(
            BindingRepository bindingRepository,
            ApplicationEventPublisher eventPublisher) {
        this.bindingRepository = bindingRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void activate(String bindingId) {
        BindingRecord binding = bindingRepository.activate(bindingId);
        eventPublisher.publishEvent(
                new BindingActivated(binding.bindingId(), binding.instanceId()));
    }
}

public record BindingActivated(
        String bindingId,
        String instanceId) {
}
~~~

Listener có thể thực hiện công việc phụ trợ:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.stereotype.Component;

@Component
public class BindingMetricsListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onBindingActivated(BindingActivated event) {
        // Cập nhật metric hoặc phát tín hiệu nội bộ không mang tính quyết định.
    }
}
~~~

Mặc định, event listener của Spring được gọi trong luồng publish theo cơ chế multicaster mặc định. Nếu listener chạy lâu, nó có thể kéo dài transaction hoặc thời gian phản hồi của request. Có thể cấu hình executor hoặc dùng **@Async** cho công việc phụ trợ, nhưng điều đó không biến event thành một thông điệp bền vững.

Application event thích hợp cho các hoạt động như:

- Cập nhật metric, cache hoặc read model có thể tái tạo.
- Ghi log nghiệp vụ hoặc phát tín hiệu trong cùng process.
- Làm sạch tài nguyên bộ nhớ sau khi trạng thái đã được lưu.
- Thông báo cho thành phần khác trong ứng dụng rằng một thay đổi đã xảy ra.
- Kích hoạt một tác vụ best-effort mà mất event không làm sai lệch trạng thái nghiệp vụ.

Không dùng ApplicationEvent đơn thuần làm bằng chứng duy nhất rằng một tác vụ provider đã được ghi nhận và sẽ được thực hiện sau restart.

## 4. Vì sao @Async không tự tạo durable queue?

**@Async** cho phép method chạy trên executor khác thay vì thread gọi. Điều này có thể giúp request HTTP trả về nhanh hơn, nhưng executor thông thường chỉ là cơ chế thực thi trong process.

Ví dụ:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class ProviderEventListener {

    @Async
    public void handle(InstanceProvisionRequested event) {
        // Thực hiện xử lý trong executor của process hiện tại.
    }
}
~~~

Nếu process dừng trước khi executor thực hiện xong, công việc đang nằm trong memory queue có thể mất. Khi ứng dụng có nhiều replica, mỗi replica còn có executor riêng; event được publish ở replica A không tự động được chuyển tới executor của replica B.

Cần phân biệt:

| Cơ chế | Điều nó cung cấp | Điều nó không tự bảo đảm |
|---|---|---|
| @Async | Chạy method trên executor | Lưu job bền vững qua restart |
| ThreadPoolTaskExecutor | Quản lý thread và hàng đợi trong process | Phục hồi queue sau process crash |
| ApplicationEventPublisher | Phát event trong application context | Giao nhận qua network hoặc lưu event |
| @TransactionalEventListener | Gắn listener với phase của transaction | Atomic durable delivery nếu process crash sau commit |
| Scheduled task | Chạy công việc theo lịch | Theo dõi riêng từng OSB operation nếu không có state store |

Có thể dùng @Async cho công việc không quan trọng nếu ứng dụng chấp nhận mất event và có cách tái tạo kết quả. Với provision/update/deprovision, cần lưu operation và công việc trong một kho bền vững trước khi trả 202.

## 5. Reactor Mono và Flux cũng không phải durable task store

Spring WebFlux và SCOSB sử dụng Reactor để biểu diễn xử lý bất đồng bộ. **Mono** mô tả tối đa một kết quả, **Flux** mô tả một chuỗi kết quả. Chúng giúp kết hợp I/O non-blocking và điều khiển luồng trong thời gian ứng dụng đang chạy.

Ví dụ:

~~~java
Mono<ProviderResult> result =
        providerClient.createDatabase(command)
                .timeout(providerTimeout)
                .retryWhen(retryPolicy);
~~~

Publisher trên mô tả cách thực hiện lời gọi provider. Nó không tự lưu command, trạng thái operation hoặc checkpoint xuống database. Nếu process dừng khi subscription đang chạy, subscription đó không tự khởi động lại sau khi broker được deploy lại.

Một **Sinks.Many** hoặc queue trong memory cũng chỉ giữ dữ liệu trong bộ nhớ của process. Nó hữu ích cho fan-out hoặc phối hợp trong runtime, nhưng không thay thế database, durable message broker hay workflow engine.

Có thể dùng Reactor bên trong worker để thực hiện một durable task. Ranh giới là: trước khi bắt đầu side effect, task và operation phải được ghi nhận bền vững; sau đó worker mới tạo subscription để xử lý. Nếu worker dừng, một worker khác đọc lại task chưa hoàn tất và tiếp tục theo checkpoint cùng idempotency policy.

## 6. OSB API đặt yêu cầu bền vững ở đâu?

OSB API cho phép broker xử lý đồng bộ hoặc bất đồng bộ. Khi operation hoàn tất nhanh, broker có thể trả response thành công ngay. Khi operation cần chạy nền và platform chấp nhận asynchronous operation, broker trả **202 Accepted** cùng operation identifier theo hợp đồng của endpoint.

Ví dụ flow provision:

~~~http
PUT /v2/service_instances/instance-100?accepts_incomplete=true
Content-Type: application/json
~~~

Response minh họa:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "provision-op-100"
}
~~~

Platform tiếp tục hỏi:

~~~http
GET /v2/service_instances/instance-100/last_operation?operation=provision-op-100
~~~

Broker trả trạng thái đã lưu:

~~~json
{
  "state": "in progress",
  "description": "Creating database resources"
}
~~~

Khi worker hoàn tất, operation được lưu ở trạng thái cuối cùng và lần polling tiếp theo trả **succeeded** hoặc **failed**.

Điểm mấu chốt: broker không nên trả 202 trước khi có một bản ghi operation bền vững và một cách đáng tin cậy để worker nhận được công việc. Nếu chỉ publish ApplicationEvent rồi trả 202, một process crash giữa hai bước có thể khiến platform tiếp tục polling một operation không bao giờ được thực hiện.

## 7. Mẫu kiến trúc: request, outbox, queue và worker

Một cấu trúc phổ biến kết hợp transaction database, **transactional outbox**, durable message broker và worker:

~~~mermaid
flowchart TD
    P["OSB platform request"] --> H["SCOSB service handler"]
    H --> V["Validate and authorize"]
    V --> T["Database transaction"]
    T --> I["Service instance / operation"]
    T --> O["Outbox event"]
    T --> C["Commit"]
    C --> R["Return 202 + operation ID"]
    O --> X["Outbox publisher"]
    X --> Q["Durable message queue"]
    Q --> W["Background worker"]
    W --> D["Provider adapter"]
    D --> E["Cloud / Kubernetes provider"]
    E --> W
    W --> S["Persist operation and instance state"]
    L["Platform polling"] --> G["getLastOperation()"]
    G --> S
~~~

Các thành phần có trách nhiệm riêng:

- **SCOSB service handler:** nhận request OSB, kiểm tra dữ liệu và gọi application service.
- **Database transaction:** tạo operation, cập nhật trạng thái instance và ghi outbox event một cách nguyên tử.
- **Outbox publisher:** chuyển event đã commit tới durable queue.
- **Durable queue:** giữ message khi worker tạm thời không hoạt động, theo cấu hình durability của hệ thống.
- **Worker:** claim operation, gọi provider và lưu checkpoint/kết quả.
- **Provider adapter:** chuyển command nghiệp vụ thành API call cụ thể tới cloud hoặc Kubernetes.
- **getLastOperation():** đọc operation store để trả trạng thái cho platform.

Durable queue không loại bỏ nhu cầu lưu operation trong database. Queue điều phối công việc; database là nguồn dữ liệu nghiệp vụ để truy vấn instance, operation và kết quả. Nếu queue message bị xử lý xong nhưng platform tiếp tục polling, broker vẫn phải có operation record để trả lời.

## 8. Transactional outbox giải quyết khoảng trống commit/publish

Một lỗi phổ biến là ghi operation vào database rồi publish message bằng hai bước độc lập:

1. Database commit thành công.
2. Broker process crash trước khi gửi message.

Kết quả là operation tồn tại nhưng không có worker nhận việc.

Đảo thứ tự cũng có vấn đề:

1. Message được publish.
2. Database transaction rollback.
3. Worker nhận message nhưng không tìm thấy operation hợp lệ.

Transactional outbox lưu operation và event trong cùng transaction database. Publisher riêng đọc các event chưa publish và chuyển chúng tới queue.

Ví dụ schema rút gọn:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    instance_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    state VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE broker_outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    operation_id VARCHAR(128) NOT NULL
        REFERENCES broker_operation(operation_id),
    event_type VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    publish_state VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Trong cùng transaction:

~~~java
@Transactional
public OperationAccepted acceptProvision(ProvisionCommand command) {
    ServiceInstance instance = instanceRepository.createProvisioning(command);
    Operation operation = operationRepository.createQueued(
            instance.instanceId(), "PROVISION");

    outboxRepository.insert(
            OutboxEvent.provisionRequested(operation.operationId()));

    return new OperationAccepted(instance.instanceId(), operation.operationId());
}
~~~

Đoạn code minh họa ranh giới transaction. Việc gửi queue không diễn ra trực tiếp bên trong transaction này. Sau khi commit, publisher sẽ chuyển outbox event.

Publisher có thể đọc theo batch, gửi message rồi đánh dấu PUBLISHED. Nếu publisher crash sau khi queue đã nhận message nhưng trước khi cập nhật trạng thái outbox, event có thể được gửi lại. Vì vậy, outbox thường cung cấp giao nhận ít nhất một lần; consumer phải idempotent.

## 9. Worker phải có checkpoint và state machine

Worker không nên chỉ nhận một message rồi chạy một đoạn code dài mà không lưu tiến độ. Provider có thể trả về operation ID riêng, timeout, hoặc yêu cầu polling. Broker cần ghi nhận các bước để có thể tiếp tục sau restart.

Một state machine nội bộ ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> CLAIMED: Worker claims
    CLAIMED --> IN_PROGRESS: Start provider action
    IN_PROGRESS --> WAITING_PROVIDER: Provider returns operation ID
    WAITING_PROVIDER --> IN_PROGRESS: Provider still processing
    IN_PROGRESS --> SUCCEEDED: Provider result committed
    IN_PROGRESS --> FAILED: Terminal error
    WAITING_PROVIDER --> RECONCILIATION_REQUIRED: Provider outcome uncertain
    RECONCILIATION_REQUIRED --> IN_PROGRESS: Reconcile and resume
    RECONCILIATION_REQUIRED --> SUCCEEDED: Provider confirms success
    RECONCILIATION_REQUIRED --> FAILED: Confirmed terminal failure
~~~

Mỗi bước chuyển trạng thái cần có điều kiện rõ ràng:

- QUEUED chỉ được claim bởi worker hợp lệ.
- CLAIMED cần lưu worker/lease và thời điểm hết hạn.
- IN_PROGRESS được lưu trước hoặc sau các side effect theo checkpoint đã thiết kế.
- WAITING_PROVIDER lưu provider operation ID để worker có thể tiếp tục truy vấn.
- SUCCEEDED chỉ được ghi khi provider và broker đã commit dữ liệu cần thiết.
- FAILED chỉ dùng khi đã xác định lỗi kết thúc; timeout không rõ kết quả có thể cần reconciliation.

Khi worker nhận lại task sau khi lease hết hạn, nó phải đọc operation hiện tại và provider state trước khi thực hiện side effect. Không mặc định rằng worker cũ đã chết đồng nghĩa provider chưa thực hiện lệnh.

## 10. Dùng ApplicationEvent ở đúng vị trí trong kiến trúc

ApplicationEvent vẫn hữu ích trong kiến trúc durable task. Ví dụ, sau khi worker cập nhật operation thành SUCCEEDED, broker có thể phát event nội bộ để refresh cache hoặc cập nhật metric.

~~~mermaid
flowchart TD
    A["Worker receives durable task"] --> B["Provider operation"]
    B --> C["Commit operation = SUCCEEDED"]
    C --> D["Publish local Spring event"]
    D --> E["Refresh cache"]
    D --> F["Update metrics"]
    D --> G["Notify in-process observer"]
~~~

Trong flow này, trạng thái thành công đã được commit trước khi phát local event. Nếu event bị mất do process crash, cache hoặc metric có thể được làm mới lại từ database. Tác vụ phụ trợ không quyết định kết quả provision.

Có thể dùng **@TransactionalEventListener(phase = AFTER_COMMIT)** để listener chỉ chạy sau khi transaction commit. Tuy nhiên, listener vẫn chạy trong process; process có thể crash ngay sau commit và trước khi listener hoàn tất. Nếu hành động của listener là bắt buộc phải giao nhận, hãy ghi một outbox event trong transaction thay vì chỉ dựa vào AFTER_COMMIT.

Quy tắc thực tế:

- Event best-effort, có thể tái tạo: dùng Spring ApplicationEvent.
- Công việc phải được thực hiện sau restart: dùng durable task/outbox/queue.
- Thay đổi trạng thái nghiệp vụ: lưu database trong transaction.
- Tác vụ phụ thuộc provider: thực hiện trong worker có retry và idempotency.
- Thông báo cho thành phần nội bộ sau commit: dùng application event nếu mất event không làm sai nghiệp vụ.

## 11. Kết hợp Reactor bên trong durable worker

Reactor phù hợp để thực hiện I/O non-blocking trong worker. Ví dụ, worker có thể đọc operation, lấy credential, gọi provider và ghi kết quả bằng chuỗi Mono.

~~~java
public Mono<Void> executeProvision(String operationId) {
    return operationRepository.findById(operationId)
            .switchIfEmpty(Mono.error(
                    new OperationNotFoundException(operationId)))
            .flatMap(operation -> operationRepository.claim(operation)
                    .thenReturn(operation))
            .flatMap(operation -> providerCredentialProvider
                    .acquire(operation.providerTarget())
                    .flatMap(session -> providerClient.provision(
                            operation.command(), session)))
            .flatMap(providerResult ->
                    persistProvisionResult(operationId, providerResult))
            .then();
}
~~~

Đây là pseudocode kiến trúc. Implementation cần xử lý lease, version, provider operation ID, timeout và phân loại lỗi. Nếu worker dùng reactive pipeline, subscription phải được tạo bởi worker runtime sau khi message đã được nhận; không tạo một subscription trong request handler rồi bỏ tham chiếu và kỳ vọng nó tự sống qua restart.

Một số nguyên tắc Reactor:

- Không gọi block() trên event loop của WebFlux.
- Không dùng publishOn/subscribeOn như một cách lưu công việc bền vững.
- Không gọi subscribe() rời rạc trong service handler để fire-and-forget.
- Giữ lỗi trong pipeline để worker có thể cập nhật trạng thái operation.
- Giới hạn concurrency và prefetch để không làm quá tải provider.
- Dùng timeout theo từng provider call và deadline tổng của operation.
- Nếu gọi API blocking, cô lập trên boundedElastic hoặc dùng client non-blocking phù hợp.

## 12. Retry, idempotency và giao nhận ít nhất một lần

Durable queue và outbox thường có thể gửi cùng message nhiều lần. Worker có thể crash sau khi provider đã thực hiện side effect nhưng trước khi broker đánh dấu operation thành công. Vì vậy, không nên dựa vào giả định message chỉ được xử lý đúng một lần.

Worker cần idempotency ở cả hai lớp:

1. **Broker-level idempotency:** cùng operation ID không tạo operation nghiệp vụ mới hoặc ghi đè kết quả khác.
2. **Provider-level idempotency:** nếu provider hỗ trợ idempotency key, gửi operation ID hoặc key ổn định để provider nhận diện request lặp.

Nếu provider không hỗ trợ idempotency key, broker cần truy vấn resource theo marker/metadata hoặc provider operation ID trước khi gửi lại lệnh tạo. Một retry sau timeout phải xác định provider đã làm gì, thay vì gửi lại một create request mù quáng.

Retry policy nên phân biệt:

| Lỗi | Hướng xử lý |
|---|---|
| Provider throttling | Backoff có jitter, tôn trọng Retry-After |
| Network timeout, kết quả chưa rõ | Tra cứu provider operation/resource trước retry |
| Token hết hạn | Refresh credential rồi retry nếu side effect an toàn |
| Permission denied | Dừng retry tự động và cảnh báo policy |
| Invalid parameter | Đánh dấu lỗi cuối cùng |
| Provider 5xx tạm thời | Retry có giới hạn nếu operation idempotent |
| Resource conflict | Đọc trạng thái hiện tại và reconcile |

Không retry vô hạn. Khi vượt retry budget, chuyển operation sang FAILED hoặc RECONCILIATION_REQUIRED tùy mức độ chắc chắn của kết quả và quy trình vận hành.

## 13. Transaction boundary và saga

Database broker và provider thường không tham gia cùng một transaction ACID. Không giữ transaction database mở trong lúc gọi cloud API trong nhiều phút. Cách làm đó giữ lock lâu, gây contention và không thể rollback side effect bên ngoài.

Dùng transaction ngắn để ghi ý định và operation, sau đó thực hiện provider call ngoài transaction. Khi provider phản hồi, mở transaction mới để lưu external resource mapping, instance state và operation result.

~~~mermaid
sequenceDiagram
    participant API as Broker handler
    participant DB as Broker database
    participant Q as Durable queue
    participant W as Worker
    participant P as Provider

    API->>DB: Transaction: instance + operation + outbox
    DB-->>API: Commit
    API-->>API: Return 202
    Q->>W: Deliver operation
    W->>P: Create external resource
    P-->>W: Resource ID / provider operation ID
    W->>DB: Transaction: mapping + operation result + instance state
    DB-->>W: Commit
~~~

Nếu workflow gồm nhiều side effect, chẳng hạn tạo database, tạo network policy và tạo backup schedule, có thể dùng saga. Mỗi bước có trạng thái và có thể có hành động bù trừ:

- Tạo database thành công.
- Tạo network policy thất bại.
- Broker thử lại bước network policy.
- Nếu không thể khôi phục, broker có thể chạy compensating action để xóa database theo policy.
- Operation kết thúc với trạng thái phản ánh kết quả thực tế.

Compensation không phải rollback ACID. Một tài nguyên đã được tạo rồi xóa vẫn có thể để lại log, chi phí hoặc dữ liệu audit. Vì vậy, mỗi bước cần idempotency và trạng thái riêng.

## 14. Phục hồi sau restart và xử lý worker cạnh tranh

Khi broker restart, worker mới cần biết operation nào chưa hoàn tất. Có thể truy vấn operation ở QUEUED, IN_PROGRESS hoặc WAITING_PROVIDER cùng với lease hết hạn.

Một chiến lược claim:

1. Worker đọc một nhóm operation đủ điều kiện.
2. Thực hiện conditional update để chuyển QUEUED sang CLAIMED hoặc gia hạn lease.
3. Chỉ worker claim thành công mới thực hiện side effect.
4. Mỗi lần cập nhật lưu version/fencing token.
5. Worker cũ không được ghi đè kết quả sau khi lease của nó hết hạn.
6. Worker mới kiểm tra provider state trước khi tiếp tục operation đã bị bỏ dở.

Với database hỗ trợ, có thể dùng row locking hoặc SELECT ... FOR UPDATE SKIP LOCKED để nhiều worker lấy các operation khác nhau. Nếu dùng distributed queue, broker vẫn cần xử lý duplicate delivery và lease/visibility timeout.

Không giữ một lock database trong suốt provider call. Dùng lease có thời hạn, cập nhật heartbeat hoặc checkpoint; provider call có thể lâu hơn lease nên cần gia hạn hoặc fencing để tránh worker cũ và worker mới cùng thao tác.

## 15. Phân biệt event history với current state

Một số broker cần audit chi tiết hơn trạng thái hiện tại. Có thể lưu event history append-only:

| Event | Ý nghĩa |
|---|---|
| ProvisionRequested | Platform yêu cầu tạo instance |
| ProvisionAccepted | Broker chấp nhận và tạo operation |
| ProviderCreateStarted | Worker bắt đầu gọi provider |
| ProviderOperationPending | Provider trả mã operation đang chạy |
| ProviderResourceCreated | Provider xác nhận tài nguyên |
| InstanceReady | Broker lưu trạng thái instance sẵn sàng |
| ProvisionFailed | Operation kết thúc thất bại |

Event history hỗ trợ audit và phân tích, còn bảng operation và instance giữ current state. Không nên coi event log là nguồn duy nhất nếu chưa thiết kế replay, ordering, schema evolution và xử lý duplicate.

Khi event được phát từ nhiều replica, cần có event ID, aggregate ID, sequence/version và timestamp. Consumer phải xử lý duplicate; nếu thứ tự quan trọng, cần kiểm tra sequence trước khi áp dụng event. Event payload không nên chứa credential hoặc secret.

## 16. Backpressure và giới hạn tải worker

Durable queue có thể tích lũy message khi provider chậm hoặc worker thiếu tài nguyên. Nếu worker lấy quá nhiều message cùng lúc, broker có thể tạo hàng loạt connection, vượt quota provider hoặc chiếm hết thread.

Cần giới hạn:

- Số operation worker claim đồng thời.
- Số provider call đồng thời theo provider account.
- Số operation đồng thời theo tenant hoặc plan.
- Queue prefetch và batch size.
- Thời gian tối đa một bước provider call.
- Số retry và tổng retry budget.
- Tốc độ publish từ outbox.

Reactor có thể giúp giới hạn concurrency trong pipeline, nhưng giới hạn phải phối hợp với queue consumer và provider quota. Ví dụ flatMap với concurrency hữu hạn kiểm soát số publisher con đang chạy trong một subscription; nó không thay thế rate limiter phân tán giữa nhiều replica.

## 17. Observability cho durable operation

Một event flow trong process có thể theo dõi bằng log và trace, nhưng durable workflow cần định danh xuyên suốt nhiều process và nhiều lần retry.

Mỗi operation nên có:

- operation ID ổn định.
- service instance ID và loại operation.
- correlation ID hoặc trace context được truyền qua message.
- tenant reference đã được mask phù hợp.
- attempt count, worker ID và lease expiry.
- provider operation ID.
- trạng thái hiện tại, thời gian bắt đầu và thời điểm cập nhật gần nhất.
- mã lỗi đã chuẩn hóa và kết quả cuối cùng.

Metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| broker_operations_queued | Số operation đang chờ |
| broker_operations_in_progress | Số operation đang chạy |
| broker_operation_duration_seconds | Thời gian hoàn tất operation |
| broker_operation_retry_total | Tổng số lần retry |
| broker_outbox_pending | Số outbox event chưa publish |
| broker_queue_oldest_message_age_seconds | Tuổi message cũ nhất |
| broker_provider_request_failures_total | Lỗi provider theo nhóm |
| broker_operation_reconciliation_total | Operation cần đối chiếu |

Không đưa token, password, raw parameters nhạy cảm hoặc toàn bộ request body vào log. Dùng operation ID và correlation ID để tìm log liên quan.

## 18. Kiểm thử ranh giới giữa event flow và durable task

Test cần xác minh cả hai cơ chế hoạt động đúng mục đích.

| Tình huống | Kết quả mong đợi |
|---|---|
| Application event được publish | Listener nội bộ nhận event theo cấu hình |
| Listener chạy @Async | Request không phải chờ listener, nhưng không coi queue là durable |
| Transaction rollback | AFTER_COMMIT listener không được chạy |
| Process crash sau DB commit nhưng trước publish | Outbox publisher vẫn tìm thấy event PENDING |
| Queue giao cùng message hai lần | Worker không tạo side effect trùng |
| Worker crash sau provider success | Worker mới reconcile bằng provider operation/resource ID |
| Broker restart khi operation IN_PROGRESS | Operation vẫn có thể được tiếp tục |
| Provider trả operation ID | Broker lưu ID và worker theo dõi tiếp |
| Platform polling | getLastOperation đọc state đã lưu, không chạy lại provider |
| Retry vượt budget | Operation chuyển sang trạng thái lỗi hoặc reconciliation |
| Nhiều worker cạnh tranh | Chỉ worker claim hợp lệ thực hiện bước có side effect |
| Queue backlog tăng | Concurrency và rate limit giữ tải trong giới hạn |

Có thể kiểm thử transactional outbox với database thật qua Testcontainers, còn message broker có thể dùng container tương ứng hoặc test fixture của hệ thống. Mock publisher chỉ xác minh code gọi publisher, không chứng minh transaction database và queue được phối hợp bền vững.

## 19. Quy trình lựa chọn cơ chế

Khi thêm một luồng xử lý vào broker, hãy tự hỏi:

1. Nếu process dừng ngay sau khi nhận yêu cầu, có được phép mất công việc không?
2. Platform hoặc người vận hành có cần biết trạng thái và kết quả cuối cùng không?
3. Công việc có gọi provider hoặc tạo side effect bên ngoài không?
4. Có cần retry sau timeout hoặc phục hồi sau restart không?
5. Nhiều replica có thể cùng xử lý công việc không?
6. Có cần audit operation và xác định request lặp không?

Nếu câu trả lời cho các câu hỏi về mất công việc, trạng thái, side effect hoặc phục hồi là có, hãy dùng durable operation. ApplicationEvent có thể được dùng bổ sung cho thông báo nội bộ sau commit, nhưng không thay thế operation store và queue.

Một cách chọn nhanh:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Thông báo nội bộ trong cùng process | Spring ApplicationEvent |
| I/O non-blocking trong request/worker | Reactor Mono/Flux |
| Chạy method trên executor trong process | @Async / TaskExecutor |
| Lưu yêu cầu nghiệp vụ qua restart | Database operation store |
| Đồng bộ commit database với publish event | Transactional outbox |
| Giao công việc giữa nhiều process | Durable message broker |
| Điều phối nhiều bước có checkpoint/compensation | Durable workflow hoặc saga |
| Platform hỏi trạng thái OSB operation | last_operation đọc operation store |

## 20. Checklist triển khai cho service broker

Trước khi đưa một tác vụ provision/update/deprovision vào production, hãy kiểm tra:

- Command và operation có định danh ổn định.
- Operation được lưu trước khi broker trả 202.
- Instance state và operation state được cập nhật bằng transaction phù hợp.
- Outbox event được ghi cùng transaction nếu công việc cần publish ra queue.
- Publisher và worker xử lý duplicate delivery.
- Worker có claim/lease, checkpoint và giới hạn concurrency.
- Provider call có timeout, retry budget và idempotency.
- Provider operation ID được lưu để polling hoặc reconciliation.
- Operation có thể phục hồi sau broker restart.
- getLastOperation chỉ đọc state và trả đúng operation platform yêu cầu.
- Spring ApplicationEvent chỉ dùng cho event nội bộ phù hợp.
- @Async, executor và Reactor không bị nhầm với durable queue.
- Secret không xuất hiện trong event payload, log hoặc trace.
- Có metric cho queue backlog, operation duration, retry và lỗi provider.
- Có integration test cho transaction/outbox/worker và tình huống crash.

## Kết luận

Event flow trong ứng dụng Spring và durable task giải quyết hai bài toán khác nhau. **ApplicationEvent**, **@Async** và **Reactor Mono/Flux** giúp phối hợp xử lý trong runtime, nhưng tự chúng không lưu công việc qua restart. Với các operation OSB API có side effect như provision, update, bind hoặc deprovision, broker cần ghi operation bền vững, dùng transactional outbox để chuyển công việc tới durable queue và worker có checkpoint, idempotency cùng recovery. Sau khi trạng thái đã commit, application event có thể thông báo cho các thành phần nội bộ như cache hoặc metric. Tách đúng ranh giới này giúp broker vừa tận dụng mô hình reactive của Spring vừa bảo đảm công việc hạ tầng được theo dõi và phục hồi đáng tin cậy.

## Tài liệu tham khảo

- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — event publication và listener trong application context.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — TaskExecutor, @Async và scheduling.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — TransactionalEventListener và transaction phase.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — Mono, Flux, Sinks, scheduler và backpressure.
- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — provision, update, deprovision và last_operation.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — service abstraction và xử lý operation trong SCOSB.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — ghi dữ liệu nghiệp vụ và event trong cùng transaction.

