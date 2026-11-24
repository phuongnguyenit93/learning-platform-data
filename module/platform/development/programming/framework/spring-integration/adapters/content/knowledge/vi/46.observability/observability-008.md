# JMX quản trị endpoint runtime trong Spring Integration Adapters

## 1. Bối cảnh: vì sao cần điều khiển endpoint khi ứng dụng đang chạy?

Trong Spring Integration, một luồng tích hợp có thể nhận dữ liệu từ **File, SFTP, HTTP, JMS, AMQP, Kafka hoặc database**, đi qua **MessageChannel**, transformer, router, filter, service activator rồi gửi tới hệ thống đích bằng **outbound adapter/gateway**. Khi một hệ thống ngoài chậm, connector mất kết nối hoặc nhận được dữ liệu sai hàng loạt, đội vận hành thường cần trả lời ngay:

- Inbound adapter có đang chạy và nhận message mới không?
- Poller có tiếp tục đọc file/bản ghi dù downstream đã quá tải không?
- Handler, consumer hoặc MessageChannel đang xử lý bao nhiêu message?
- Có thể **tạm dừng đầu vào**, quan sát backlog rồi mở lại mà không cần restart toàn bộ JVM không?
- Những thay đổi runtime tác động tới node nào trong một cụm nhiều instance?
- Sau khi thao tác qua JMX, liệu message **in-flight**, transaction, offset, phiên broker và dữ liệu chưa xử lý có được bảo toàn không?

**Java Management Extensions (JMX)** là cơ chế quản trị và quan sát đối tượng trong JVM thông qua **MBean**. Trong Spring Integration, JMX có thể giúp nhìn thấy thông tin một số thành phần tích hợp và, **khi bean/phiên bản thực sự expose thao tác phù hợp**, hỗ trợ thay đổi vòng đời runtime của endpoint. Bài thuộc chương **Observability** của module **SPRING_INTEGRATION_ADAPTERS**, liên hệ trực tiếp tới inbound/outbound adapter, gateway, poller, MessageChannel, **hợp đồng message, lỗi và vòng đời kết nối**.

Mục tiêu không phải “mở mọi thao tác JMX cho người vận hành”. Mục tiêu là **quan sát được trạng thái thực và thực hiện thay đổi có kiểm soát khi cần**, với bảo mật, phê duyệt, kiểm chứng và khôi phục rõ ràng.

> **Giới hạn quan trọng:** Không phải mọi endpoint đều có cùng các thuộc tính hoặc thao tác `start`/`stop` trên JMX. MBean, ObjectName, metric, operation và cách enablement khác nhau theo Spring Integration/Spring Boot version, loại bean và cấu hình exporter. Mọi ví dụ phải được kiểm chứng bằng MBeanInfo của **ứng dụng thực tế** trước khi tự động hóa.

### Mục tiêu học tập

1. Giải thích **JMX, MBeanServer, ObjectName, attribute, operation** và quan hệ với Spring Integration endpoint.
2. Bật và kiểm tra exposure của **Integration MBean** mà không nhầm với Spring Boot Actuator JMX.
3. Phân biệt **quan sát trạng thái** với **start/stop/pause** và tác động tới message in-flight.
4. Xây runbook an toàn cho File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC và các loại channel.
5. Quản trị nhiều instance, quyền truy cập, audit, change/incident và thao tác khôi phục.
6. Kết hợp JMX với Micrometer, logs, traces, MessageHistory và metric phía broker/target.

## 2. JMX là gì?

JMX là cơ chế quản lý/giám sát các tài nguyên Java trong một JVM. Thành phần được quản lý có thể được hiển thị dưới dạng **MBean** với metadata và khả năng mà MBean đó công bố.

| Khái niệm | Vai trò | Gợi ý sử dụng |
|---|---|---|
| **MBean** | Đối tượng quản lý có thuộc tính và/hoặc thao tác | Một endpoint/handler/bean được export |
| **MBeanServer** | Registry trong JVM chứa MBeans và xử lý truy vấn/invoke | Điểm trung gian của công cụ quản trị |
| **ObjectName** | Danh tính MBean theo domain và key properties | Tìm đúng bean, đúng JVM |
| **Attribute** | Giá trị có thể đọc hoặc, nếu được expose, có thể ghi | Trạng thái chạy, count, config cụ thể |
| **Operation** | Phương thức MBean cho phép gọi | Chỉ có khi được export; có thể thay đổi runtime |
| **Notification** | Sự kiện MBean có thể phát ra nếu hỗ trợ | Theo dõi thay đổi; không phải mọi bean đều phát |
| **JMX client** | JConsole, VisualVM, công cụ monitoring hoặc client Java | Đọc MBeanInfo và giá trị |
| **JMX exporter** | Xuất một tập bean Java thành MBean | Cấu hình exposure với scope và security |

### 2.1. Ví dụ về ObjectName

Một MBean có thể được hiển thị dưới dạng:

~~~text
<domain>:type=<type>,name=<component-name>,...
~~~

Đây chỉ là **mẫu minh họa**, không phải ObjectName cố định của Spring Integration. **Không hardcode** một domain, tên loại MBean hoặc một thuộc tính theo ví dụ trên nếu chưa khám phá cấu hình và version đang chạy.

### 2.2. JMX nội bộ JVM khác remote JMX

**Local JMX** cho phép quan sát MBeans của JVM tại môi trường được phép truy cập. **Remote JMX** mở đường quản trị từ mạng tới JVM và tạo thêm bề mặt tấn công. Khi remote được bật, cần cơ chế bảo mật thực sự: giới hạn mạng, authentication/authorization, TLS hoặc đường kết nối được bảo vệ, không sử dụng cấu hình bỏ xác thực/bỏ mã hóa để “debug nhanh”.

## 3. MBean trong Spring Integration: quan sát và thao tác

Các bean Spring Integration có thể gồm:

- **MessageChannel:** đường chuyển message giữa endpoints.
- **Inbound channel adapter:** nhận message, poll hoặc lắng nghe nguồn.
- **Inbound gateway:** nhận request và tạo reply flow.
- **Message handler/outbound adapter:** chuyển đổi, gọi API, publish, lưu tài nguyên.
- **Polling consumer/SourcePollingChannelAdapter:** phối hợp poller và source.
- **Event-driven consumer/message producer:** nhận hoặc phân phối message theo sự kiện.
- **IntegrationFlow:** mô tả cấu trúc luồng; không đồng nghĩa bản thân flow là một MBean có start/stop.

Spring Integration có cơ chế JMX management như **`IntegrationMBeanExporter`** và cấu hình enablement tương ứng ở các phiên bản có hỗ trợ. **Phải phân biệt bean được đưa vào Spring context, bean được quản lý qua Spring Integration và bean thực sự được export thành MBean**.

### 3.1. Hai nhóm khả năng cần xem riêng

| Nhóm | Ví dụ khái niệm | Nguyên tắc |
|---|---|---|
| **Read-only observation** | `isRunning`, send/receive count, error count, component info | Đọc được gì phụ thuộc MBeanInfo |
| **State-changing management** | `start`, `stop`, setter hoặc operation điều khiển | Chỉ gọi khi MBean expose và có quyền/change |

Không suy rằng thuộc tính `running=true` có nghĩa “không có lỗi”. Có endpoint đang hoạt động nhưng không nhận dữ liệu vì remote source rỗng, session hỏng, queue nghẽn hoặc poller không có task chạy.

### 3.2. Tại sao các thao tác runtime cần kiểm soát?

`stop` một source có thể ngừng nhận đầu vào mới, nhưng chưa chắc dừng xử lý các message đã vào queue. Ngược lại, `stop` consumer có thể để queue tồn đọng và không còn ai lấy message. Với một broker listener, thay đổi lifecycle còn liên quan tới consumer group, message acknowledgment, rebalance và khả năng giao lại.

**Đọc được operation không đồng nghĩa operation vô hại.** Mọi invocation phải qua quy trình thay đổi/incident, có bằng chứng trước–sau và phương án khôi phục.

## 4. Kiến trúc quan sát và điều khiển qua JMX

~~~mermaid
flowchart LR
    EXT[File / SFTP / HTTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Endpoint]
    IN --> CH[MessageChannel]
    CH --> H[Handler / Router / Transformer]
    H --> OUT[Outbound Endpoint]
    OUT --> TARGET[Remote System]
    IN -. management info .-> MX[MBeanServer trong JVM]
    CH -. management info .-> MX
    H -. management info .-> MX
    OUT -. management info .-> MX
    CLIENT[JMX Client được ủy quyền] -->|Query / Invoke| MX
    MX -. Attributes / Operations .-> CLIENT
    IN --> MET[Metrics / Logs / Traces]
    OUT --> MET
    TARGET --> MET
    MET --> CHECK[Kiểm chứng kết quả & audit]
    CLIENT --> CHECK
~~~

JMX cung cấp góc nhìn **của JVM/bean**. Nếu ứng dụng có ba replicas, bạn có thể đang nhìn thấy **chỉ một replica**. Broker, source SFTP, database và remote HTTP service thường có trạng thái riêng, không được suy ra đầy đủ từ MBean của adapter.

### 4.1. Đơn vị tác động là thành phần trong process

Một operation `stop` trên endpoint ở node A **không tự động dừng endpoint cùng tên ở node B**, trừ khi dự án chủ động có cơ chế điều phối riêng. Với rollout nhiều pod/VM, phải xác định instance, deployment, trách nhiệm lease/lock và cách tránh duplicate polling.

## 5. Bật JMX export cho Spring Integration

Trong các phiên bản Spring Integration có hỗ trợ, có thể sử dụng annotation **`@EnableIntegrationMBeanExport`** để cấu hình export các MBean integration. Ví dụ khai báo mang tính khởi đầu:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationMBeanExport;

@Configuration
@EnableIntegration
@EnableIntegrationMBeanExport
public class IntegrationJmxConfiguration {
    // Kiểm tra MBeans thực sự xuất hiện với version đang dùng.
}
~~~

**Chú ý version:** annotation, bean exporter, domain mặc định và các thành phần được export phải được kiểm tra trên bản Spring Integration đang dùng. Ứng dụng Spring Boot có thể đã tạo cơ chế management/export phù hợp qua auto-configuration; tránh thêm cấu hình trùng mà chưa hiểu tác động.

### 5.1. Phân biệt `@EnableIntegrationManagement` với export JMX

| Cơ chế | Mục đích chính | Điều không tự đảm bảo |
|---|---|---|
| **Integration management/observation** | Instrument channel/handler và các tín hiệu quản lý/metrics tùy version | Không chắc một MBean cụ thể xuất hiện |
| **Integration MBean export** | Đưa thành phần tích hợp vào JMX MBeanServer theo cấu hình | Không tự bật Prometheus hay distributed tracing |
| **Spring Boot Actuator** | Health/metrics/management endpoints qua transport được cấu hình | Không mặc định cho phép `start/stop` mọi adapter |
| **Custom MBean** | Expose một interface quản lý do ứng dụng định nghĩa | Không tự an toàn hoặc đúng lifecycle nếu tác giả chưa thiết kế |

Không nên chọn configuration chỉ dựa trên tên annotation. Trong quá trình triển khai cần xác minh được **MBean tồn tại, metadata chính xác, quyền truy cập đúng và operation có semantics như mong đợi**.

### 5.2. Với Spring Boot JMX

Spring Boot có thể cho phép export một số bean và Actuator endpoints tới JMX qua các cài đặt riêng (ví dụ `spring.jmx.enabled` và `management.endpoints.jmx.exposure.*` tùy version). **Cấu hình Actuator JMX endpoint exposure không đồng nghĩa kích hoạt Spring Integration MBeanExporter**. Hãy tách bài toán:

1. Boot/Actuator có đang đăng ký MBeans không?
2. Spring Integration exporter có đang đăng ký endpoint/channel không?
3. Có conflict về ObjectName/domain với exporter khác không?
4. Runtime JMX access có bị giới hạn đúng chính sách không?

### 5.3. Chỉ bật những gì thật sự cần

Nếu một môi trường chỉ cần metrics và health, không nhất thiết mở remote JMX có quyền invoke. Nên ưu tiên **read-only monitoring** và chỉ cung cấp quyền thay đổi state cho một workflow hoặc nhóm được ủy quyền.

## 6. Cách khám phá MBeans trước khi thiết kế runbook

Đừng bắt đầu bằng `invoke("stop")`. Một đợt khám phá an toàn nên:

1. Kết nối tới **JVM đúng** qua kênh được cấp phép.
2. Liệt kê các domain, ObjectName và bean liên quan Spring Integration.
3. Đọc **MBeanInfo** để xem attributes/operations thực sự được expose.
4. Xác định bean tương ứng với **component ID** trong IntegrationFlow.
5. Đọc vài attribute không thay đổi state, phân biệt count tích lũy và gauge hiện tại.
6. Ghi lại tên, type, description, khả năng đọc/ghi, signature của operation.
7. Kiểm tra MBean đúng instance/tenant/environment.
8. Chỉ đưa operation có quyền thay đổi trạng thái vào runbook sau khi thử ở môi trường kiểm thử.

### 6.1. Ví dụ Java chỉ đọc metadata MBean

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class LocalMBeanInspector {
    private LocalMBeanInspector() {}

    public static void inspectDomain(String domain) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName pattern = new ObjectName(domain + ":*");
        Set<ObjectName> names = server.queryNames(pattern, null);

        for (ObjectName name : names) {
            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean: " + name.getCanonicalName());
            for (MBeanOperationInfo operation : info.getOperations()) {
                System.out.println("  operation: " + operation.getName());
            }
        }
    }
}
~~~

**Đây là mã minh họa đọc metadata trong JVM đang chạy**, không phải client remote hay công cụ tự bật quyền. Chỉ truyền domain đáng tin/được phép. Với môi trường thật, không nên in toàn bộ ObjectName lên log công khai nếu chúng tiết lộ topology/tenant; cần chọn lọc và kiểm soát đầu ra.

### 6.2. Không giả định tên operation bằng method Java

Một Spring bean có method `start()` nhưng MBean chưa chắc export method đó. **MBeanInfo là nguồn mô tả operation thực sự**, còn việc gọi có được phép và tác động thế nào cần xác nhận bằng chính sách và test.

## 7. Đặt tên endpoint ổn định để dễ tìm qua JMX

Tên tự sinh của Spring Integration có thể thay đổi sau refactor hoặc khi tạo flow động. Một flow có endpoint ID tường minh dễ liên kết:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderIntegrationFlowConfiguration {
    @Bean
    IntegrationFlow ordersFlow() {
        return IntegrationFlow.from("ordersInput")
                .filter(String.class, s -> !s.isBlank(),
                        e -> e.id("validateOrderInput"))
                .transform(String.class, String::trim,
                        e -> e.id("normalizeOrderInput"))
                .handle(message -> {
                    // Xử lý nghiệp vụ; không log raw payload.
                }, e -> e.id("ordersSink"))
                .get();
    }
}
~~~

**Đặt ID giúp tìm component**, không bảo đảm mọi DSL endpoint trong ví dụ đều là lifecycle endpoint hoặc MBean. Khi một handler không expose stop/start, phải điều khiển đúng inbound/consumer endpoint upstream nếu đó là mục tiêu nghiệp vụ.

### 7.1. Quy tắc đặt tên

- Đặt theo chức năng: `invoiceSftpInbound`, `ordersKafkaConsumer`, `billingHttpOutbound`.
- Tránh chứa secrets, tên khách hàng, dữ liệu runtime, email hoặc file path.
- Giữ ổn định giữa deployments khi nhiệm vụ quản trị phụ thuộc tên.
- Nếu có nhiều instance, thêm **instance identity ở hệ inventory/monitoring**, không ép mọi component ID thay đổi theo message.
- Bảo đảm naming không xung đột khi có dynamic flows hoặc nhiều context.

## 8. Endpoint lifecycle trong Spring Integration

Các Spring Integration endpoints/producer/consumer có thể tham gia cơ chế **`Lifecycle`/`SmartLifecycle`** của Spring, nhưng **không phải mọi handler hoặc adapter có cùng hành vi lifecycle**. Một số endpoints được tạo và chạy cùng ApplicationContext, có khả năng start/stop; một số chỉ là logic xử lý, không có nguồn hoạt động riêng để dừng.

### 8.1. Bốn câu hỏi phải trả lời

1. Bean nào thực sự được **start/stop** — inbound producer, polling consumer, listener container hay handler?
2. `stop` có ngăn **nhận message mới**, ngăn **dispatch**, hay ngăn **gửi tới đích**?
3. Message đã **in-flight**, nằm trong queue, transaction hoặc broker unacked sẽ ra sao?
4. Sau `start`, có tái đọc file/record, rebalance Kafka, redelivery JMS/AMQP hoặc duplicate side effects không?

### 8.2. Tách ba trạng thái

| Trạng thái | Ví dụ | Tại sao quan trọng |
|---|---|---|
| **Bean lifecycle** | Endpoint báo `isRunning=true` | Chỉ phản ánh bean đang được coi là running |
| **Connectivity/health** | SFTP/HTTP/broker kết nối thành công | Running không bảo đảm network còn hoạt động |
| **Business progress** | Files/records được xử lý và xác nhận | Có thể running nhưng không có dữ liệu hoặc bị nghẽn |

Đóng một incident cần cả ba lớp khi phù hợp, không chỉ một cờ `isRunning`.

## 9. Start, stop, pause và drain khác nhau

Trong vận hành, bốn từ này hay bị dùng thay nhau nhưng có thể ảnh hưởng khác biệt:

| Hành động | Ý định | Điều phải kiểm chứng |
|---|---|---|
| **Start** | Cho endpoint tiếp tục hoạt động | Poll/listener thực sự chạy; không tạo duplicate |
| **Stop** | Dừng nguồn hoặc consumer theo semantics bean | Ngừng nhận message mới hay chỉ một bộ phận? |
| **Pause** | Tạm ngừng một phần việc, nếu framework/client hỗ trợ | Có giữ kết nối/assignment? Có tự resume? |
| **Drain** | Ngừng ingress và xử lý hết in-flight/backlog theo chiến lược | Khi nào được coi là drained? Transaction/ack đã hoàn tất? |

**JMX không cung cấp một nút “drain mọi luồng” phổ quát.** Drain thường là một quy trình phối hợp: chặn ingress, theo dõi queue/in-flight, xử lý checkpoint, xác nhận target rồi mới ngừng consumer theo từng adapter.

### 9.1. Đừng stop outbound adapter trước khi chặn ingress

Nếu inbound vẫn nhận 10.000 message/phút nhưng outbound bị stop, QueueChannel hoặc executor có thể đầy. Đổi thứ tự stop hợp lý phụ thuộc cấu trúc flow, nhưng thường cần:

1. Xem source và pending volume.
2. Quyết định ngừng hoặc throttle ingress.
3. Cho downstream xử lý những message cần hoàn tất.
4. Theo dõi queue age, in-flight và remote acknowledgment.
5. Chỉ stop thành phần còn lại khi không làm mất message/transaction.

Không áp dụng trình tự này một cách máy móc khi đang có credential compromise hoặc dữ liệu độc hại; trong sự cố an ninh, **containment** có thể ưu tiên cao hơn drain hoàn toàn.

## 10. SOP-JMX-01 — Kiểm tra trạng thái endpoint runtime

**Trigger:** hệ thống không nhận dữ liệu, cảnh báo backlog tăng, adapter lỗi kết nối hoặc sau deployment cần xác minh endpoint.

**Đầu vào:** incident/change ID, instance, environment, component ID, target system, symptom và quyền operator.

1. Xác nhận **ứng dụng/instance đúng**, thời gian và phiên bản deployment.
2. Mở JMX client qua kênh quản trị đã bảo vệ; xác định `ObjectName` bằng danh mục/MBeanInfo.
3. Đọc những thuộc tính có thật và được phép: running state, counters, counts hoặc gauges.
4. Đối chiếu Spring Integration endpoint ID với flow topology và adapter/gateway thực tế.
5. Kiểm tra **poller/listener/consumer** tương ứng, không chỉ MessageChannel.
6. Xem logs/metrics: lần poll cuối, queue depth, oldest age, handler error, retry, remote timeout.
7. Kiểm tra trạng thái bên ngoài: SFTP session/remote listing, Kafka lag, JMS/AMQP queue, DB connection/rows.
8. Kết luận sơ bộ: `RUNNING_NO_INPUT`, `STOPPED`, `DOWNSTREAM_BLOCKED`, `CONNECTION_FAILURE` hoặc `UNKNOWN`.
9. Chỉ yêu cầu điều khiển state nếu cần và có approval; nếu không, tiếp tục triage read-only.

### 10.1. Mẫu ghi nhận read-only

~~~yaml
observation_id: JMX-OBS-EXAMPLE-081
environment: staging
instance_ref: integration-worker-02
component_ref: invoiceSftpInbound
component_kind: inbound-channel-adapter
observed_at: "2026-11-23T15:30:00+07:00"
bean_running: true
poll_last_success_ref: poll-event-1081
source_file_age_bucket: 10m-30m
downstream_queue_age_bucket: 1m-5m
connectivity_status: CONNECTED
business_progress: DELAYED
evidence_refs:
  - jmx-snapshot-081
  - flow-dashboard-081
operator_decision: INVESTIGATE_DOWNSTREAM
~~~

**Ví dụ là bản ghi audit do ứng dụng/đội vận hành tự định nghĩa**, không phải cấu trúc JSON/YAML mặc định mà JMX tự xuất.

## 11. SOP-JMX-02 — Thay đổi trạng thái có kiểm soát

**Trigger:** đã xác minh cần dừng/tạm dừng/khởi động endpoint, ví dụ nguồn gửi liên tục dữ liệu hỏng hoặc downstream không chịu nổi tải.

### 11.1. Pre-change bắt buộc

1. Có **incident hoặc change ID**, mục tiêu cụ thể và người phê duyệt theo policy.
2. Chọn đúng **instance, component và operation**, đối chiếu `MBeanInfo`.
3. Kiểm tra actor có quyền và đủ thông tin vận hành; người đọc MBean không mặc nhiên được phép invoke.
4. Chụp **before snapshot**: state, source age, backlog, in-flight, error rate, external connection.
5. Xác định tác động tới ingress/egress, người dùng, transaction, retry và dữ liệu pending.
6. Xác định điều kiện khôi phục, thao tác rollback/restore và thời điểm kiểm tra tiếp.
7. Thông báo chủ ứng dụng/SRE/SOC nếu có security risk hoặc ảnh hưởng production.

### 11.2. Thực thi

- Thực hiện đúng operation đã được approve, không thử nhiều method không hiểu rõ.
- Ghi thời điểm/actor/instance/ObjectName/operation mà **không chứa credentials**.
- Đọc lại trạng thái MBean sau thao tác.
- Kiểm tra **tín hiệu thực**: nguồn dừng phát hay chưa, queue age, broker consumer assignment, kết nối, business processing.
- Nếu kết quả không rõ, đánh dấu `UNKNOWN`; không lặp invoke vô hạn.

### 11.3. Post-change

1. Theo dõi message in-flight và các side effects còn chạy.
2. Đảm bảo không có dữ liệu mất hoặc duplicate vượt hợp đồng retry/idempotency.
3. Xác minh backlog/health trong cửa sổ đại diện.
4. Cập nhật incident/change và người chịu trách nhiệm.
5. Nếu chỉ dừng tạm, ghi rõ **điều kiện và người được phép start lại**.

## 12. Ví dụ quan sát rồi mới gọi operation

Ví dụ pseudocode cho workflow không phụ thuộc một MBean name cố định:

~~~text
manage_endpoint(request):
    assert authorized_requester(request.actor)
    assert approved_change_or_incident(request.id)

    jvm = resolve_exact_instance(request.instance_ref)
    object_name = discover_target_mbean(jvm, request.component_ref)
    info = read_mbean_info(object_name)

    assert target_component_identity_verified(info, request.component_ref)
    assert requested_operation_is_exposed(info, request.operation)
    assert operation_is_allowed_for_role(request.actor, request.operation)

    before = collect_mbean_and_external_state(request)
    assess_backlog_inflight_and_protocol_risk(before)
    if not safe_to_proceed:
        escalate_and_stop()

    invoke_once_with_approval(request)
    after = read_mbean_and_external_state(request)
    verify_requested_effect(after, request)
    audit_before_after_and_follow_up(request, before, after)
~~~

Không tự động suy `start` hoặc `stop` tồn tại. Đối với điều khiển production, operation nên được gọi qua **workflow quản trị có phê duyệt và phân quyền**, không từ script ad hoc trên laptop không được quản lý.

## 13. Control Bus và JMX: hai đường quản trị cần phân biệt

Spring Integration còn có **Control Bus**, một mô hình gửi control message tới thành phần quản trị trong application context theo cấu hình được phép. JMX và Control Bus có thể cùng hướng tới quản lý runtime, nhưng **không phải cùng giao diện**:

| Đường quản trị | Điểm vào | Rủi ro |
|---|---|---|
| **JMX** | MBeanServer/ObjectName/operation | Remote management exposure, quyền invoke |
| **Control Bus** | Control messages qua channel/handler được cấu hình | Chạy operation ngoài dự kiến nếu ingress bị lộ hoặc expression quá rộng |
| **Admin API riêng** | REST/CLI được thiết kế theo tổ chức | Authentication, RBAC, audit và remote invocation |
| **Orchestrator** | Deployment/replica/consumer control ở platform | Scope nhiều instance, rollout/race condition |

Không nhầm `Control Bus` với bất kỳ inbound MessageChannel nào. Nếu có một control channel nhận dữ liệu từ người dùng hoặc hệ thống ngoài, cần **authentication, authorization, giới hạn lệnh và không expose biểu thức tùy ý**. Đường nào được dùng phụ thuộc security architecture và policy.

## 14. File inbound adapter: stop poller không đồng nghĩa xóa file

Một File inbound adapter kiểu polling thường quét thư mục, lọc file, tạo Spring Message và chuyển vào channel.

### 14.1. Điều cần xác minh qua JMX và metrics

- Endpoint/poller có `running` hay không, nếu được expose.
- Poller có thực sự tick và tìm file eligible không.
- Có file đang được ghi dở, đang lock hoặc đã qua accept-once filter?
- Backlog file ngoài thư mục có tăng?
- Queue nội bộ và outbound có xử lý xong dữ liệu đã nhận?

### 14.2. Khi stop

Nếu stop đúng inbound polling endpoint, mục tiêu là **ngăn đọc file mới**. File nguồn có thể vẫn nằm trên đĩa; **không được giả định** nó sẽ tự được xử lý đúng một lần sau start, vì còn phụ thuộc metadata store, filter, trạng thái rename/move, transaction và xử lý trùng.

### 14.3. Sau start

Đọc lại running state, chờ ít nhất một chu kỳ poll đại diện, kiểm tra số file eligible/accepted và đối chiếu processed/confirmed ở target. Nếu không thấy message, xem source filter trước khi kết luận JMX start thất bại.

## 15. SFTP adapter: phiên remote và đường quản trị

SFTP inbound/outbound liên quan **session factory**, remote directory, permissions, retry và trạng thái file.

### 15.1. Khi dừng SFTP inbound

1. Xem có transfer đang thực hiện không.
2. Xác định bean nào sở hữu polling và session lifecycle.
3. Đánh giá phần file đã copy về local, remote metadata/filter và temporary files.
4. Dừng poller/endpoint theo capability đã kiểm thử.
5. Kiểm tra không còn fetch mới; không suy rằng session remote đã đóng ngay nếu đang có I/O.
6. Sau khôi phục, kiểm tra file completeness, remote rename/handoff và duplicate acceptance.

### 15.2. Khi SFTP outbound lỗi

Stop outbound handler có thể khiến upstream queue tích tụ. Nếu bắt buộc ngừng vì remote không ổn định, cân nhắc **throttle/chặn ingress, xử lý DLQ/retry và dung lượng queue**. Không dùng JMX để “reset” một phiên bằng cách đổi secret không qua vault/owner.

### 15.3. JMX không thay remote monitoring

MBean running chỉ cho biết thành phần được coi là active. Remote SSH authentication, transfer confirmation, server disk và remote file state cần telemetry phía SFTP/client; history/message count không thay được bằng chứng tải file thành công.

## 16. HTTP inbound gateway và HTTP outbound gateway

### 16.1. HTTP inbound

Một HTTP inbound gateway có thể phụ thuộc web container/router hơn là một polling endpoint có `start/stop` trên MBean. Dừng một integration endpoint **không nhất thiết ngừng HTTP listener** hoặc khiến mọi route trả response theo kỳ vọng.

Khi muốn chặn ingress khẩn:

- Xác định điểm đúng: web route, gateway, reverse proxy, load balancer hay business handler.
- Chọn cơ chế có thể trả lỗi có kiểm soát, hạn chế traffic hoặc chuyển sang maintenance theo policy.
- Không nhận request rồi bỏ qua mà không có response semantics rõ ràng.
- Kiểm tra in-flight HTTP requests, timeout và idempotency trước khi mở lại.

### 16.2. HTTP outbound

Nếu outbound HTTP bị lỗi, ngắt handler hoặc stop downstream có thể gây backlog và retry. Một timeout **không chứng minh** remote chưa commit. Sau khi mở lại, xác minh idempotency key, request correlation, remote status và retry budget.

### 16.3. Thao tác JMX và route khác nhau

Không suy rằng MBean `stop` của một bean integration sẽ thay đổi trạng thái toàn bộ servlet container/WebFlux handler mapping; điều này phải được kiểm thử theo đúng app architecture và framework version.

## 17. JMS inbound/outbound: ack và transaction quan trọng hơn cờ running

JMS inbound có thể vận hành qua listener container, consumer và session. Dừng listener không phải tương đương purge queue.

| Khi thay đổi runtime | Cần kiểm tra |
|---|---|
| Stop consumer | Đã ngừng nhận message mới? In-flight được commit/rollback thế nào? |
| Start consumer | Connection/session đã khôi phục? Có redelivery? |
| Stop outbound | Pending messages đi đâu? Queue/retry/DLQ có tăng? |
| Connection reset | Có giao lại message, duplicate side effect hoặc lock? |

### 17.1. Trình tự kiểm chứng

1. Xác định JMS listener container hoặc endpoint nào thực sự chịu điều khiển.
2. Xem transaction/ack mode và trạng thái in-flight.
3. Trước stop, đánh giá mức độ cần **drain** và thời hạn.
4. Sau stop, kiểm tra broker queue depth, consumer count và unacked/delivery state.
5. Sau start, kiểm tra redelivery, terminal failures, DLQ và business outcome.

Không dùng MBean `isRunning=false` để tuyên bố “message không mất”. Tính bền vững phụ thuộc broker, ack/transaction và nghiệp vụ.

## 18. AMQP/RabbitMQ: listener, ack/nack và requeue

Với Spring Integration AMQP adapter và listener container liên quan, những thứ cần theo dõi gồm **consumer count, ready/unacked messages, publisher confirms, reconnects, nack/requeue và DLQ**.

### 18.1. Stop và redelivery

Tùy cấu hình ack và transaction, khi stop consumer có message in-flight, broker có thể giao lại message chưa được ack. Sau start:

- Kiểm tra duplicate delivery và idempotent receiver.
- Theo dõi redelivery ratio, DLQ và poison-message loop.
- Đối chiếu publisher confirm với consumer outcome.
- Đừng tăng consumer vô hạn nếu lỗi schema khiến mọi message đều nack/requeue.

### 18.2. Không điều khiển broker bằng giả định về MBean adapter

Một operation dừng adapter trong JVM không thay đổi tự động queue policy, exchange, routing keys hay state của các consumer ở node khác. Mọi thay đổi broker phải qua công cụ/owner có thẩm quyền tương ứng.

## 19. Kafka inbound/outbound: consumer group, lag và rebalance

Kafka có những hệ quả runtime đáng chú ý:

- Dừng consumer/listener có thể ảnh hưởng **partition assignment** và rebalance.
- Message/record đã poll nhưng chưa commit offset có thể được xử lý lại.
- Consumer lag có thể tăng khi node bị stop dù topic vẫn nhận record.
- Producer send success không đồng nghĩa business consumer đã xử lý.
- Start lại có thể kéo theo retries, replay hoặc conflict với transaction/idempotency.

### 19.1. Runbook riêng cho Kafka consumer

1. Đọc consumer group, topic, assignment, lag, retry/DLQ state bằng telemetry tương ứng.
2. Xác định listener/container hoặc integration endpoint nào thực sự đang được quản trị.
3. Thẩm định tác động với nhóm consumer khác và partition distribution.
4. Chọn stop/pause/resume theo API **thực sự hỗ trợ**, không giả định MBean có mọi operation.
5. Kiểm tra offset commit/in-flight transaction trước và sau thay đổi.
6. Quan sát rebalance, lag, throughput, duplicate processing và data freshness khi start lại.
7. Ghi evidence và owner nếu backlog chưa được xử lý hết.

### 19.2. Không dừng toàn bộ group ngoài phạm vi

JMX invocation lên một JVM có thể chỉ chạm một consumer instance. Nếu incident cần dừng cả nhóm, phải có kế hoạch điều phối platform/broker/ứng dụng; không gọi lặp ngẫu nhiên trên các node khi chưa rõ ownership.

## 20. JDBC/database inbound: poller, checkpoint và giao dịch

JDBC inbound polling thường sử dụng query chọn rows theo điều kiện và trạng thái xử lý/checkpoint. Khi stop/start:

- **Stop poller** thường nhằm ngăn query lấy batch mới, không xóa rows source.
- Rows đã SELECT có thể đang được xử lý, update status hoặc chờ commit.
- Nếu transaction rollback trước khi đánh dấu processed, một row có thể được đọc lại.
- Khi source backlog tăng, cần theo dõi watermark/cursor, oldest row age, pool saturation.
- Nếu DB connector đang timeout, việc retry poll có thể tạo tải và lock.

### 20.1. Tránh đếm SELECT như business completion

`rows_selected`, `messages_emitted`, `rows_processed` và `transactions_committed` là các mốc khác nhau. JMX running chỉ bổ sung trạng thái adapter, không tự cung cấp tính đúng đắn của transaction và idempotency.

### 20.2. JDBC outbound/gateway

Nếu dừng outbound handler mà inbound vẫn chạy, queue có thể tăng. Khi khôi phục, cần kiểm tra transaction result, deadlocks, duplicate updates và record states. Không in raw SQL bind parameters hoặc hàng dữ liệu nhạy cảm khi điều tra.

## 21. MessageChannel và khả năng quản trị runtime

### 21.1. DirectChannel

DirectChannel thường dispatch đồng bộ tới subscriber. Nếu thấy send count hoặc error count từ instrumentation/JMX, đó là tín hiệu tại ranh giới channel. Nó **không nhất thiết đo độ trễ mạng thuần** hoặc xác nhận target đã commit.

### 21.2. QueueChannel

QueueChannel giữ message để consumer/poller nhận sau. Quan sát queue depth, capacity, oldest age, enqueue/dequeue rate. Dừng consumer có thể khiến **depth tăng**. Dừng upstream không tự làm queue rỗng.

### 21.3. ExecutorChannel

ExecutorChannel dispatch qua executor. Channel send được chấp nhận không chứng minh handler đã chạy. Cần executor active threads, queue wait, task rejection và tracing context, không chỉ số send thành công.

### 21.4. PublishSubscribeChannel

Một send có thể tới nhiều subscribers; thao tác stop một subscriber có thể để các subscriber khác tiếp tục. Cần per-branch outcome và error handling. Không dùng một MBean counter của channel làm bằng chứng mọi nhánh thành công.

| Channel | Mục tiêu quan sát | Hạn chế khi chỉ nhìn JMX |
|---|---|---|
| Direct | Send/error và handler liên quan | Thời gian downstream có thể nằm trong call path |
| Queue | Depth, consumer status, wait | Không đo external backlog |
| Executor | Accepted task, executor state | Không bảo đảm task đã xử lý |
| Publish-subscribe | Fan-out/subscriber activity | Không chứng minh mọi subscriber hoàn tất |

## 22. JMX và polling lifecycle: khi nào stop có hiệu lực?

Một nguồn polling có ít nhất ba lớp:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant MX as MBeanServer
    participant P as Polling Endpoint
    participant S as File / SFTP / JDBC Source
    participant Q as Internal Queue / Channel
    O->>MX: Invoke stop (nếu được phép)
    MX->>P: Lifecycle operation
    P-->>MX: Operation completed / accepted
    MX-->>O: JMX response
    Note over P,S: Poll đã bắt đầu có thể còn công việc dang dở
    P->>S: Không khởi tạo poll mới theo trạng thái dừng
    Q-->>O: Backlog / in-flight vẫn có thể tồn tại
    O->>MX: Read state
    Note over O,Q: Xác minh thêm bằng poll/queue/target telemetry
~~~

### 22.1. Phân biệt “operation return” và “business effect”

Một JMX invocation trả thành công chỉ xác nhận lời gọi MBean diễn ra theo semantics operation. Nó **không bảo đảm**:

- Poll đang chạy đã dừng ngay.
- Remote connection đã đóng.
- Message in-flight đã commit.
- Queue trong JVM đã rỗng.
- Các replicas khác đã stop.
- Remote target ngừng nhận dữ liệu từ các nguồn khác.

Sau thao tác luôn cần **readback + external verification** trong một cửa sổ phù hợp cadence.

## 23. Quản lý flow động: không nhầm lifecycle với đăng ký bean

Spring Integration hỗ trợ các trường hợp đăng ký flow động qua cơ chế phù hợp với phiên bản, chẳng hạn các API quanh **`IntegrationFlowContext`**. Việc **register/unregister một flow** khác với `start/stop` endpoint đã tồn tại:

| Thao tác | Tác động khái niệm | Lưu ý |
|---|---|---|
| **Start endpoint** | Cho lifecycle endpoint hoạt động | Không tạo thêm cấu hình mới |
| **Stop endpoint** | Ngừng hoạt động theo bean capability | Không xóa định nghĩa/queue tự động |
| **Register flow** | Đăng ký cấu trúc/beans mới ở runtime | Cần ID, owner, cleanup và conflict prevention |
| **Remove/unregister flow** | Tháo flow/beans theo API hỗ trợ | Có thể ảnh hưởng in-flight, references, resources |
| **Reconfigure flow** | Thay mapping, poller hoặc handler | Cần change/version và restart/rollout strategy |

Không sử dụng JMX như một đường tùy tiện để tạo/xóa flow nếu ứng dụng chưa **expose operation rõ ràng**, có RBAC và thử nghiệm safe teardown.

## 24. Hệ nhiều instance: JMX là trạng thái cục bộ, SLO là toàn hệ

~~~mermaid
flowchart TD
    ROUTE[Load Balancer / Broker / Shared Source] --> A[Integration Instance A]
    ROUTE --> B[Integration Instance B]
    ROUTE --> C[Integration Instance C]
    A --> JA[JMX A]
    B --> JB[JMX B]
    C --> JC[JMX C]
    JA --> OPS[Authorized Operations]
    JB --> OPS
    JC --> OPS
    A --> DATA[Shared Queue / DB / Remote Target]
    B --> DATA
    C --> DATA
~~~

### 24.1. Các bẫy cluster

1. JConsole kết nối node A báo inbound đã stop, nhưng B/C vẫn tiếp tục poll.
2. Kubernetes pod được thay thế, ObjectName cũ không còn ở cùng JVM.
3. Dừng một Kafka consumer làm rebalance, thay đổi lag/assignment của các consumer còn lại.
4. Hai SFTP poller cùng nguồn gây duplicate nếu thiếu distributed lock/filter metadata dùng chung.
5. Dashboard tổng hợp chỉ số toàn cụm che mất một node bị lỗi.
6. Lệnh stop/start được chạy hai lần bởi hai on-call operators khác nhau.

### 24.2. Điều phối an toàn

- Xác định **instance/replica/deployment identity** trước khi invoke.
- Có quyền thực thi rõ và cơ chế **lock/serialization** đối với change cùng component.
- Có danh mục các node và tình trạng rollout/restart.
- Xác minh both per-instance state và end-to-end flow metrics.
- Nếu mục tiêu là dừng toàn service, dùng orchestration được thiết kế chứ không tự phỏng đoán số node.

## 25. JMX so với Actuator, Micrometer, Health và tracing

| Cơ chế | Thế mạnh | Hạn chế |
|---|---|---|
| **JMX/MBean** | Đọc metadata bean và operation management nội bộ JVM | Phụ thuộc bean/version, khó biểu diễn toàn cluster |
| **Spring Boot Actuator** | Health/info/metrics/management endpoints qua transport cấu hình | Không thay thế operation trên mọi Integration endpoint |
| **Micrometer** | Counters, timers, gauges; SLI/SLO, alert, dashboard | Aggregate, không cho điều khiển runtime theo mặc định |
| **Distributed tracing** | Đường call và độ trễ xuyên service | Cần propagation/sampling và không có control operation |
| **MessageHistory** | Danh sách component cục bộ qua message khi bật | Không phải timer, audit bền vững hay remote confirm |
| **Structured logs/audit** | Lỗi cụ thể, actor, quyết định và evidence | Cần sanitize, retention và quyền truy cập |

### 25.1. Khi nào cần metric thay vì JMX?

Để biết throughput, p95/p99, error rate, backlog age và sự kiện SLO trên nhiều instances, metrics/time series thường phù hợp hơn. JMX có thể dùng như **một nguồn tín hiệu hoặc control plane chuyên biệt** khi MBean thực sự expose thông tin cần đọc.

### 25.2. Khi nào cần JMX?

Khi phải kiểm tra một bean cụ thể trong JVM hoặc thực hiện một operation lifecycle **được hỗ trợ và phê duyệt**, JMX có thể trực tiếp và hữu ích. Không nên bật remote JMX cho mọi process chỉ để xem vài counter vốn đã có qua Micrometer.

## 26. Bảo vệ JMX: ưu tiên an toàn vận hành

**Remote JMX có thể cho phép đọc thông tin nội bộ và thực thi thao tác nhạy cảm**. Nếu không được bảo vệ, nó tạo đường quản trị ngoài workflow ứng dụng.

### 26.1. Những nguyên tắc bắt buộc

1. **Không expose JMX/RMI công khai Internet** hoặc trong mạng không tin cậy.
2. Dùng authentication/authorization theo phương án JVM/platform, chỉ mở cho danh sách actor cần thiết.
3. Bảo vệ transport bằng TLS hoặc kênh quản trị an toàn được tổ chức cho phép.
4. Phân tách read-only monitoring với quyền invoke/modify; không cấp mọi operation cho tài khoản exporter.
5. Giới hạn MBeans được export theo nhu cầu, tránh chứa secrets và operation nguy hiểm.
6. Audit kết nối/thao tác theo khả năng công cụ và workflow, có actor, instance, target, before/after.
7. Quản lý credential/certificate quản trị trong secret manager; rotation và offboarding theo lifecycle.
8. Rà socket/ports/RMI registry và chính sách firewall, đặc biệt khi chạy container/Kubernetes.
9. Không vô hiệu SSL/authentication chỉ để “JConsole kết nối được”.
10. Bật cảnh báo khi JMX sử dụng ngoài change window, từ nguồn không hợp lệ hoặc trên nhiều instances bất thường.

### 26.2. Không giả định JMX native tự có RBAC chi tiết

Khả năng phân quyền theo **MBean, attribute, operation** phụ thuộc server/access mechanism, proxy/gateway và security configuration. Nếu không thể cưỡng chế đủ hẹp ở JMX native, nên cung cấp một **admin workflow/service** có danh sách thao tác cho phép, phê duyệt và audit thay vì mở quyền invoke rộng.

### 26.3. Không đưa bí mật vào MBean attributes

Một MBean có thể expose property của Java bean. Không export password/client secret/private key hay cấu hình sensitive dưới dạng readable attributes. Khi cần chẩn đoán, expose trạng thái như `credentialPresent=true`, secret version/fingerprint an toàn hoặc last rotation time.

## 27. Audit và quản trị thay đổi qua JMX

### 27.1. Mẫu hồ sơ change

~~~yaml
change_id: JMX-CHANGE-EXAMPLE-271
incident_ref: INC-EXAMPLE-271
environment: production
application_ref: invoice-integration
instance_ref: invoice-worker-03
component_ref: invoiceSftpInbound
object_name_ref: approved-jmx-object-reference
operator_ref: iam-integration-oncall
approver_ref: integration-owner
action: STOP_IF_SUPPORTED
reason: downstream-database-overloaded
approved_at: "2026-11-23T15:15:00+07:00"
before:
  running: true
  backlog_age_bucket: 5m-10m
  inflight_category: LOW
applied_at: "2026-11-23T15:20:00+07:00"
after:
  mbean_running: false
  inbound_polls_stopped: VERIFIED
  in_flight_status: TRACKED
  downstream_dependency: STILL_UNAVAILABLE
verification_refs:
  - jmx-readback-271
  - integration-metrics-271
restore_owner_ref: application-oncall
restore_condition: db-healthy-and-backlog-plan-approved
status: CONTAINED_PENDING_RESTORE
~~~

Đây là **ví dụ giả lập**, không phải giá trị được JMX tự ghi hoặc tên field bắt buộc. ObjectName thực tế có thể chứa thông tin nội bộ nên audit record có thể chỉ dùng một tham chiếu được bảo vệ.

### 27.2. Trạng thái incident không chỉ “done”

| Trạng thái | Ý nghĩa |
|---|---|
| `REQUESTED` | Có đề nghị thao tác |
| `APPROVED` | Đã xác minh actor/scope và phê duyệt |
| `APPLIED` | Invocation được thực hiện và trả kết quả |
| `EFFECT_VERIFIED` | Tác động mong muốn được kiểm chứng |
| `RESTORE_PENDING` | Đã contain nhưng cần mở lại |
| `RESTORED_VERIFIED` | Luồng khôi phục, target và backlog đúng |
| `EXCEPTION_OPEN` | Không đủ bằng chứng hoặc vẫn còn rủi ro |

Không đóng change chỉ vì thao tác JMX trả response thành công. **Restoration** có thể là một change/decision riêng.

## 28. Khi endpoint bị stop mà ứng dụng restart

Một rủi ro thực tế: operator stop endpoint qua JMX, sau đó JVM restart hoặc deployment rollout. Tùy lifecycle configuration, endpoint có thể **tự start trở lại theo cấu hình ban đầu**.

### 28.1. Vấn đề cần làm rõ

- Trạng thái stop có được persist ngoài JVM không?
- Có config flag tại source-of-truth để disable ingress lâu hơn một phiên chạy không?
- Startup policy có cơ chế chặn nếu incident đang mở không?
- Orchestrator có restart process vì health check thất bại?
- Ai chịu trách nhiệm kiểm tra sau rollout?

### 28.2. Cách vận hành

Nếu mục tiêu là ngừng lâu dài, **không chỉ dựa vào JMX local stop**. Cần áp cấu hình hoặc workflow được quản lý bền vững, có owner, TTL/restore condition và reconcile. Sau restart, kiểm tra actual endpoint state, poll count và remote traffic.

## 29. Các lỗi JMX điển hình và cách điều tra

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Không thấy MBean nào | Chưa bật export, sai context, khác JVM | Kiểm tra enablement và process |
| Có MBean nhưng không thấy endpoint | Bean không được export, wrong ID/version/scope | Đọc bean inventory, MBeanInfo, naming |
| Invoke trả `ReflectionException` hoặc signature mismatch | Operation không được expose hoặc signature sai | Đọc operations/parameter types thay vì thử mù |
| `InstanceNotFoundException` | Bean/JVM đã restart, ObjectName thay đổi | Refresh listing, kiểm tra deployment instance |
| `AttributeNotFoundException` | Attribute không có trong MBeanInfo | Khám phá đúng tên/khả năng đọc |
| `SecurityException`/access denied | Quyền không đủ hoặc chính sách chặn | Dùng escalation/approval, không bypass |
| Connection timeout | Firewall, TLS, RMI host/port, JVM down | Kiểm tra kênh quản trị và health |
| `stop` trả success nhưng source vẫn phát | Sai bean/instance, in-flight hoặc replica khác | Xem per-node state và external telemetry |
| `start` nhưng không có message | Source rỗng, poller disabled, connection lỗi, filter | Xem poll ticks, source age, error logs |
| Sau start có duplicates | Offset/ack/metadata filter/transaction chưa an toàn | Dedupe/idempotency, kiểm tra replay |

**Không thực hiện thao tác lặp không giới hạn** khi status không rõ. Đọc lại trạng thái và ghi evidence trước retry hoặc escalation.

## 30. Runbook JMX-03 — “Đã start nhưng không có dữ liệu”

1. Xác minh `start` đã được gọi lên **đúng MBean, đúng JVM**, có operation hỗ trợ.
2. Đọc `isRunning` (nếu được expose); phân biệt state với connectivity.
3. Với polling source: xem scheduler, trigger, poller last tick, task executor và lock.
4. Với File/SFTP: xem file eligibility, filter, remote directory, session và permission.
5. Với JMS/AMQP/Kafka: xem connection/consumer count, subscription, assignment, lag, broker permissions và error channel.
6. Với JDBC: xem query, watermark/last processed ID, connection pool, transaction và rows eligible.
7. Kiểm tra MessageChannel, handler và outbound có subscribe/consumer hợp lệ không.
8. Đọc error logs, tracing, metrics và message history nếu có, không dump raw payload.
9. Thử canary/synthetic event được phê duyệt nếu policy cho phép, xác minh end-to-end.
10. Mở follow-up với owner nếu state running nhưng business progress vẫn bằng 0.

## 31. Runbook JMX-04 — “Đã stop nhưng message vẫn được xử lý”

1. Kiểm tra có stop **đúng inbound endpoint** hay nhầm handler/channel.
2. Kiểm tra nhiều instances hoặc một đường input khác cùng gửi vào channel.
3. Phân biệt **message đã nhận trước stop** với message mới.
4. Xem pending QueueChannel/executor, broker prefetch, JMS unacked hoặc Kafka polled records.
5. Kiểm tra poll đang chạy dở, retry scheduler hoặc DLQ replay.
6. Xác định producer bên ngoài còn gửi, nhưng app không nhận mới hay app vẫn nhận qua route khác.
7. Đọc evidence per-node; không gọi stop vào mọi MBean không rõ chức năng.
8. Nếu có data exposure đang diễn ra, phối hợp Security/Platform áp containment đúng lớp.
9. Xem restart/rollout có làm endpoint tự start lại không.
10. Đóng khi đã xác minh ingress/processing semantics phù hợp mục tiêu, có kế hoạch xử lý backlog.

## 32. Kiểm thử tính đúng đắn trước khi dùng JMX trên production

### 32.1. Các cấp test

| Cấp | Nội dung | Mục tiêu |
|---|---|---|
| **Unit/component** | Endpoint có lifecycle và MBean metadata? | Biết operation thật sự tồn tại |
| **Integration test** | Start/stop ở flow đại diện | Kiểm chứng thay đổi nguồn/consumer |
| **Failure test** | Stop khi queue có message và target lỗi | Hiểu in-flight, retry, rollback |
| **Restart test** | JVM restart sau stop | Biết trạng thái có persist không |
| **Cluster test** | Stop một replica, node khác chạy | Hiểu scope và rebalance |
| **Security test** | Read-only operator thử write/invoke | Kiểm tra chặn thao tác trái quyền |
| **Audit test** | Invoke qua workflow, lưu before/after | Truy vết và điều tra |
| **Load test** | Large backlog, slow target, repeated restart | Xác định giới hạn throughput và dữ liệu tồn |

### 32.2. Ví dụ test specification

~~~text
Given:
  - Endpoint polling được export qua JMX trong môi trường test
  - Source có 3 file hợp lệ, downstream có fake handler
  - Test có quyền gọi đúng operation đã được discover

When:
  - Stop endpoint theo MBeanInfo
  - Chờ qua một cửa sổ poll đại diện

Then:
  - Không phát sinh poll mới theo semantics endpoint
  - Không mất dữ liệu nguồn
  - In-flight được phân loại rõ, không đoán là đã xử lý xong

When:
  - Start lại endpoint

Then:
  - Polling phục hồi
  - File được xử lý theo hợp đồng retry/dedup
  - Flow outcome và audit được verified
~~~

Đây là **đặc tả kiểm thử**, không phải test đã được chạy. Không dùng kết quả test của File adapter để suy semantics của Kafka listener hoặc HTTP inbound.

## 33. Cảnh báo và chỉ số vận hành quanh JMX

### 33.1. Metrics nên có

| Metric | Câu hỏi |
|---|---|
| **Endpoint desired vs actual state** | Endpoint đang ở trạng thái theo policy không? |
| **Unexpected stop/start count** | Có thay đổi ngoài change/incident? |
| **Last poll success age** | Poller còn thực thi không? |
| **Source pending oldest age** | File/record còn chờ bao lâu? |
| **Channel queue depth/age** | Có backlog tích tụ sau khi stop không? |
| **Handler attempts/success/failure** | Business processing đang tiến triển? |
| **Outbound confirmation rate** | Target đã nhận theo protocol hay chưa? |
| **JMS/AMQP unacked/redeliver** | Stop/start có tạo replay? |
| **Kafka lag/rebalance count** | Consumer lifecycle tác động thế nào? |
| **JMX access/operation audit** | Ai đã thao tác, đúng thời gian/target không? |
| **Restoration overdue** | Endpoint bị dừng quá hạn chưa có owner? |

### 33.2. Alert nào hữu ích?

- Endpoint **unexpectedly stopped** ngoài change window.
- Endpoint **running nhưng poll success age quá lớn**, trong khi source có item eligible.
- Queue age/backlog vượt deadline sau thao tác stop.
- Consumer group lag hoặc DLQ tăng sau start.
- Thao tác JMX trái quyền hoặc không có incident reference.
- Endpoint đang stop tạm nhưng đã qua **restore deadline**.
- JMX monitoring mất dữ liệu; phân biệt **no data** với `isRunning=false`.

**Không tạo cảnh báo P0 cho mọi endpoint stop có phê duyệt**. Hãy liên kết desired state và change windows.

## 34. Tình huống thực hành

### Tình huống A — SFTP inbound đã stop nhưng remote file vẫn tăng

Operator dừng poller qua JMX, thấy `isRunning=false`; phía đối tác tiếp tục upload file.

**Phân tích:** remote file count tăng là bình thường nếu partner vẫn phát dữ liệu, trong khi inbound local không poll. Cần theo dõi source oldest file age và capacity. Khi start lại, xác minh accept-once metadata, file completeness và downstream business confirmation.

### Tình huống B — Kafka consumer stop một pod, lag tăng

Đội trực dừng một endpoint Kafka ở node A nhưng topic vẫn có records, node B/C vẫn hoạt động.

**Phân tích:** JMX tác động node A, cần xem consumer group rebalance, assignment và lag tổng/per-instance. Không mặc định cả group dừng; nếu muốn maintenance toàn cụm phải phối hợp orchestrator.

### Tình huống C — HTTP inbound còn nhận request sau lệnh stop

MBean của một handler báo stopped nhưng reverse proxy vẫn gửi HTTP traffic tới ứng dụng.

**Phân tích:** handler lifecycle không nhất thiết điều khiển HTTP listener/web route. Phải kiểm tra component ownership và dùng ingress maintenance/routing policy phù hợp, không tự tắt xác minh TLS/SSO.

### Tình huống D — JMS redelivery sau start

Một JMS consumer bị stop khi có message in-flight; start lại thấy cùng business event được xử lý thêm lần nữa.

**Phân tích:** kiểm tra transaction/ack/rollback, idempotent receiver, source redelivery và DLQ. MBean running không bảo đảm exactly-once; cần kiểm tra business side effects.

### Tình huống E — QueueChannel tiếp tục đầy sau khi dừng outbound

Operator stop outbound HTTP handler nhưng File inbound vẫn tạo 5.000 message/phút.

**Phân tích:** cần chặn/throttle ingress theo kế hoạch, xem queue capacity, oldest age và in-flight. Nếu remote timeout, đối soát outcome trước retry. Không chỉ tăng heap để giữ queue vô hạn.

### Tình huống F — Một MBean không có operation start

JMX client liệt kê handler nhưng không thấy `start`.

**Phân tích:** đây có thể là component xử lý thuần, không phải lifecycle endpoint, hoặc exporter không expose operation. Đọc MBeanInfo và tìm đúng consumer/producer; không tự invoke method không có.

### Tình huống G — Stop mất hiệu lực sau rollout

On-call stop polling để containment nhưng deployment rolling update tạo pod mới và poll lại.

**Phân tích:** JMX state cục bộ không persist. Cần source-of-truth disable flag hoặc quy trình orchestration, change owner và kiểm tra actual state sau rollout.

### Tình huống H — Remote JMX mở không có xác thực

Một server staging để cổng JMX truy cập được từ mạng rộng, cho phép invoke.

**Phân tích:** kích hoạt Security review, giới hạn mạng và quyền, kiểm tra log truy cập, sửa TLS/authn/authz theo policy; không dùng cấu hình bỏ xác thực để tiết kiệm công quản trị.

### Tình huống I — JDBC poller stop nhưng DB row vẫn bị cập nhật

Sau khi stop, bảng DB vẫn có vài row chuyển trạng thái processed.

**Phân tích:** có thể là transaction/poll đang chạy hoặc instance khác đang xử lý. Đối chiếu timestamp, row watermark, node ID và commit evidence; không kết luận stop thất bại chỉ vì có update sau thời điểm invocation.

### Tình huống J — AMQP consumer stop, ready tăng nhưng unacked giảm

Operator thấy ready messages tăng, unacked messages giảm sau stop.

**Phân tích:** hành vi có thể liên quan consumer ngừng nhận và broker giải quyết in-flight; kiểm tra ack/nack/requeue, queue state và các consumer khác. Không diễn giải một gauge là bằng chứng mất message.

### Tình huống K — MBean count đẹp nhưng user không nhận dữ liệu

JMX send count tăng, `isRunning=true`, nhưng một HTTP outbound gateway không được remote phản hồi.

**Phân tích:** send counter chỉ đo một phần flow. Kiểm tra HTTP status/timeout, circuit breaker, retry, remote audit và business confirmation. Running không phải end-to-end SLO.

### Tình huống L — Hai operators invoke đồng thời

Một người stop inbound để điều tra, người khác start vì thấy dashboard lỗi.

**Phân tích:** cần change serialization/ownership, incident bridge, audit và desired state. Đừng để hai automation hoặc người trực dùng JMX điều khiển ngược nhau không có khóa/đối soát.

## 35. Checklist vận hành nhanh

### 35.1. Trước khi đọc JMX

- [ ] Đúng JVM, instance, environment và deployment version?
- [ ] Kênh JMX được bảo vệ; không mở remote public?
- [ ] Đã đọc `MBeanInfo` thay vì giả định attribute/operation?
- [ ] ObjectName map tới component ID và flow nào?
- [ ] Đã phân biệt lifecycle, connectivity và business progress?

### 35.2. Trước khi invoke

- [ ] Có incident/change ID, approval và quyền actor hợp lệ?
- [ ] Biết rõ operation nào được export và tác động tới endpoint nào?
- [ ] Đã đánh giá message in-flight, queue, transaction, ack/offset, retry?
- [ ] Đã xác định scope: một instance hay toàn cluster?
- [ ] Có before snapshot, restore condition, owner và deadline?
- [ ] Có điều phối với App Owner/SRE/Security nếu ảnh hưởng production?

### 35.3. Sau khi invoke

- [ ] MBean state đã readback; result có bị `UNKNOWN`?
- [ ] Poll/listener/consumer/connection đã thực sự đổi như mục tiêu?
- [ ] Có source/queue/broker backlog hoặc in-flight chưa hoàn tất?
- [ ] Kafka rebalance, JMS/AMQP redelivery và DB transaction đã được kiểm tra khi liên quan?
- [ ] Target/business confirmation có bằng chứng?
- [ ] Có audit actor/time/target/operation/before/after?
- [ ] Nếu stop tạm, ai chịu trách nhiệm start lại và khi nào?
- [ ] Nếu JVM restart, desired state có được bảo đảm không?

## 36. Tổng kết

**JMX quản trị endpoint runtime** giúp đội vận hành nhìn sâu vào các thành phần Spring Integration trong một JVM và, khi MBean có operation phù hợp, thực hiện thay đổi vòng đời mà không phải luôn restart toàn ứng dụng. Giá trị của JMX nằm ở **khả năng kiểm tra đúng bean, đúng trạng thái và điều khiển đúng phạm vi**, không phải ở việc gọi được một phương thức `start` hay `stop`.

Trong module **Spring Integration Adapters**, từng luồng File, SFTP, HTTP, JMS, AMQP, Kafka và database có **cơ chế nhận dữ liệu, acknowledgement, retry, transaction và kết nối** khác nhau. Vì thế một operation thành công chỉ là bước đầu: phải đối soát MessageChannel, poller, consumer, backlog, in-flight, broker/remote state và kết quả business. Kết hợp **JMX có phân quyền + Micrometer metrics + logs/tracing + MessageHistory + readback tại đích**, cùng quy trình change, audit và khôi phục có owner, là cách quản trị endpoint runtime an toàn và có thể kiểm chứng.
