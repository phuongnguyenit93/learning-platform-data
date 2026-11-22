# Audit lời gọi quản trị và người thực hiện trong Spring Framework JMX

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Security và vận hành  
> **Bài học:** Audit lời gọi quản trị và người thực hiện

## 1. Mục tiêu

Một JMX operation có thể xem hoặc thay đổi trạng thái ứng dụng đang chạy. Khi thao tác có tác dụng phụ như xóa cache, thay đổi ngưỡng, reset counter, bật/tắt thành phần, kiểm soát quyền gọi thôi chưa đủ: hệ thống còn cần biết **ai đã làm gì, với đối tượng nào, lúc nào, kết quả ra sao**.

Sau bài học, bạn có thể:

- Phân biệt **authentication**, **authorization**, **audit logging** và **observability** đối với JMX.
- Biết những trường tối thiểu của một sự kiện audit dành cho lời gọi quản trị.
- Hiểu giới hạn của việc xác định người gọi qua JMX/RMI, nhất là khi sử dụng local MBeanServer, proxy, shared credentials hoặc custom connector.
- Thiết kế một management facade trong Spring để audit những operation quan trọng.
- Phân biệt log phía client, interceptor, JMX connector và log tại operation server-side.
- Tránh ghi password, token, secret, dữ liệu cá nhân hoặc payload nhạy cảm vào audit log.
- Xây dựng quy trình kiểm chứng có thể phân biệt **đã yêu cầu**, **đã được chấp nhận**, **đã thực thi** và **đã hoàn thành**.

## 2. Vì sao JMX operation cần audit?

JMX là kênh quản trị của Java runtime và ứng dụng. Một MBean có thể expose:

- **Attribute chỉ đọc** như số kết nối, trạng thái queue.
- **Attribute writable** như cấu hình timeout, limit, cờ vận hành.
- **Operation** như refresh cache, pause worker, thay đổi logging, reload configuration.
- **Notification** phản ánh sự kiện và thay đổi trạng thái.

Ví dụ:

\`\`\`java
@ManagedOperation(description = "Pause background workers")
public void pauseWorkers() {
    workerService.pause();
}
\`\`\`

Nếu một operator gọi operation và hệ thống ngừng xử lý job, câu hỏi điều tra thường là:

1. Có ai gọi \`pauseWorkers\` không?
2. Thao tác diễn ra lúc nào và trên instance nào?
3. Tên ObjectName/operation chính xác là gì?
4. Tham số nào được sử dụng?
5. Ai hoặc tài khoản dịch vụ nào đã được xác thực?
6. Lệnh bị từ chối, lỗi hay hoàn tất?
7. Có correlation ID để nối audit với application logs không?

Không ghi audit sẽ khiến sự cố khó tái hiện, khó xác minh trách nhiệm và dễ nhầm một thao tác quản trị với lỗi ứng dụng.

## 3. Bốn lớp kiểm soát khác nhau

| Lớp | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Authentication | Người gọi chứng minh danh tính nào? | JMX connector xác thực account |
| Authorization | Danh tính này được phép làm gì? | Cho phép đọc, hạn chế invoke operation |
| Audit | Ai đã yêu cầu/thực hiện thao tác nào và kết quả gì? | Ghi event \`jmx.operation.invoke\` |
| Observability | Ứng dụng đang hoạt động và có biến đổi gì? | Metric queue depth, JMX notification |

**Audit không thay thế authorization.** Ghi lại thao tác trái phép sau khi nó đã được thực thi không phải biện pháp kiểm soát hợp lệ.

**Authentication cũng không tự tạo audit đầy đủ.** Một connector có thể xác thực người dùng nhưng không mặc định ghi đầy đủ tên MBean, operation, tham số được phép ghi, kết quả và correlation ID.

## 4. Luồng gọi quản trị cần quan sát

\`\`\`text
JConsole / JMX client
          |
          | credentials / subject
          v
JMXConnectorServer
          |
          | authentication + authorization
          v
MBeanServerConnection
          |
          | ObjectName + attribute/operation
          v
MBeanServer
          |
          v
Spring ModelMBean / management facade
          |
          | kiểm tra phạm vi + audit
          v
Business service
          |
          v
Thay đổi trạng thái / tác vụ vận hành
\`\`\`

Có thể audit ở nhiều vị trí:

- **Connector/access layer**: ghi thông tin kết nối, tài khoản được xác thực, truy cập được phép/từ chối.
- **MBeanServer/interceptor**: ghi thao tác JMX theo ObjectName, signature và kết quả nếu hạ tầng hỗ trợ.
- **Management facade**: ghi thao tác quản trị có ý nghĩa nghiệp vụ và kết quả thực tế.
- **Business service**: ghi những thay đổi trạng thái quan trọng, bất kể đến từ JMX, HTTP, scheduler hay message consumer.

Thiết kế mạnh thường kết hợp các lớp này theo trách nhiệm, không chỉ phụ thuộc một dòng log trong \`@ManagedOperation\`.

## 5. Audit event nên có những trường nào?

Một sự kiện audit hợp lý:

\`\`\`json
{
  "event": "jmx.operation",
  "timestamp": "2026-11-11T10:15:30.000Z",
  "application": "order-service",
  "instance": "order-service-2",
  "objectName": "app.management:type=WorkerPool,name=background",
  "operation": "pause",
  "signature": [],
  "actor": "jmx-operator-17",
  "actorSource": "authenticated-jmx-subject",
  "requestId": "ops-7cfe1a",
  "outcome": "SUCCESS",
  "durationMs": 12
}
\`\`\`

Đây là **mẫu cấu trúc log do ứng dụng thiết kế**, không phải schema chuẩn mà Spring JMX tự phát ra.

| Trường | Ý nghĩa |
|---|---|
| \`timestamp\` | Thời gian UTC hoặc timezone có offset rõ ràng |
| \`event\` | Loại hành động được ghi |
| \`application\`, \`instance\` | Ứng dụng và node nơi thực thi |
| \`objectName\` | Định danh MBean được gọi |
| \`operation\`, \`signature\` | Tên và chữ ký JMX |
| \`actor\` | Danh tính đã được xác thực hoặc danh tính hệ thống |
| \`actorSource\` | Nguồn xác thực danh tính |
| \`requestId\` | Mã tương quan để truy vết |
| \`outcome\` | SUCCESS, DENIED, FAILED, ACCEPTED hoặc trạng thái khác |
| \`durationMs\` | Thời gian xử lý thao tác |
| \`reasonCode\` | Mã lỗi hoặc lý do từ chối không nhạy cảm |

Không nhất thiết ghi toàn bộ parameter values. Với một số thao tác, chỉ ghi tên tham số và giá trị đã được allowlist/masking là đủ.

## 6. Điểm khó: ai thực sự là người gọi JMX?

Đây là phần dễ bị suy luận sai.

### 6.1. Local JMX

Code trong cùng JVM có thể gọi trực tiếp:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

server.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

Lời gọi này không nhất thiết đi qua remote connector hoặc lớp xác thực. Trong nhiều cấu hình, không có thông tin “operator đăng nhập” đi kèm lời gọi.

Không thể dùng mỗi \`System.getProperty("user.name")\` để chứng minh người nào đã gọi JMX operation; giá trị đó thường phản ánh OS user chạy JVM, **không phải actor của từng invocation**.

### 6.2. Remote JMX với tài khoản riêng

Khi JMX connector xác thực client, nó có thể tạo security subject/principal tương ứng. Trong một số cấu hình có subject được đưa vào security context của lời gọi, server-side code có thể truy xuất subject qua API JMX/RMI phù hợp.

Tuy nhiên không nên khẳng định \`Subject.current()\` hoặc một API lấy subject luôn hoạt động trên mọi JDK/connector. Ngữ cảnh security phụ thuộc JDK, connector implementation, cơ chế xác thực và call path.

### 6.3. Shared credentials

Nếu nhiều operator dùng chung một tài khoản \`jmx-admin\`, audit chỉ có thể khẳng định **tài khoản chung** đã được sử dụng. Nó không thể xác định đáng tin cậy cá nhân thực hiện nếu không có một lớp identity hoặc workflow bổ sung.

### 6.4. Client-supplied username

Một operation như:

\`\`\`java
public void pause(String requestedBy) { ... }
\`\`\`

không tạo danh tính đáng tin cậy; client có thể truyền bất kỳ chuỗi nào. \`requestedBy\` chỉ là metadata do caller khai báo, không phải bằng chứng authentication.

**Nguyên tắc:** phân biệt \`verifiedActor\` (từ cơ chế xác thực đáng tin cậy) với \`claimedActor\` (dữ liệu do client cung cấp). Không gộp hai trường thành một identity đã xác minh.

## 7. Security Subject trong JMX remote

JMX remote có thể kết hợp Java security \`Subject\` và \`Principal\` khi connector thiết lập bối cảnh xác thực.

Tư duy thiết kế:

\`\`\`text
Client credentials
       |
       v
JMXAuthenticator / connector
       |
       v
Authenticated Subject (nếu cơ chế hỗ trợ)
       |
       v
Invocation authorization context
       |
       v
Management operation audit
\`\`\`

Khi cần xác định người gọi ở mức đáng tin cậy, nên xây kiến trúc identity ở **connector/authentication layer** và truyền actor qua đường đã được kiểm soát tới audit layer, hoặc dùng cơ chế audit tập trung có hỗ trợ connector.

Lưu ý:

- Không dựa vào ThreadLocal tùy ý nếu connector không bảo đảm truyền context.
- Không dựa vào tên thread làm user ID.
- Không suy ra user từ source IP khi có NAT, bastion hoặc shared monitoring agent.
- Không tin username do client tự truyền vào operation là đã xác thực.
- Nếu actor không xác định được, ghi rõ \`UNKNOWN\` hoặc \`SYSTEM\` với lý do, không bịa danh tính.

## 8. Thiết kế management facade có audit

Một service nghiệp vụ:

\`\`\`java
public interface WorkerService {
    void pause();
    void resume();
    boolean isPaused();
}
\`\`\`

Facade quản trị:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=background"
)
public class WorkerManagementFacade {

    private final WorkerService workers;
    private final ManagementAudit audit;

    public WorkerManagementFacade(
            WorkerService workers,
            ManagementAudit audit
    ) {
        this.workers = workers;
        this.audit = audit;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return workers.isPaused();
    }

    @ManagedOperation(description = "Pause background workers")
    public void pause() {
        long started = System.nanoTime();
        String actor = audit.resolveVerifiedActorOrUnknown();

        try {
            workers.pause();
            audit.recordSuccess(
                actor,
                "app.management:type=WorkerPool,name=background",
                "pause",
                System.nanoTime() - started
            );
        } catch (RuntimeException e) {
            audit.recordFailure(
                actor,
                "app.management:type=WorkerPool,name=background",
                "pause",
                e.getClass().getSimpleName()
            );
            throw e;
        }
    }
}
\`\`\`

\`ManagementAudit\` là abstraction **do ứng dụng tự thiết kế**, không phải một Spring Framework API có sẵn. Nó cần định nghĩa cách lấy actor, ghi log, xử lý lỗi logging và bảo đảm thời gian đo bằng nanoseconds được chuyển sang đơn vị mà schema audit sử dụng.

Ví dụ chủ ý không ghi exception message vì message đôi khi chứa dữ liệu nhạy cảm. Một logger thật có thể ghi mã lỗi chuẩn hóa và correlation ID.

### Một interface audit tối thiểu

\`\`\`java
public interface ManagementAudit {

    String resolveVerifiedActorOrUnknown();

    void recordSuccess(
        String actor,
        String objectName,
        String operation,
        long elapsedNanos
    );

    void recordFailure(
        String actor,
        String objectName,
        String operation,
        String reasonCode
    );
}
\`\`\`

\`resolveVerifiedActorOrUnknown()\` không được tự đoán người gọi từ hostname hoặc OS account. Nếu không có thông tin từ connector đáng tin cậy, trả về \`UNKNOWN\` hoặc một định danh hệ thống đã được xác định rõ.

## 9. Audit từ chối quyền truy cập

Một operation có thể bị từ chối **trước khi method facade được gọi**, ví dụ trong connector authorization hoặc MBeanServer access-control layer.

Khi đó, \`try/catch\` bên trong \`@ManagedOperation\` **không thể ghi nhận sự kiện DENIED** bởi method không hề được thực thi.

\`\`\`text
Client
   |
   v
Authorization check
   |
   +--> DENIED --> ghi audit ở security/connector layer
   |
   v
Facade method được gọi
   |
   +--> SUCCESS/FAILED --> ghi audit tại operation
\`\`\`

Vì vậy audit hoàn chỉnh cần tính đến cả các lần gọi **bị từ chối trước lớp business**.

Nếu dùng security proxy/gateway trước connector, cần bảo đảm log security được liên kết với phiên quản trị. Không tự tạo một authorization check khác trong facade rồi coi nó là thay thế cho kết nối JMX được bảo vệ.

## 10. Audit read attribute hay chỉ operation?

Không phải mọi hoạt động JMX đều là \`invoke\`:

\`\`\`java
connection.getAttribute(name, "QueueDepth");
connection.setAttribute(
    name,
    new Attribute("MaxWorkers", 16)
);
connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

Có ba loại hành động khác nhau:

| Hành động | Ví dụ | Mức ưu tiên audit |
|---|---|---|
| Attribute read | \`getAttribute("QueueDepth")\` | Tùy độ nhạy và lượng truy vấn |
| Attribute write | \`setAttribute("MaxWorkers")\` | Nên audit vì thay đổi trạng thái |
| Operation invoke | \`invoke("pause")\` | Nên audit các operation có tác dụng phụ |

Với attribute read có tần suất rất cao, log từng lần đọc có thể tạo nhiều dữ liệu. Hãy xác định policy theo độ nhạy và nhu cầu compliance. Có thể dùng metric truy cập tổng hợp cho các chỉ số bình thường, nhưng cần audit chi tiết đối với dữ liệu nhạy cảm hoặc hành động quản trị quan trọng.

Nếu chọn audit writable attribute, không chỉ instrument \`@ManagedOperation\` vì setter quản trị đi qua \`setAttribute\`, không phải operation cùng tên trong mọi mô hình.

## 11. AOP có thể giúp audit nhưng không thay thế kiến trúc security

Spring AOP có thể dùng một aspect để ghi log cho các method thuộc management facade:

\`\`\`java
@Aspect
@Component
public class ManagementAuditAspect {

    private final ManagementAudit audit;

    public ManagementAuditAspect(ManagementAudit audit) {
        this.audit = audit;
    }

    @Around(
        "execution(* com.example.management.*ManagementFacade.*(..))"
    )
    public Object around(ProceedingJoinPoint pjp)
            throws Throwable {

        long start = System.nanoTime();
        String actor = audit.resolveVerifiedActorOrUnknown();
        String method = pjp.getSignature().getName();

        try {
            Object result = pjp.proceed();
            audit.recordSuccess(
                actor,
                "management-facade",
                method,
                System.nanoTime() - start
            );
            return result;
        } catch (Throwable error) {
            audit.recordFailure(
                actor,
                "management-facade",
                method,
                error.getClass().getSimpleName()
            );
            throw error;
        }
    }
}
\`\`\`

Ví dụ giả định có Spring AOP và AspectJ annotation support phù hợp, cùng import các class \`Aspect\`, \`Around\`, \`ProceedingJoinPoint\` và \`Component\`.

Giới hạn cần hiểu:

- Nếu exporter tham chiếu trực tiếp target thay vì Spring AOP proxy, advice có thể bị bỏ qua.
- Self-invocation qua \`this.method()\` thường không kích hoạt advice mới.
- \`@ManagedAttribute\` getter/setter có thể cần chính sách audit riêng.
- Advice không chạy khi connector từ chối trước khi method được invoke.
- Actor vẫn chỉ đáng tin khi resolver có nguồn identity đáng tin.

Không ghi toàn bộ \`pjp.getArgs()\` mặc định: đối số có thể chứa credentials, payload nghiệp vụ hoặc dữ liệu cá nhân.

## 12. Kết quả: SUCCESS khác ACCEPTED

Một operation đồng bộ:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    counters.reset();
}
\`\`\`

Nếu trả về không có exception, thao tác đồng bộ có thể được ghi là \`SUCCESS\`, theo hợp đồng method.

Nhưng operation bất đồng bộ:

\`\`\`java
@ManagedOperation
public String requestRebuild() {
    return jobs.enqueueRebuild();
}
\`\`\`

chỉ xác nhận yêu cầu đã được đưa vào queue. Audit nên ghi:

\`\`\`json
{
  "operation": "requestRebuild",
  "outcome": "ACCEPTED",
  "jobId": "job-019"
}
\`\`\`

Khi worker hoàn thành, một sự kiện khác:

\`\`\`json
{
  "event": "management.job.completed",
  "jobId": "job-019",
  "outcome": "SUCCESS"
}
\`\`\`

Không ghi \`SUCCESS\` cho toàn bộ công việc chỉ vì lời gọi enqueue đã trả về. Correlation ID hoặc job ID giúp nối audit command với execution result.

## 13. Audit notification không giống audit command

JMX notification có thể ghi nhận biến đổi trạng thái:

\`\`\`text
app.worker.paused
app.cache.refreshed
app.job.completed
\`\`\`

Nhưng notification không tự chứng minh ai đã thực hiện thao tác.

Một event \`app.worker.paused\` có thể xảy ra do:

- Operator gọi JMX operation.
- Tác vụ nội bộ tự động pause.
- Scheduler hoặc business rule thay đổi trạng thái.
- Một API khác ngoài JMX làm cùng hành động.

Nếu cần gắn danh tính, audit command phải lấy actor từ security context đáng tin và sinh correlation ID; event trạng thái có thể tham chiếu correlation ID đó khi hợp đồng cho phép.

**Notification không mặc định là audit log bền vững.** Listener có thể chưa được đăng ký, mất kết nối, hoặc MBean bị unregister. Với audit quan trọng, dùng một audit sink có khả năng lưu trữ và chính sách retention/immutability phù hợp.

## 14. Bảo vệ dữ liệu trong audit log

Không ghi:

- Mật khẩu hoặc token dùng để đăng nhập JMX.
- \`Authorization\` headers, keystore password hoặc private key.
- Toàn bộ environment variables/system properties.
- Đối tượng Java được \`toString()\` có thể chứa secret.
- Payload \`Notification.userData\` chưa được phân loại.
- Dữ liệu cá nhân không cần thiết cho mục đích audit.

Một operation ví dụ:

\`\`\`java
@ManagedOperation
public void rotateCredentials(String secret) { ... }
\`\`\`

Nếu audit tất cả arguments bằng:

\`\`\`java
log.info("args={}", Arrays.toString(args));
\`\`\`

sẽ vô tình sao chép secret vào log. Giải pháp không chỉ là masking sau khi log; tốt hơn là **không thiết kế JMX operation nhận secret dạng plain text** khi có một cơ chế quản lý secret khác an toàn hơn.

### Allowlist tham số được ghi

Ví dụ một operation:

\`\`\`text
resizeWorkers(int workers)
\`\`\`

có thể log giá trị \`workers=16\` nếu policy cho phép. Với \`refreshCache(String cacheName)\`, có thể log tên cache nếu không chứa dữ liệu nhạy cảm. Với operation nhận password/token, chỉ ghi \`argumentPresent=true\` hoặc mã thao tác, không ghi giá trị.

## 15. Định danh người gọi qua bastion hoặc gateway

Trong một tổ chức, operator có thể đi qua bastion hoặc gateway trước khi tới JMX connector.

\`\`\`text
Operator identity
      |
      v
Bastion / privileged access manager
      |
      v
JMX connector (service account)
      |
      v
MBeanServer
\`\`\`

Nếu JMX connector chỉ thấy một service account dùng chung, audit tại JVM không thể tự phân biệt từng người. Cần liên kết:

1. Session ID hoặc ticket ID từ bastion/PAM.
2. Danh tính operator đã xác thực ở gateway.
3. Thời gian kết nối/đóng session.
4. Định danh service account tới JMX.
5. Audit operation ở server nếu có cơ chế correlation đáng tin.

Cần thiết kế đường truyền identity có kiểm soát; không đơn thuần tin một \`operatorName\` do client truyền vào.

## 16. Một chiến lược actor resolution an toàn

Nếu audit component không thể xác định người dùng:

\`\`\`java
public enum ActorSource {
    AUTHENTICATED_JMX_SUBJECT,
    TRUSTED_MANAGEMENT_GATEWAY,
    APPLICATION_SYSTEM,
    UNKNOWN
}
\`\`\`

Ghi \`actorSource\` cùng \`actor\`. Ví dụ:

\`\`\`json
{
  "actor": "UNKNOWN",
  "actorSource": "UNKNOWN",
  "operation": "pause",
  "outcome": "SUCCESS"
}
\`\`\`

Dữ liệu audit thiếu danh tính là một vấn đề cần cải thiện trong hạ tầng identity, nhưng **thành thật ghi unknown tốt hơn tạo danh tính giả**.

Cũng nên phân biệt actor là người hay service account: một monitoring agent có thể gọi operation để điều chỉnh cấu hình tự động. Trường \`actorType\` có thể nhận \`HUMAN\` hoặc \`SERVICE\` khi xác định được từ identity system.

## 17. Ghi log thất bại mà không che mất lỗi chính

Giả sử business operation lỗi và audit sink cũng lỗi. Có hai lựa chọn kiến trúc:

- **Best-effort audit:** ghi lỗi audit riêng, không chặn operation; phù hợp một số metric/low-risk action nhưng có thể mất bằng chứng.
- **Fail-closed audit:** không cho thực hiện action nếu không thể ghi audit trước theo chính sách; phù hợp hành động rất nhạy cảm, nhưng cần thiết kế transaction/idempotency rõ.

Không có một lựa chọn đúng cho mọi hệ thống. Điều cần tránh là exception của audit logger vô tình che mất exception nghiệp vụ mà không có dấu vết.

Nếu audit bắt buộc, nên có cơ chế bền vững như append-only event store, outbox hoặc queue với retry hợp lý. Nhưng phải xác định ranh giới transaction và bảo đảm audit record không nhầm \`ACCEPTED\` thành \`COMPLETED\`.

## 18. Idempotency, retry và lệnh có tác dụng phụ

JMX remote có thể gặp timeout sau khi server đã thực thi operation nhưng trước khi client nhận response.

\`\`\`text
Client invoke("reset")
       |
       v
Server thực thi reset thành công
       |
       X response bị mất
       |
Client thấy timeout
\`\`\`

Nếu client retry mù, một thao tác không idempotent có thể chạy hai lần.

Đối với operation quan trọng, cân nhắc:

- Mã yêu cầu/correlation ID.
- Idempotency key được quản lý đáng tin, không chứa secret.
- Audit trạng thái \`REQUESTED\`, \`ACCEPTED\`, \`COMPLETED\`, \`FAILED\`.
- Cơ chế tra cứu kết quả theo request ID.
- Chính sách retry có giới hạn và hiểu tác dụng phụ.

Audit cần phản ánh **điều thực sự xảy ra ở server**, không chỉ những gì client cho rằng đã xảy ra.

## 19. Kiểm chứng audit bằng integration test

Một bài test có thể dùng MBeanServer riêng:

\`\`\`java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("audit.test");
\`\`\`

Sau đó:

1. Đăng ký một MBean façade hoặc khởi tạo Spring context export MBean vào server này.
2. Dùng một \`ManagementAudit\` implementation trong bộ nhớ để thu các audit records.
3. Gọi operation \`pause()\` qua \`MBeanServer.invoke\`.
4. Xác nhận business operation có tác dụng dự kiến.
5. Xác nhận audit event có ObjectName, operation, outcome, timestamp và actor source.
6. Tạo một lỗi nghiệp vụ rồi xác nhận outcome \`FAILED\`.
7. Kiểm tra không có secret trong audit payload.
8. Nếu có security integration, kiểm tra riêng case \`DENIED\` ở nơi authorization thực sự thực thi.
9. Đóng context và unregister MBean test để không ảnh hưởng các test khác.

Ví dụ assertion ý tưởng:

\`\`\`java
server.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);

assertTrue(workerService.isPaused());
assertEquals("pause", audit.lastEvent().operation());
assertEquals("SUCCESS", audit.lastEvent().outcome());
\`\`\`

Đây là phác thảo test có những class/fixture do ứng dụng tự cung cấp, không phải đoạn độc lập đầy đủ.

## 20. Kiểm tra đường đi có bỏ qua AOP không

Nếu audit được áp dụng qua Spring AOP, phải xác nhận exporter gọi đúng Spring proxy.

\`\`\`text
Client
   |
   v
MBeanServer
   |
   v
Exporter target reference
   |
   +--> Spring proxy -> AuditAspect -> business target
   |
   +--> Target trực tiếp -> không qua AuditAspect
\`\`\`

Với service dùng JDK dynamic proxy, chỉ các method trên proxy interface có thể gọi qua proxy theo quy tắc tương ứng. Một management facade riêng thường dễ kiểm soát hơn khi cần audit và authorization có chủ đích.

Dùng \`MBeanInfo\` kiểm tra operation có được expose, rồi gọi operation trong integration test để xác nhận audit interceptor thật sự chạy. Có metadata không có nghĩa audit advice chắc chắn được thực thi.

## 21. Audit ở mức MBeanServerConnection và MBeanServer

Một client có thể bọc \`MBeanServerConnection\` để ghi:

\`\`\`java
connection.invoke(name, operation, params, signature);
\`\`\`

Nhưng log phía client có giới hạn:

- Client có thể bị chỉnh sửa hoặc bỏ qua wrapper.
- Một client khác có thể kết nối trực tiếp.
- Client không nhất thiết biết kết quả business cuối cùng.
- Client log có thể bị mất khi process crash.
- Danh tính client tự khai báo không chứng minh user thật.

Với yêu cầu audit bắt buộc cho mọi lệnh, nên có cơ chế ghi ở **server-side security/invocation boundary** hoặc management facade/service mà mọi đường thay đổi trạng thái đều đi qua.

Không có một public Spring JMX annotation tự động audit toàn bộ MBeanServer. Cần kết hợp công cụ phù hợp với connector, platform và yêu cầu vận hành.

## 22. Audit setAttribute

Một writable attribute:

\`\`\`java
@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    // ...
}
\`\`\`

Client có thể thay đổi qua:

\`\`\`java
connection.setAttribute(
    name,
    new Attribute("MaxWorkers", 16)
);
\`\`\`

Nếu chỉ audit \`@ManagedOperation\`, thao tác này có thể bị bỏ sót. Nên kiểm soát trong setter hoặc một tầng audit phù hợp để bao phủ \`setAttribute\`.

Một hướng thiết kế là không expose writable attribute cho thay đổi quan trọng, thay bằng một \`@ManagedOperation\` có validation và audit rõ ràng:

\`\`\`java
@ManagedOperation(description = "Change worker limit")
public void changeWorkerLimit(int value) {
    // Validate + authorization + audit + mutate.
}
\`\`\`

Đây không phải quy tắc bắt buộc; writable attribute vẫn hợp lệ. Mục tiêu là đảm bảo các đường thay đổi trạng thái đều có cùng kiểm soát cần thiết.

## 23. Retention, integrity và truy cập audit

Một audit log có giá trị khi có thể tìm lại và tin cậy.

Cần xác định:

- **Retention**: giữ bao lâu theo yêu cầu tổ chức/pháp lý.
- **Access control**: ai được xem bản ghi audit.
- **Integrity**: hạn chế sửa/xóa trái phép; cơ chế append-only hoặc immutable storage nếu cần.
- **Time synchronization**: dùng clock đồng bộ giữa node, ghi timestamp UTC.
- **Correlation**: request ID, job ID, session ID và instance ID.
- **Privacy**: chỉ ghi dữ liệu cần thiết; áp dụng masking và retention phù hợp.
- **Failure handling**: phát hiện khi audit sink không hoạt động.
- **Monitoring**: cảnh báo khi đột ngột có nhiều thao tác quản trị hoặc nhiều lệnh bị từ chối.

Đối với hành động nghiêm trọng, audit trail nên nằm ngoài process quản trị hoặc được xuất tới hệ thống tập trung có chính sách lưu trữ phù hợp. Nếu chỉ ghi vào log local rồi container bị xóa, bằng chứng có thể biến mất.

## 24. Những sai lầm thường gặp

### 24.1. Tưởng JMX có username là Spring biết caller

JMX connector có thể xác thực một principal, nhưng không bảo đảm mọi method Spring nhận được identity trong \`SecurityContextHolder\`. Spring Security HTTP context và JMX security subject là hai luồng khác nhau, cần tích hợp có chủ đích.

### 24.2. Dùng IP làm danh tính người vận hành

IP có thể là NAT, proxy, bastion hoặc agent. Nó hữu ích làm metadata kết nối nếu có nguồn đáng tin, nhưng không phải bằng chứng cá nhân.

### 24.3. Dùng username do method parameter truyền vào

Đây là claimed identity, dễ giả mạo. Chỉ dùng để hiển thị bổ sung nếu cần, không thay verified actor.

### 24.4. Log toàn bộ tham số

Có thể làm lộ secret, token hoặc thông tin cá nhân. Audit bằng allowlist field và loại bỏ payload nhạy cảm.

### 24.5. Chỉ ghi SUCCESS khi method trả về

Với operation bất đồng bộ, điều đó chỉ có thể phản ánh request đã được chấp nhận. Cần log kết quả cuối của job riêng.

### 24.6. Chỉ audit JMX invoke

Bỏ sót \`setAttribute\`, các thao tác bị security layer từ chối và các đường thay đổi trạng thái ngoài JMX.

### 24.7. Chỉ log ở client

Client có thể không đáng tin hoặc không bao phủ mọi lối gọi. Nên đặt audit server-side ở boundary thích hợp.

### 24.8. Gắn aspect nhưng exporter bypass proxy

Advice có thể không chạy nếu exporter giữ target trực tiếp. Cần test invocation từ MBeanServer thực tế.

## 25. Checklist thiết kế audit JMX

- [ ] Đã phân loại các MBean operations và writable attributes có tác dụng phụ.
- [ ] Có policy xác thực và phân quyền phù hợp với JMX connector.
- [ ] Định nghĩa rõ actor từ nguồn đáng tin, có \`UNKNOWN\` khi không xác định được.
- [ ] Không dùng OS user, IP hoặc client-supplied username làm verified identity.
- [ ] Ghi ObjectName, operation, signature, timestamp, outcome và instance.
- [ ] Có correlation ID/job ID cho thao tác bất đồng bộ.
- [ ] Không ghi secret hoặc payload nhạy cảm vào audit.
- [ ] Có cơ chế ghi DENIED tại tầng authorization.
- [ ] Bao phủ cả \`setAttribute\` khi nó thay đổi trạng thái.
- [ ] Có xử lý audit sink failure phù hợp mức độ quan trọng.
- [ ] Có chính sách retention, integrity và quyền truy cập audit.
- [ ] Đã integration-test đường gọi JMX thực sự qua exporter/proxy.
- [ ] Remote JMX chỉ được mở cho client được phép, có TLS/auth phù hợp.

## 26. Tình huống thực hành

**Bối cảnh:** một Spring Boot ứng dụng expose MBean \`app.management:type=Scheduler,name=main\`. JMX operation \`resume()\` được gọi qua một bastion bằng shared service account.

**Câu hỏi A:** Có thể ghi “Nguyễn Văn A đã gọi resume” chỉ dựa trên account \`jmx-admin\` không?

Không. Audit ở JVM chỉ biết service account đã được dùng. Muốn có danh tính cá nhân cần thông tin session identity đáng tin từ bastion/PAM và cơ chế correlation.

**Câu hỏi B:** Nếu \`resume()\` được phép nhưng task bên dưới lỗi sau khi chạy 30 giây, outcome nào nên ghi?

Nếu \`resume\` chỉ enqueue công việc, audit invocation nên ghi \`ACCEPTED\`; worker xử lý xong mới ghi event \`COMPLETED\` hoặc \`FAILED\` theo job ID.

**Câu hỏi C:** Nếu người gọi bị JMX security layer từ chối trước method, audit trong \`resume()\` có ghi được không?

Không. Phải audit sự kiện DENIED tại tầng xử lý authentication/authorization.

**Câu hỏi D:** Nếu \`MaxWorkers\` được thay qua \`setAttribute\`, một aspect chỉ intercept \`@ManagedOperation\` có bao phủ không?

Không bảo đảm. Cần audit setter/attribute-write hoặc security boundary phù hợp.

## 27. Câu hỏi tự kiểm tra

1. Authentication khác audit ở điểm nào?
2. Vì sao \`System.getProperty("user.name")\` không đủ làm verified actor?
3. Khi dùng shared JMX account, có thể chứng minh cá nhân nào thực hiện operation không?
4. Vì sao thao tác DENIED cần được ghi ngoài management facade?
5. \`setAttribute\` có phải \`invoke\` operation thông thường không?
6. Vì sao không log toàn bộ \`params\` hoặc \`Notification.userData\`?
7. Audit \`ACCEPTED\` khác \`SUCCESS\` như thế nào?
8. Nếu JMX remote timeout sau khi operation đã chạy, retry mù có thể gây vấn đề gì?
9. Vì sao một audit aspect có thể bị bypass trong ứng dụng Spring AOP?
10. Đâu là các trường tối thiểu để truy vết lời gọi quản trị?

## 28. Ghi nhớ

\`\`\`text
JMX caller
    |
    +--> Authentication -> identity/subject đáng tin nếu có
    |
    +--> Authorization -> ALLOW / DENY
    |         |
    |         +--> Audit DENIED ở security boundary
    |
    +--> MBean invocation / attribute write
              |
              v
        Management facade / service
              |
              +--> Audit request + actor + ObjectName + operation
              |
              +--> Business action
                       |
                       +--> SUCCESS / FAILED
                       +--> ACCEPTED -> later job outcome
\`\`\`

**Nguyên tắc cốt lõi:** audit lời gọi quản trị JMX phải ghi được **hành động, thời gian, tài nguyên, kết quả và danh tính có mức độ tin cậy rõ ràng**. Không giả định mọi JMX invocation đều cung cấp user identity; không coi credential chung là danh tính cá nhân và không xem notification là audit trail bền vững. Bảo vệ cả operation, writable attribute, thao tác bị từ chối và hành động bất đồng bộ; đồng thời giữ audit log không chứa dữ liệu nhạy cảm.