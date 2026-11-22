# Cleanup resource khi tenant bị xóa trong dynamic runtime

Trong hệ thống đa tenant, mỗi tenant có thể được gắn với một **IntegrationFlow tạo động** để nhận message, gọi handler, polling dữ liệu, giữ trạng thái correlation, retry hoặc phát sự kiện ra hệ thống bên ngoài. Khi tenant bị xóa, chỉ xóa một hàng trong bảng <code>tenants</code> là chưa đủ: inbound adapter có thể vẫn nhận message, executor còn task đang chạy, delayer còn message đến hạn, aggregator còn pending group, hoặc một kết nối tới broker vẫn chiếm tài nguyên.

Chủ đề **“Cleanup resource khi tenant bị xóa”** thuộc chương **Dynamic runtime** của module **SPRING_INTEGRATION_RUNTIME**. Mục tiêu là thiết kế một quy trình tháo gỡ flow an toàn khi ứng dụng đang hoạt động, sử dụng <code>IntegrationFlowContext</code> và kết hợp lifecycle, channel, consumer endpoint, poller, executor, transaction, retry, message store, error handling và correlation.

> **Phân biệt ngay từ đầu:** <code>IntegrationFlowContext.remove(flowId)</code> hoặc <code>IntegrationFlowRegistration.destroy()</code> gỡ bỏ flow đã đăng ký động và các bean phụ thuộc do cơ chế đăng ký sở hữu. Chúng **không** tự quyết định phải làm gì với message chưa xử lý, giao dịch đang chạy, bản ghi trong persistent store, tác vụ ngoại vi hoặc tài nguyên dùng chung của nhiều tenant.

## 1. Tenant bị xóa nhưng runtime vẫn còn: điều gì có thể xảy ra?

Giả sử tenant <code>T-42</code> có một flow:

~~~text
Tenant inbound adapter
    → tenant.input
    → transformer
    → ExecutorChannel
    → service activator
    → router
    ├─ outbound broker adapter
    └─ tenant audit store
~~~

Một lệnh xóa tenant đến đúng lúc executor đang xử lý message thứ ba trong batch; đồng thời một poller còn đang lấy dữ liệu và aggregator đang chờ fragment cuối.

Nếu lệnh xóa chỉ gọi <code>flowContext.remove("tenant.T-42")</code> ngay lập tức, kết quả có thể là:

- Flow không còn đăng ký, nhưng một <code>Runnable</code> đã giao cho executor vẫn có thể chạy tới cuối.
- Message bị broker redeliver sau restart và chạm vào handler không còn tồn tại.
- Dữ liệu <code>MessageGroupStore</code> vẫn còn vì nằm trong JDBC/Redis độc lập với vòng đời bean.
- Scheduled task hoặc HTTP callback do code ứng dụng tự tạo vẫn giữ tham chiếu tới resource của tenant.
- Một bean kết nối dùng chung bị đóng nhầm, làm tenant khác ngừng xử lý.
- Tenant bị tạo lại với cùng ID trong lúc cleanup cũ còn đang xóa, gây race condition và mất dữ liệu mới.

Vì vậy, bài toán **không đơn thuần là gọi API destroy**. Nó là một quá trình ngăn nhận công việc mới, xử lý công việc đã nhận, tháo gỡ đúng tài nguyên sở hữu và xác nhận trạng thái cuối cùng.

~~~mermaid
flowchart TD
    A["Yêu cầu xóa tenant"] --> B["Đánh dấu DELETING bền vững"]
    B --> C["Chặn admission / tạm dừng nguồn nhận mới"]
    C --> D{"Còn in-flight hoặc pending?"}
    D -->|Có| E["Drain, hoàn tất hoặc chuyển quarantine"]
    E --> D
    D -->|Không, hoặc đã xử lý theo policy| F["Stop flow"]
    F --> G["Destroy registration / remove flow"]
    G --> H["Đóng resource thuộc riêng tenant"]
    H --> I["Dọn dữ liệu theo retention policy"]
    I --> J["Xác minh và đánh dấu DELETED"]
    D -. "Hết hạn / lỗi" .-> K["Giữ trạng thái DELETING_FAILED để retry"]
~~~

Sơ đồ là một **quy trình ứng dụng cần thực hiện**, không phải tính năng có sẵn tự chạy trong <code>IntegrationFlowContext</code>.

## 2. Kiểm kê ownership trước khi cleanup

Trước khi viết một dòng code xóa resource, phải xác định thành phần nào **thuộc về tenant** và thành phần nào được **chia sẻ**. “Có sử dụng resource” không có nghĩa “được quyền đóng resource”.

| Resource | Phạm vi sở hữu thường gặp | Chính sách khi xóa tenant |
|---|---|---|
| <code>IntegrationFlowRegistration</code> của tenant | Riêng tenant | Stop rồi destroy/remove đúng ID |
| Channel/endpoint được tạo cùng dynamic flow | Riêng flow | Được quản lý theo lifecycle của registration nếu là bean phụ thuộc được đăng ký |
| Shared <code>DirectChannel</code>/<code>PublishSubscribeChannel</code> | Toàn ứng dụng | Chỉ ngắt subscriber/route của tenant; **không** hủy channel chung |
| <code>ThreadPoolTaskExecutor</code> riêng tenant | Riêng tenant | Chặn task mới, drain/cancel theo SLA, shutdown sau khi hết owner |
| Global executor hoặc <code>TaskScheduler</code> | Dùng chung | Không shutdown; chỉ hủy task/registration do tenant tạo nếu có |
| Kafka/JMS/AMQP listener container riêng | Có thể riêng tenant | Pause/stop đúng container; xác nhận ACK và redelivery |
| Shared connection factory hoặc broker client | Dùng chung | Không đóng; chỉ tháo endpoint/consumer của tenant |
| <code>MessageGroupStore</code>, <code>JdbcMessageStore</code> | Có thể dùng chung backend và phân vùng theo region/key | Dọn **đúng partition** theo chính sách, không xóa toàn bộ bảng |
| Delayer/aggregator pending message | Riêng tenant về mặt dữ liệu | Chọn hoàn tất, hủy có kiểm toán hoặc quarantine |
| Retry queue, DLQ, outbox/inbox và error record | Thường ở persistent store/broker | Áp dụng retention, idempotency và quy định bảo toàn dữ liệu |
| Tenant credentials/secret, file watcher, timer tự tạo | Riêng tenant | Thu hồi/close khi không còn in-flight work cần chúng |
| Metrics, subscriptions, callbacks, caches | Tùy cách đăng ký | Hủy listener/registration và khóa cache thuộc tenant |

**Quy tắc sở hữu:** Thành phần tạo resource phải ghi rõ ai chịu trách nhiệm đóng, thời điểm được phép đóng và hành vi nếu cleanup thất bại. Một singleton được inject cho nhiều flow **không** trở thành resource riêng tenant chỉ vì flow dùng nó.

## 3. API gỡ flow động: stop, destroy và remove

Spring Integration cung cấp <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code> để tạo và quản lý flow ở runtime. Một flow được đăng ký nhận lại <code>IntegrationFlowContext.IntegrationFlowRegistration</code>.

| API | Công dụng | Giới hạn |
|---|---|---|
| <code>flowContext.registration(flow)</code> | Tạo builder để đăng ký flow | Chưa đăng ký cho tới khi <code>register()</code> |
| <code>.id(flowId)</code> | Gắn ID cụ thể để quản trị, tránh tên ngẫu nhiên | ID phải duy nhất trong context |
| <code>.useFlowIdAsPrefix()</code> | Prefix tên bean của flow, giảm va chạm giữa các flow tương tự | Phải đã chỉ định <code>.id(...)</code> |
| <code>.autoStartup(false)</code> | Đăng ký trước nhưng chưa tự start | Ứng dụng phải gọi <code>registration.start()</code> |
| <code>registration.start()</code> | Start các thành phần lifecycle của flow | Không tự mở lại dữ liệu/cấu hình đã bị xóa ở DB |
| <code>registration.stop()</code> | Dừng lifecycle của flow | Không mặc định **đợi tất cả task in-flight hoàn tất** |
| <code>registration.destroy()</code> | Destroy flow và bean phụ thuộc do registration quản lý, dọn registry nội bộ | Không xóa persistent message data và resource ngoại vi ngoài ownership |
| <code>flowContext.remove(flowId)</code> | Destroy registration theo ID và dọn cache của context | Cùng nhóm hành vi với <code>destroy()</code>; không cần gọi cả hai |
| <code>flowContext.getRegistrationById(flowId)</code> | Tìm registration động đã có | Có thể trả <code>null</code> sau cleanup hoặc sau restart chưa rebuild |

Các bean phụ thuộc đăng ký thông qua builder <code>addBean(...)</code> cũng thuộc phạm vi hủy của registration. Không đưa một singleton **shared** vào <code>addBean(...)</code> chỉ để tiện truy cập, nếu không muốn resource đó bị destroy cùng flow tenant.

Tài liệu Spring Integration khuyến nghị chỉ định **flow ID rõ ràng**. Với flow có nhiều component mang cùng ID nội bộ, <code>useFlowIdAsPrefix()</code> giúp tránh trùng tên bean. Phần này nói tới API 6.x; hãy kiểm tra version thực tế khi sử dụng các phương thức nâng cao.

### Stop khác destroy ở đâu?

~~~text
RUNNING
  ├─ registration.stop()    → STOPPED (còn definition/registration)
  │                           registration.start() có thể chạy lại
  └─ registration.destroy() → không còn registration trong context
                              muốn chạy lại phải tạo và register flow mới
~~~

Stop dùng để tạm dừng, sửa cấu hình hoặc chuyển trạng thái trước khi drain. Destroy/remove dùng khi flow **không còn được phép tồn tại** trong context. Không nên dùng <code>remove()</code> làm “pause” vì việc tạo lại flow có thể sinh tên bean/resource hoặc đăng ký subscription mới.

## 4. Ví dụ Java DSL: đăng ký một IntegrationFlow cho mỗi tenant

Ví dụ Java 17+ và Spring Integration 6.x: ứng dụng tạo flow nhận message qua <code>DirectChannel</code> riêng, gọi một service **dùng chung** có kiểm tra tenant, rồi kết thúc. Đây là mô hình tối thiểu để thấy rõ **flow-owned** và **shared** resource.

**Bước 1 — định nghĩa command và service chung:**

~~~java
public record TenantEvent(
        UUID tenantId,
        String eventId,
        String payload) {}

@Service
public class TenantBusinessService {
    public void process(TenantEvent event) {
        // Xác thực tenant còn ACTIVE theo trạng thái bền vững;
        // ghi DB idempotently theo (tenantId, eventId).
        // Logic nghiệp vụ thực không được giả định do Spring Integration quản lý.
    }
}
~~~

<code>eventId</code> là khóa idempotency của **một hành động**; <code>tenantId</code> là khóa phân vùng/sở hữu. Không lấy <code>MessageHeaders.ID</code> thay cho event ID của nghiệp vụ vì một lần redelivery có thể tạo message ID mới.

**Bước 2 — tạo flow và đăng ký với ID ổn định:**

~~~java
@Component
public class TenantFlowFactory {
    private final IntegrationFlowContext flowContext;
    private final TenantBusinessService businessService;

    public TenantFlowFactory(IntegrationFlowContext flowContext,
                             TenantBusinessService businessService) {
        this.flowContext = flowContext;
        this.businessService = businessService;
    }

    public String flowId(UUID tenantId) {
        return "tenant.flow." + tenantId;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration create(
            UUID tenantId) {
        String id = flowId(tenantId);
        if (flowContext.getRegistrationById(id) != null) {
            throw new IllegalStateException("Flow đã tồn tại: " + id);
        }

        GenericHandler<TenantEvent> handler = (event, headers) -> {
            if (!tenantId.equals(event.tenantId())) {
                throw new IllegalArgumentException("Message sai tenant");
            }
            businessService.process(event);
            return null; // One-way handler; không gửi reply.
        };

        IntegrationFlow flow = IntegrationFlow
            .from(new DirectChannel())
            .handle(handler)
            .get();

        var registration = flowContext.registration(flow)
            .id(id)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();

        registration.start(); // Chỉ sau khi đã đăng ký trạng thái/routing phù hợp.
        return registration;
    }
}
~~~

Các import chính: <code>java.util.UUID</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code>, <code>org.springframework.integration.handler.GenericHandler</code>, <code>org.springframework.integration.channel.DirectChannel</code> và <code>org.springframework.stereotype.Component</code>/<code>Service</code>.

Trong ví dụ này, <code>TenantBusinessService</code> là bean dùng chung trong Spring context. **Không gọi destroy service đó** khi xóa flow tenant. <code>DirectChannel</code> được tạo mới cho mỗi flow; endpoint của từng flow gắn với channel riêng. Hai tenant có thể dùng cùng code service nhưng không chia channel input.

Ví dụ minh họa API đăng ký. Trong production, phép kiểm tra <code>getRegistrationById()</code> rồi <code>register()</code> phải có **cơ chế đồng bộ tạo/xóa ở tầng ứng dụng**; bản thân cặp thao tác ấy không phải giao dịch nguyên tử trên nhiều node. Ngoài ra, chỉ start flow sau khi trạng thái tenant đã sẵn sàng nhận message.

### Gửi message vào đúng flow

~~~java
UUID tenantId = UUID.fromString(
    "a9a67cb0-ec34-4f6d-9fab-d35464a55c3b");
String id = tenantFlowFactory.flowId(tenantId);

// Chỉ gửi sau khi đã kiểm tra tenant còn ACTIVE và có quyền nhận.
var registration = flowContext.getRegistrationById(id);
if (registration == null) {
    throw new IllegalStateException("Tenant flow không khả dụng");
}

Message<TenantEvent> event = MessageBuilder
    .withPayload(new TenantEvent(tenantId, "event-1001", "data"))
    .setHeader("tenantId", tenantId.toString())
    .setHeader("correlationId", "request-1001")
    .build();

registration.getInputChannel().send(event);
~~~

<code>MessageBuilder</code> thuộc <code>org.springframework.integration.support</code>. Lấy registration thành công **chưa ngăn được** một thread cleanup khác destroy flow ngay sau đó. Vì vậy trong ứng dụng thật, toàn bộ đường send phải đi qua **admission gate** đồng bộ theo tenant, thay vì cho phép mọi nơi gửi bằng reference tới channel đã cache.

## 5. State machine cho xóa tenant

Một trạng thái <code>DELETED</code> đơn lẻ không đủ để biểu diễn công việc cleanup có nhiều bước và dễ thất bại giữa chừng. Một state machine đề xuất:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> DELETING: lệnh xóa + CAS/version
    DELETING --> DRAINING: chặn ingress thành công
    DRAINING --> QUIESCED: in-flight=0 hoặc đã quarantine
    QUIESCED --> UNREGISTERED: stop + destroy flow
    UNREGISTERED --> CLEANING_DATA: thu hồi resource riêng
    CLEANING_DATA --> DELETED: kiểm tra hậu điều kiện
    DELETING --> CLEANUP_FAILED: lỗi
    DRAINING --> CLEANUP_FAILED: timeout / lỗi
    QUIESCED --> CLEANUP_FAILED: lỗi
    UNREGISTERED --> CLEANUP_FAILED: lỗi
    CLEANING_DATA --> CLEANUP_FAILED: lỗi
    CLEANUP_FAILED --> DELETING: retry có checkpoint
~~~

Tên trạng thái là **hợp đồng của ứng dụng**, không phải trạng thái Spring Integration cung cấp sẵn. Cần lưu bền vững <code>tenantId</code>, <code>deletionRequestId</code>, <code>generation</code>, phase hiện tại, thời điểm, lỗi cuối cùng và checkpoint đã hoàn tất. Khi một pod chết giữa chừng, pod khác có thể tiếp tục cleanup theo trạng thái này.

### Vì sao không đánh dấu DELETED trước rồi mới dọn?

Nếu đánh dấu đã xóa trước khi resource thực sự ngừng nhận message, các đường xử lý nền có thể vẫn cập nhật database hoặc gửi yêu cầu ra hệ thống khác với tenant không còn hợp lệ. Mặt khác, nếu chờ mọi cleanup hạ tầng xong **trong một database transaction dài**, transaction sẽ giữ lock quá lâu và không thể nguyên tử bao trùm broker/API ngoài.

Giải pháp thường là transaction ngắn để chuyển <code>ACTIVE → DELETING</code>, rồi xử lý các bước bất đồng bộ, idempotent với checkpoint. API xóa trả về trạng thái “đang xử lý” nếu toàn bộ cleanup không thể hoàn tất trong request HTTP thông thường.

## 6. Bước 1 — Chặn nhận message mới (quiesce ingress)

Đây là bước **quan trọng nhất** để drain có điểm kết thúc. Nếu consumer vẫn tiếp tục nhận message mới, số in-flight có thể không bao giờ về 0.

**Admission gate** là chính sách do ứng dụng kiểm soát trước khi đưa message vào flow:

~~~text
Incoming request / broker delivery
   → kiểm tra tenantId + generation + tenant state
   → ACTIVE?  ── Yes ──> submit to tenant flow
        │
        No
        ↓
   reject / NACK / quarantine theo loại nguồn
~~~

Một đoạn kiểm tra kiểu <code>if (tenant.isActive()) send(message)</code> chưa đủ nếu xóa có thể xảy ra giữa hai thao tác. Ở một JVM có thể dùng read/write lock hoặc cơ chế serialize admission và mark-deleting. Với nhiều pod, phải dùng **trạng thái bền vững có version/CAS**, partition ownership hoặc coordination chung. Local <code>synchronized</code> không chặn được producer trên JVM khác.

| Nguồn vào | Cách quiesce phù hợp | Cẩn trọng |
|---|---|---|
| HTTP/gateway chung nhiều tenant | Router chặn tenant đang DELETING trước khi gọi dynamic flow | Không tắt cả gateway chung |
| Kafka/JMS/AMQP container riêng tenant | Pause/stop consumer riêng hoặc gỡ listener subscription có kiểm soát | ACK, redelivery, requeue và partition ownership phụ thuộc adapter |
| Polling inbound adapter riêng tenant | Ngừng poll mới của endpoint đó | Task đã lấy message có thể vẫn đang xử lý |
| Shared input channel có router theo tenant | Chặn route tới tenant, giữ đường xử lý cho tenant khác | Không remove bean channel chung |
| Scheduler/callback tự tạo | Hủy lịch tương lai, chặn callback mới theo generation | Callback đã bắt đầu vẫn có thể chạy |

Không nên dùng <code>registration.stop()</code> làm **bước duy nhất** để ngăn toàn bộ ingress; nó không thay thế kiểm tra tenant ở nguồn chung hoặc ở những API bên ngoài trực tiếp gọi service. Quyết định với message đến sau mốc DELETING phải rõ: từ chối, ACK và bỏ qua hợp lệ, NACK/redeliver hay chuyển DLQ/quarantine. Không ACK “đã xử lý thành công” cho một message nghiệp vụ còn bắt buộc phải bảo toàn.

## 7. Bước 2 — Drain in-flight và xử lý pending message

Sau khi không có **công việc mới được nhận**, cần xử lý công việc đã được tiếp nhận trước mốc xóa.

| Trạng thái công việc | Lựa chọn | Điều phải ghi nhận |
|---|---|---|
| Handler đang chạy đồng bộ | Cho hoàn tất hoặc timeout/cancel có kiểm soát | Số in-flight, transaction outcome |
| Task đã giao cho executor | Chờ queue/task chạy xong hoặc chuyển sang quarantine | <code>send()</code> thành công không đồng nghĩa task đã hoàn tất |
| <code>QueueChannel</code> in-memory | Drain trước shutdown, hoặc chấp nhận mất khi policy cho phép | Không có persistence qua restart |
| Queue dùng <code>JdbcChannelMessageStore</code> | Drain/di chuyển theo API và transaction của queue | Không DELETE raw row khi consumer còn nhận |
| Delayer còn message chưa tới hạn | Hủy có kiểm toán, phát sớm có chủ đích hoặc chuyển kho bền vững | <code>messageGroupId</code>, lịch đã tạo, deadline |
| Aggregator/resequencer còn pending group | Chờ đủ phần, force complete hoặc quarantine các fragment | Correlation key, partial/discard policy, group status |
| Retry/backoff đang chờ | Cho kết thúc hoặc chặn attempt mới theo tenant state | Không chạy lại sau DELETED |
| DLQ/error message/outbox | Lưu theo retention hoặc xử lý hồi phục | Không mặc định xóa vĩnh viễn |

**Định nghĩa “drained” phải đo bằng completion thực**, ví dụ handler kết thúc, ACK và transaction/commit phù hợp đã hoàn tất. Đếm số lần <code>send()</code> trả về không có ý nghĩa nếu flow có <code>ExecutorChannel</code> hoặc consumer reactive.

### Timeout là quyết định nghiệp vụ, không phải “đã drain”

Nếu hết ngân sách chờ, có ba phương án phổ biến:

1. **Tiếp tục chờ và giữ tenant ở DELETING/DRAINING**; phù hợp công việc quan trọng không được mất.
2. **Chuyển pending work sang quarantine/DLQ bền vững**, ghi đủ correlation, lý do và người sở hữu replay; chỉ tiếp tục cleanup khi chuyển thành công.
3. **Hủy công việc theo chính sách được phê duyệt**, ghi audit và không giả định resource ngoài đã rollback.

Không bao giờ ghi <code>inFlight=0</code> bằng cách reset counter để vượt qua điều kiện drain. Cần phân biệt active handler, scheduled task, broker delivery và dữ liệu đã persist nhưng chưa có consumer.

## 8. Bước 3 — Stop, destroy đúng flow và tránh hủy nhầm

Sau khi admission đã đóng, in-flight đã kết thúc hoặc được chuyển sang đường phục hồi phù hợp, ta mới dừng và gỡ flow.

~~~java
public void unregisterTenantFlow(UUID tenantId) {
    String id = tenantFlowFactory.flowId(tenantId);

    var registration = flowContext.getRegistrationById(id);
    if (registration == null) {
        // Có thể đã được destroy hoặc chưa rebuild sau restart.
        return;
    }

    registration.stop();
    registration.destroy();
    // Không gọi thêm flowContext.remove(id) cho cùng registration.
}
~~~

Đây là **phần cuối** của quy trình cleanup, không phải toàn bộ quy trình. Từ một nơi khác, ứng dụng có thể dùng <code>flowContext.remove(id)</code> như một cách gỡ tương đương; hãy chọn **một** đường destroy theo ID và nhất quán khi retry.

Trong trường hợp có nhiều flow cho một tenant (inbound, outbound, scheduler, error processing), cần registry nghiệp vụ liệt kê **tất cả flow ID** theo tenant/generation và dọn theo thứ tự phụ thuộc. Không tìm tên bean bằng phép so chuỗi mơ hồ như <code>startsWith(tenantId)</code> rồi destroy hàng loạt khi namespace không được kiểm soát.

### Vì sao cần prefix flow ID?

Nhiều tenant có thể cùng sử dụng một cấu trúc:

~~~text
tenant.flow.A1.handler
tenant.flow.A1.channel
tenant.flow.B2.handler
tenant.flow.B2.channel
~~~

<code>.id(id).useFlowIdAsPrefix()</code> giúp bean do dynamic flow tạo ra có tên khác nhau khi các endpoint bên trong dùng tên tương tự. Nhưng các bean **đã khai báo global** vẫn có vòng đời độc lập. Không được kết luận từ tiền tố tên rằng mọi bean chứa tiền tố đó đều là tài nguyên được phép xóa.

## 9. Bước 4 — Dọn resource theo ownership, không theo vị trí tham chiếu

Các tài nguyên ứng dụng tự tạo cần có **cleanup hook** rõ ràng, ví dụ:

~~~java
public interface TenantResourceLease extends AutoCloseable {
    UUID tenantId();
    String resourceName();
    @Override void close() throws Exception;
}
~~~

Một <code>TenantResourceRegistry</code> do ứng dụng xây dựng có thể lưu các lease riêng tenant, ghi lại owner và đảm bảo mỗi lease chỉ đóng một lần theo chính sách. Khi destroy flow, chỉ close lease thực sự được tạo cho tenant đó.

**Cần phân biệt**:

- Nếu một connection factory riêng tenant được builder <code>.addBean(...)</code> đăng ký làm bean phụ thuộc, vòng đời bean đó có thể đã được xử lý khi registration destroy. Không vừa đăng ký phụ thuộc vừa tự <code>close()</code> hai lần nếu thư viện không hỗ trợ idempotent close.
- Nếu sử dụng singleton connection pool/shared scheduler toàn ứng dụng, **không** đưa nó vào registry cleanup của tenant.
- Nếu ứng dụng tự khởi tạo <code>ScheduledFuture</code>, <code>Disposable</code> của Reactor, thread riêng hoặc callback registration không phải bean phụ thuộc, cần huỷ những handle này đúng cách.
- Nếu dùng dynamic listener/consumer của broker, phải xác nhận listener đã unregister hoặc unsubscribe theo API của adapter/container, không chỉ mất reference Java.

Một mẹo tốt là lập bảng **resource → owner → create action → close action → hậu điều kiện** ngay tại thời điểm provision tenant. Cleanup lúc xóa chỉ thực thi những action đã được xác định trước, thay vì đi dò toàn bộ Spring context để suy đoán.

## 10. Bước 5 — Pending group, message store và retry sau khi flow biến mất

<code>IntegrationFlowContext.remove()</code> **không phải** câu lệnh xóa toàn bộ dữ liệu tenant. Persistent state vẫn có thể tồn tại trong:

- <code>JdbcMessageStore</code>/<code>MessageGroupStore</code> cho aggregator, resequencer, delayer;
- <code>JdbcChannelMessageStore</code> cho queue;
- Redis/MongoDB store và delayed/scheduled messages;
- broker topic/queue, consumer offset, retry topic, DLQ;
- outbox, inbox, audit event và bảng idempotency.

**Không xóa thẳng các bản ghi trong bảng <code>INT_MESSAGE</code>/<code>INT_MESSAGE_GROUP</code> theo một điều kiện <code>LIKE '%tenant%'</code>**. Schema/quan hệ group, locking và transaction của store có thể khiến xóa raw row làm mất công việc hoặc gây lỗi cho consumer còn chạy.

### Thiết kế key và region cho cleanup chính xác

Khi tạo dynamic flow, nên có namespace ổn định theo tenant và generation:

~~~text
flowId          = tenant.flow.<tenantUUID>.<generation>
delayGroupId    = tenant.delay.<tenantUUID>.<generation>
aggregateRegion = tenant.aggregate.<tenantUUID>.<generation>
correlationKey  = <tenantUUID>:<batchId>
retryKey        = <tenantUUID>:<businessEventId>
~~~

Đây là **quy ước ứng dụng**, không phải yêu cầu tên chuẩn của Spring Integration. Với <code>MessageGroupStore</code> dùng chung, region/partition cần được hỗ trợ đúng cách bởi implementation và dùng nhất quán với correlating handler. Không chỉ nối <code>tenantId</code> vào một header rồi giả định store có API “xóa mọi message của tenant” an toàn.

**Khi nào được xóa dữ liệu?** Sau khi không còn consumer/producer có thể ghi vào partition đó, đã xác định pending message cần xử lý thế nào và đã tuân thủ retention/audit yêu cầu. Thao tác thực tế phải dùng API, transaction hoặc job migration/purge phù hợp với store cụ thể, không phải chỉ destroy bean.

### Error flow dùng chung là một bẫy

Một global <code>errorChannel</code> có thể vẫn nhận lỗi từ task đã chạy hoặc từ adapter sau khi tenant flow bị xóa. Error consumer phải xử lý theo <code>tenantId</code>, <code>generation</code> và trạng thái tenant:

- Không khởi tạo lại flow đã xóa chỉ vì một exception retry xuất hiện muộn.
- Không dùng lại credentials của tenant đã thu hồi.
- Không coi <code>ErrorMessage</code> là xác nhận công việc đã rollback hoặc đã lưu bền vững.
- Vẫn giữ correlation và failed/original message metadata ở mức được phép để điều tra.

## 11. Transaction và tính nhất quán của toàn bộ quy trình

Việc xóa tenant bao gồm nhiều hệ thống: database nghiệp vụ, Spring application context, broker, message store, scheduler, secret manager, object storage. **Một transaction JDBC không thể nguyên tử bao phủ toàn bộ quá trình ấy** nếu không có kiến trúc transaction phân tán đặc thù.

Một hướng thiết kế an toàn:

1. Trong **transaction ngắn**, thực hiện CAS <code>ACTIVE → DELETING</code>, ghi deletion job và outbox event.
2. Worker đọc job và bắt đầu từng bước cleanup idempotent.
3. Sau mỗi bước thành công, ghi checkpoint bền vững.
4. Nếu bước nào lỗi, để job ở trạng thái có thể retry với backoff; không reset tenant về ACTIVE một cách âm thầm.
5. Chỉ đánh dấu <code>DELETED</code> khi hậu điều kiện đã được kiểm chứng.

~~~mermaid
sequenceDiagram
    participant API as Tenant API
    participant DB as Tenant lifecycle DB
    participant W as Cleanup worker
    participant SI as IntegrationFlowContext
    participant EXT as Store / Broker / Resources
    API->>DB: CAS ACTIVE → DELETING + tạo job
    DB-->>API: accepted + deletionRequestId
    W->>DB: claim job theo tenant/generation
    W->>EXT: chặn ingress và drain
    EXT-->>W: drained / archived
    W->>SI: registration.stop() / destroy()
    SI-->>W: flow unregistered
    W->>EXT: cleanup resource thuộc tenant
    EXT-->>W: cleanup result
    W->>DB: checkpoint + DELETED khi đủ điều kiện
~~~

**Không đặt toàn bộ các bước trên trong một method <code>@Transactional</code> rồi giữ transaction mở trong lúc đợi executor hoặc broker.** Làm vậy có thể giữ DB lock lâu mà vẫn không có rollback nguyên tử cho tài nguyên ngoài.

## 12. Race condition khi tenant bị xóa và được tạo lại

Một trường hợp khó là:

~~~text
T1: cleanup của tenant A, generation=7 bắt đầu
T2: yêu cầu tạo mới tenant A được chấp nhận, generation=8
T1: cleanup chậm thực hiện DELETE theo tenantId
T3: tài nguyên của generation=8 bị xóa nhầm
~~~

Cách phòng ngừa:

- Dùng **deletion generation/version** trong job và tên resource, không chỉ tenant ID.
- Các thao tác cleanup phải kiểm tra owner/generation trước khi xóa.
- Quy định rõ **không cho tái tạo cùng tenant ID** trước khi cleanup cũ kết thúc, hoặc dùng ID/generation mới và phân tách resource tuyệt đối.
- Serialize provision/delete theo tenant với CAS và, nếu nhiều node, dùng distributed coordination phù hợp.
- Sau crash/restart, cleanup worker chỉ resume job ở đúng generation; không suy luận bằng tên hiện tại của tenant.

<code>LockRegistry</code> có thể hỗ trợ loại trừ khi nhiều worker cùng cleanup một tenant, nhưng **không tự thay cho CAS/version của DB**: nếu lease hết hạn hoặc có stale worker, điều kiện xóa theo generation ở tài nguyên đích vẫn cần thiết.

## 13. Restart ứng dụng trong lúc cleanup

Dynamic registration nằm trong application context của một tiến trình; nó không phải một cấu hình runtime được Spring Integration tự khôi phục nguyên vẹn từ database sau khi JVM restart. Ứng dụng phải có **nguồn cấu hình bền vững** để rebuild các flow còn được phép chạy.

Khi startup, một reconciler của ứng dụng nên:

| Trạng thái tenant/job trong DB | Hành vi khởi động |
|---|---|
| <code>ACTIVE</code> | Rebuild flow tương ứng theo cấu hình đã lưu, kiểm tra trùng ID rồi start |
| <code>DELETING</code>/<code>DRAINING</code> | **Không** cho nhận message mới; tiếp tục cleanup/recovery job |
| <code>CLEANUP_FAILED</code> | Retry có điều kiện hoặc đưa ra vận hành; không tự start như tenant ACTIVE |
| <code>DELETED</code> | Không rebuild flow; kiểm tra còn resource rò rỉ theo retention policy |

Thứ tự startup quan trọng: có thể cần mở channel/flow ở trạng thái <code>autoStartup(false)</code>, nạp configuration, kiểm tra tenant state, rồi mới cho adapter/gateway nhận message. Nếu adapter start trước admission gate, có thể lọt message thuộc tenant đang bị xóa vào flow mới.

Với message còn nằm trong persistent store, cần quyết định rõ có khôi phục xử lý để drain/quarantine hay không. **Đừng tự động hồi sinh flow tenant đã bị xóa** chỉ để “dọn cho sạch”, vì việc này có thể kích hoạt side effect và credentials đã bị thu hồi.

## 14. Ví dụ orchestrator cleanup có checkpoint

Đoạn mã sau là **khung tích hợp với các port của ứng dụng**. Nó thể hiện thứ tự đúng; các interface <code>TenantLifecycleRepository</code>, <code>TenantIngressController</code>, <code>TenantWorkDrain</code>, <code>TenantPendingWorkPolicy</code> và <code>TenantOwnedResources</code> là hợp đồng ứng dụng **phải tự triển khai**, không phải API sẵn có của Spring Integration.

~~~java
@Service
public class TenantCleanupCoordinator {
    private final TenantLifecycleRepository lifecycle;
    private final TenantIngressController ingress;
    private final TenantWorkDrain drain;
    private final TenantPendingWorkPolicy pending;
    private final TenantFlowFactory factory;
    private final IntegrationFlowContext flowContext;
    private final TenantOwnedResources ownedResources;

    public TenantCleanupCoordinator(
            TenantLifecycleRepository lifecycle,
            TenantIngressController ingress,
            TenantWorkDrain drain,
            TenantPendingWorkPolicy pending,
            TenantFlowFactory factory,
            IntegrationFlowContext flowContext,
            TenantOwnedResources ownedResources) {
        this.lifecycle = lifecycle;
        this.ingress = ingress;
        this.drain = drain;
        this.pending = pending;
        this.factory = factory;
        this.flowContext = flowContext;
        this.ownedResources = ownedResources;
    }

    public void cleanup(UUID tenantId, long generation) {
        // CAS/idempotency trong DB: không chạy nếu generation đã thay đổi.
        lifecycle.ensureDeleting(tenantId, generation);

        ingress.blockNewMessages(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "INGRESS_BLOCKED");

        // Phải đếm completion của handler, không đếm số lần send() thành công.
        drain.awaitQuiescence(tenantId, generation, Duration.ofSeconds(30));

        // Chính sách nghiệp vụ: process, archive hoặc quarantine pending work.
        pending.settleAndVerify(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "QUIESCED");

        var registration =
            flowContext.getRegistrationById(factory.flowId(tenantId));
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
        lifecycle.checkpoint(tenantId, generation, "FLOW_REMOVED");

        ownedResources.closeTenantOnly(tenantId, generation);
        lifecycle.checkpoint(tenantId, generation, "RESOURCES_CLOSED");

        lifecycle.markDeletedIfComplete(tenantId, generation);
    }
}
~~~

<code>Duration</code> thuộc <code>java.time</code>. Trong production, cùng một flow ID có thể tái sử dụng khi generation đổi, nên **nếu cho phép tái tạo cùng tenant**, hàm <code>flowId</code> phải tính cả generation hoặc cleanup phải xác minh registration đang thuộc đúng generation trước khi destroy. Đoạn code trên giả định không tái tạo tenant ID cho tới khi cleanup cũ hoàn tất.

Để quy trình idempotent thực sự, mỗi port phải xử lý “bước đã hoàn tất” hợp lệ, retry sau crash và trạng thái resource đã không còn. <code>awaitQuiescence()</code> có thể ném lỗi khi timeout; khi đó worker ghi <code>CLEANUP_FAILED</code>/checkpoint và không chuyển sang <code>DELETED</code>.

## 15. Chẩn đoán resource leak và xác nhận cleanup

Không được kết luận cleanup thành công chỉ vì <code>getRegistrationById(id) == null</code>. Flow có thể đã gỡ khỏi context trong khi còn task, thread, connection hoặc message tồn đọng.

| Triệu chứng | Giả thuyết | Bằng chứng nên thu thập |
|---|---|---|
| Flow không còn nhưng CPU vẫn tăng | Custom scheduler/executor hoặc task đã giao chưa dừng | Thread dump, executor active/queue, scheduled handles |
| Tenant đã DELETED vẫn có message mới | Ingress gate ở một pod chưa áp dụng, broker redelivery, callback cũ | Log tenant state/generation, consumer offset, adapter lifecycle |
| Tenant khác bị gián đoạn sau cleanup | Đã đóng shared connection factory/scheduler/channel | Ownership map, bean lifecycle log, health của tenant khác |
| JDBC store vẫn có message cũ | Persistent store không bị dọn bởi destroy | Region, group ID, pending/quarantine metrics |
| Có duplicate business side effect | Retry sau crash, không có idempotency, drain chỉ đếm send | Event ID, transaction log, outbox/inbox |
| Không thể đăng ký flow mới cùng tên | Registration cũ chưa destroy, hoặc bean ID xung đột | <code>getRegistry()</code>, ID/prefix đang sử dụng |
| Delete API treo | Chờ mãi in-flight, deadlock, broker ACK không hoàn tất | Deadline, lock wait, handler stack, queue depth |
| Cleanup bị chạy hai lần trên cluster | Không có claim/CAS hoặc distributed lock bị mất lease | Job owner, generation, transaction/version |
| Message bị gửi tới tenant khác | Router hoặc cached input channel trỏ nhầm flow | Routing key, per-tenant registration ID, validation trong handler |

Metric tối thiểu nên có:

- số tenant ở từng trạng thái <code>ACTIVE/DELETING/CLEANUP_FAILED/DELETED</code>;
- số dynamic flow đang đăng ký so với số tenant ACTIVE;
- in-flight handler, queue depth, delayed message, pending group và retry count theo tenant **với giới hạn cardinality**;
- thời gian drain, thời gian remove flow, số lỗi cleanup theo bước;
- executor active threads, scheduled task count, connection/session count trước/sau xóa;
- số message còn phát sinh với generation đã bị thu hồi.

Không gắn raw tenant ID có cardinality lớn hoặc dữ liệu nhạy cảm trực tiếp vào mọi label metric. Có thể đưa tenant ID vào trace/log truy cập hạn chế để chẩn đoán, còn metric tổng hợp theo loại resource, bước cleanup hoặc nhóm tenant.

## 16. Kiểm thử xóa tenant khi đang có message

Bộ kiểm thử cần mô phỏng **đúng ranh giới bất đồng bộ**, không chỉ gọi <code>registration.destroy()</code> rồi kiểm tra context.

| Tình huống | Điều phải xác nhận |
|---|---|
| Tenant không còn message | Flow bị gỡ, resource riêng đã đóng, tenant khác vẫn chạy |
| Có handler đồng bộ đang chạy | Admission đóng; công việc đã nhận được kết thúc hoặc xử lý theo timeout policy |
| Có task trong <code>ExecutorChannel</code> | Drain theo completion thực, không kết luận từ <code>send()</code> |
| Có queue/message store bền vững | Pending work được settle/quarantine; không xóa hàng loạt thiếu transaction |
| Có Delayer còn message hẹn giờ | Không xuất hiện side effect của tenant đã xóa sau deadline |
| Aggregator còn pending group | Group được force complete, archive hoặc giữ theo retention đã chọn |
| Broker redeliver sau markDeleting | Adapter/router áp dụng chính sách đúng, không xử lý bất hợp lệ |
| Cleanup lỗi ở bước đóng resource | Giữ checkpoint, retry không đóng nhầm singleton |
| Hai lệnh xóa cùng tenant | Một cleanup owner, các lệnh sau nhận cùng trạng thái/job |
| Xóa và provision đồng thời | Không có flow generation mới bị cleanup cũ destroy |
| JVM restart giữa cleanup | Reconciler không rebuild tenant DELETING và có thể resume job |
| Tenant khác chia sẻ scheduler/connection | Tenant đó không bị dừng hoặc mất kết nối |

### Phác thảo integration test cho API remove

~~~java
@Test
void dynamicFlowCanBeRemovedWithoutTouchingAnotherTenant() {
    UUID tenantA = UUID.randomUUID();
    UUID tenantB = UUID.randomUUID();

    var a = tenantFlowFactory.create(tenantA);
    var b = tenantFlowFactory.create(tenantB);

    assertNotNull(flowContext.getRegistrationById(a.getId()));
    assertNotNull(flowContext.getRegistrationById(b.getId()));

    a.stop();
    a.destroy();

    assertNull(flowContext.getRegistrationById(a.getId()));
    assertNotNull(flowContext.getRegistrationById(b.getId()));

    b.destroy();
}
~~~

Test này chỉ chứng minh API lifecycle cơ bản trong **một application context**. Nó chưa chứng minh admission/transaction, drain của executor, cleanup dữ liệu bền vững hoặc an toàn cluster. Những yêu cầu đó cần integration test riêng với broker/database thật hoặc Testcontainers, latch/timeout để điều khiển in-flight work, failure injection và xác nhận trạng thái sau restart.

## 17. Checklist production khi tenant bị xóa

- [ ] Có trạng thái <code>DELETING</code> bền vững và idempotent deletion job với tenant generation/version.
- [ ] Chặn ingress ở **mọi đường vào**, gồm HTTP/router chung, broker, poller và callback tự tạo.
- [ ] Định nghĩa tiêu chí drained theo **completion/ACK/commit**, không chỉ số lần <code>send()</code> trả về.
- [ ] Quyết định trước số phận queue, delayed message, pending group, retry, DLQ, outbox và audit theo retention policy.
- [ ] Dùng <code>registration.stop()</code> rồi <code>destroy()</code> hoặc <code>flowContext.remove(id)</code> đúng đối tượng; không double-destroy.
- [ ] Flow ID, region, correlation key và namespace ổn định; generation ngăn cleanup cũ phá resource mới.
- [ ] Chỉ đóng resource **thuộc riêng tenant**; shared executor, scheduler, channel, connection factory phải còn hoạt động.
- [ ] Có checkpoint để retry khi cleanup lỗi giữa chừng; reconciler không rebuild tenant DELETING sau restart.
- [ ] Error/retry flow nhận biết tenant đã xóa; không tái khởi tạo flow ngoài ý muốn.
- [ ] Có metric và cảnh báo resource leak, pending message và cleanup thất bại; kiểm thử đồng thời nhiều tenant và nhiều node.

**Kết luận:** Xóa tenant khỏi dynamic runtime là một quá trình **quiesce → drain hoặc quarantine → unregister flow → cleanup owned resource → xác minh**. <code>IntegrationFlowContext</code> quản lý vòng đời definition và bean phụ thuộc, còn ứng dụng chịu trách nhiệm với message đang chạy, persistent state, nguồn bên ngoài và ranh giới sở hữu. Khi kết hợp admission gate, state machine bền vững, idempotency, generation fencing và kiểm thử restart/concurrency, việc xóa tenant sẽ không làm mất công việc không chủ đích hoặc ảnh hưởng các tenant còn hoạt động.

## Tài liệu tham khảo

- [Spring Integration Reference — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration 6.5 Javadoc — IntegrationFlowContext](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Integration 6.5 Javadoc — IntegrationFlowRegistration](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/context/IntegrationFlowContext.IntegrationFlowRegistration.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Framework Reference — Application Context Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
