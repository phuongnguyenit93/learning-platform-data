# Không biến JMX thành API nghiệp vụ thay thế

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Thiết kế management API  
> **Bài học:** Không biến JMX thành API nghiệp vụ thay thế

## 1. Mục tiêu

JMX (Java Management Extensions) rất hữu ích để quan sát và điều khiển một ứng dụng Java đang chạy. Tuy nhiên, việc Spring Framework có thể export một phương thức dưới dạng \`@ManagedOperation\` **không có nghĩa phương thức đó nên trở thành kênh nghiệp vụ chính**.

Sau bài học, bạn có thể:

- Phân biệt **management API** với **business API** theo mục tiêu, người gọi, tần suất và tính ổn định của hợp đồng.
- Nhận diện dấu hiệu JMX đang bị lạm dụng để xử lý đơn hàng, thanh toán, truy vấn khách hàng hoặc tích hợp hệ thống.
- Giải thích vì sao JMX/RMI không tự cung cấp semantics của một API nghiệp vụ hiện đại: authentication theo người dùng, authorization theo tài nguyên, versioning, idempotency, schema, pagination, retry hoặc distributed tracing.
- Thiết kế **management facade** nhỏ, ít quyền, tách khỏi service nghiệp vụ.
- Lựa chọn giữa JMX, HTTP API, messaging, scheduler và observability tools theo mục đích.
- Giữ JMX operations an toàn, có audit và có thể kiểm thử qua \`MBeanServer\`.

## 2. JMX được thiết kế cho việc gì?

JMX cung cấp mô hình quản trị thông qua **MBean**, **ObjectName**, **MBeanServer**, attribute, operation và notification.

\`\`\`text
               Application JVM
                       |
                Business services
                       |
            Management facade/adapter
                       |
                       v
                   MBeanServer
                       |
            +----------+----------+
            |                     |
         JConsole          Monitoring/JMX client
            |
     Đọc tình trạng, điều chỉnh cấu hình,
     khởi chạy thao tác vận hành hữu hạn
\`\`\`

Những công việc JMX thường phù hợp:

- Đọc số lượng worker đang hoạt động, queue depth, cache hit ratio hoặc trạng thái kết nối.
- Xem phiên bản cấu hình, thời điểm refresh gần nhất, số lần lỗi.
- Điều chỉnh giới hạn vận hành có kiểm soát, chẳng hạn số worker hoặc timeout trong phạm vi an toàn.
- Tạm dừng/tiếp tục một thành phần để xử lý sự cố.
- Yêu cầu refresh cache, reload configuration hoặc reset counter.
- Nhận notification khi có biến cố vận hành đáng chú ý.

Các thao tác này **quản trị cách ứng dụng vận hành**. Chúng không nên thay thế đường xử lý nghiệp vụ bình thường mà người dùng hoặc hệ thống khác phụ thuộc.

## 3. Business API và management API khác nhau thế nào?

| Tiêu chí | Business API | JMX management API |
|---|---|---|
| Mục đích | Thực hiện use case của sản phẩm | Quan sát và kiểm soát runtime |
| Người gọi | Frontend, đối tác, service, batch worker | Operator, SRE, monitoring/automation được phép |
| Tần suất | Có thể rất cao | Thường thấp, không nằm trong hot path |
| Dữ liệu | Domain objects, request/response có schema | Kiểu quản trị gọn, dễ hiểu, có metadata |
| Authorization | Theo user, tenant, tài nguyên, action | Theo kênh quản trị và chính sách MBean/operation |
| Versioning | Hợp đồng API công khai với deprecation | Hợp đồng ObjectName/attribute/operation cần quản lý riêng |
| Reliability | Retry, idempotency, queues, SLO và error contract | Phụ thuộc JMX connector và logic do ứng dụng bổ sung |
| Audit | Theo sự kiện nghiệp vụ và actor | Theo thao tác quản trị, actor xác thực nếu có |
| Transport | HTTP/gRPC/messaging v.v. | Local JMX hoặc remote connector như RMI |
| Kỳ vọng client | SDK, service discovery, gateway | JConsole, VisualVM, JMX client hoặc monitoring agent |

JMX có operation nên **về kỹ thuật** vẫn có thể gọi logic nghiệp vụ. Nhưng khả năng gọi được không chứng minh rằng đây là đường giao tiếp phù hợp, an toàn hoặc ổn định.

## 4. Anti-pattern: đưa toàn bộ business service lên JMX

Giả sử hệ thống đơn hàng có service:

\`\`\`java
public interface OrderService {
    Order createOrder(CreateOrderRequest request);
    void cancelOrder(String orderId);
    PaymentResult charge(String orderId, PaymentDetails details);
    Order getOrder(String orderId);
}
\`\`\`

Một lựa chọn sai là expose các method này như management operations:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.management:type=OrderService,name=main"
)
public class OrderServiceMBean {

    private final OrderService orders;

    public OrderServiceMBean(OrderService orders) {
        this.orders = orders;
    }

    @ManagedOperation
    public Order createOrder(CreateOrderRequest request) {
        return orders.createOrder(request);
    }

    @ManagedOperation
    public PaymentResult charge(
            String orderId,
            PaymentDetails details
    ) {
        return orders.charge(orderId, details);
    }
}
\`\`\`

Vấn đề không chỉ là kiểu dữ liệu \`CreateOrderRequest\` khó nhập trong JConsole. Quan trọng hơn:

1. Kênh JMX có thể bypass một số lớp business API gateway và HTTP authorization.
2. Client quản trị có thể trở thành một con đường tạo giao dịch không được giám sát giống business API.
3. Business DTO tạo coupling classpath/serialization giữa JVM và client JMX.
4. Retry, duplicate command, audit và rate limiting không tự được JMX xử lý.
5. Remote JMX connector là bề mặt đặc quyền cao, không nên mở cho user traffic.
6. Mọi thay đổi service có thể trở thành thay đổi JMX contract.
7. Khó vận hành theo mô hình multi-tenant và identity từng người dùng cuối.

Không thêm \`@ManagedOperation\` chỉ vì method public sẵn có và muốn “gọi nhanh từ bên ngoài”.

## 5. Nguyên tắc: JMX quản lý hệ thống, business API thực hiện nghiệp vụ

\`\`\`text
Customer / frontend / integration
                 |
                 v
           Business API
       (HTTP/gRPC/message)
                 |
           Authentication
           Authorization
           Validation
           Transaction
           Idempotency
           Audit
                 |
                 v
           Business service
                 ^
                 |
     Management facade (giới hạn thao tác)
                 ^
                 |
             JMX client
\`\`\`

Management facade có thể gọi service nghiệp vụ, nhưng chỉ thông qua **tập hành động vận hành nhỏ**, có ràng buộc và điều kiện rõ. Ví dụ “tạm dừng xử lý queue” khác với “tạo một triệu đơn hàng”; “khởi chạy lại batch theo job ID đã duyệt” khác với “thanh toán mọi đơn hàng do client truyền vào”.

JMX và business API có thể cùng dùng các dependency nội bộ. Điều đó **không** khiến JMX trở thành business API thay thế nếu phạm vi thao tác được kiểm soát.

## 6. Ví dụ đúng: management facade cho queue worker

Một service nghiệp vụ:

\`\`\`java
public interface OrderProcessingService {
    void processNextBatch();
    int pendingCount();
}
\`\`\`

Một interface quản trị riêng:

\`\`\`java
public interface WorkerManagement {
    int getPendingCount();
    int getActiveWorkers();
    void pause();
    void resume();
}
\`\`\`

Implementation facade:

\`\`\`java
package example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=WorkerPool,name=orders",
    description = "Order worker operations"
)
public class OrderWorkerManagement {

    private final WorkerCoordinator coordinator;

    public OrderWorkerManagement(
            WorkerCoordinator coordinator
    ) {
        this.coordinator = coordinator;
    }

    @ManagedAttribute(description = "Queued jobs")
    public int getPendingCount() {
        return coordinator.pendingCount();
    }

    @ManagedAttribute(description = "Active workers")
    public int getActiveWorkers() {
        return coordinator.activeWorkers();
    }

    @ManagedOperation(
        description = "Pause dispatch of new jobs"
    )
    public void pause() {
        coordinator.pauseDispatch();
    }

    @ManagedOperation(
        description = "Resume dispatch of new jobs"
    )
    public void resume() {
        coordinator.resumeDispatch();
    }
}
\`\`\`

\`WorkerCoordinator\` là dependency nghiệp vụ/vận hành giả định của ứng dụng. Nó cần cung cấp implementation, concurrency control, validation và policy phù hợp.

Facade này expose **điều khiển worker**, không expose \`processOrder(customerId, payment)\` hay API thanh toán trực tiếp. Đường thực thi nghiệp vụ vẫn chạy qua business service đã thiết kế.

## 7. Thiết kế theo nguyên tắc tối thiểu quyền

Một management API nên trả lời: operator cần kiểm tra hoặc điều khiển điều gì để vận hành hệ thống?

Ví dụ nên cân nhắc:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() { ... }

@ManagedOperation
public void pauseConsumers() { ... }

@ManagedOperation
public void resumeConsumers() { ... }
\`\`\`

Ví dụ cần tránh:

\`\`\`java
@ManagedOperation
public void deleteAllCustomerRecords() { ... }

@ManagedOperation
public String dumpApiTokens() { ... }

@ManagedOperation
public Object executeArbitraryCommand(String command) { ... }
\`\`\`

Ngay cả những operation “nội bộ” vẫn là đường vào có đặc quyền nếu client có quyền tương ứng. Không xem annotation \`@ManagedResource\` là cơ chế security. Nó quyết định bề mặt quản trị có thể được exporter công bố; authentication và authorization phải được xử lý ở các lớp thích hợp.

## 8. JMX không thay thế API gateway

Một business API thông thường có thể nằm sau:

- Authentication per-user.
- Authorization per-tenant và per-resource.
- Request validation.
- Rate limiting hoặc quota.
- Audit theo business transaction.
- Idempotency key.
- API versioning và contract schema.
- Observability với correlation ID.
- Timeout và retry policy.

JMX remote connector có cơ chế bảo mật riêng, nhưng không mặc định cung cấp tất cả semantics trên.

Ví dụ:

\`\`\`text
Business API:
POST /orders
Authorization: Bearer ...
Idempotency-Key: ...
Body: create order request

JMX:
MBeanServer.invoke(
  "app.management:type=OrderService,name=main",
  "createOrder",
  ...
)
\`\`\`

Đường JMX không tự thừa hưởng HTTP filter chain, API gateway policies hoặc identity của request người dùng. Nếu muốn bảo đảm cùng chính sách nghiệp vụ, phải thiết kế và kiểm chứng lại tại service boundary. Cách đơn giản và rõ ràng hơn là không expose use case đó qua JMX.

## 9. Loại thao tác quản trị nào có thể tác động business?

Không phải tất cả management operations đều read-only. Một thao tác vận hành hữu ích vẫn có thể ảnh hưởng luồng xử lý nghiệp vụ.

Ví dụ \`pauseConsumers()\` có thể tạm ngừng đơn hàng được xử lý; \`reloadRoutingRules()\` có thể thay đổi cách phân luồng message; \`refreshCache()\` có thể tạo tải.

Vì vậy cần phân loại:

| Loại | Ví dụ | Rủi ro cần quản lý |
|---|---|---|
| Quan sát | \`getPendingCount()\` | Lộ dữ liệu hoặc cardinality |
| Điều chỉnh có giới hạn | \`setMaxWorkers(int)\` | Giá trị quá lớn, resource exhaustion |
| Điều khiển vòng đời | \`pause()\`, \`resume()\` | Gián đoạn dịch vụ |
| Bảo trì | \`refreshCache()\`, \`resetCounters()\` | Tác dụng phụ, thiếu số liệu sau reset |
| Khởi chạy job | \`requestReindex()\` | Trùng job, tải cao, trạng thái bất đồng bộ |
| Thao tác phá hủy | \`purgeAllData()\` | Mất dữ liệu; thường không nên expose qua JMX |

Không có thao tác nào tự động an toàn chỉ vì tên gọi là “maintenance”. Phải xác định phạm vi, giới hạn, người được phép và phương án phục hồi.

## 10. Điều chỉnh runtime theo ràng buộc

Ví dụ điều chỉnh số worker:

\`\`\`java
@ManagedOperation(
    description = "Set maximum worker count"
)
public void setMaxWorkers(int requested) {
    if (requested < 1 || requested > 64) {
        throw new IllegalArgumentException(
            "requested must be 1..64"
        );
    }
    workerCoordinator.setMaxWorkers(requested);
}
\`\`\`

Giới hạn 1..64 chỉ là ví dụ. Trong hệ thống thật, phải căn cứ vào năng lực hệ thống và policy vận hành.

Một operation cần xác định:

1. Có thể gọi lặp lại an toàn không?
2. Giá trị nào hợp lệ?
3. Tác dụng phụ ra sao?
4. Mất bao lâu?
5. Nếu fail giữa chừng thì state thế nào?
6. Client có cách xác minh kết quả không?
7. Có cần audit trước/sau không?

\`void\` trả về không có nghĩa operation chắc chắn hoàn tất mọi tác vụ nền đã khởi chạy.

## 11. Management API nên dùng kiểu dữ liệu đơn giản

JMX client thường dễ làm việc với:

\`\`\`text
boolean
int
long
double
java.lang.String
java.lang.String[]
CompositeData
TabularData
\`\`\`

Ví dụ:

\`\`\`java
@ManagedOperation
public String requestCacheRefresh(String cacheName) {
    // Validate allowlist, submit job,
    // return job identifier
    return "job-123";
}
\`\`\`

Dễ tương tác hơn một operation nhận object nghiệp vụ sâu:

\`\`\`java
@ManagedOperation
public CacheRefreshResult execute(
        InternalRefreshOptions options,
        RequestContext context
) { ... }
\`\`\`

Object Java tùy biến không bị JMX cấm tuyệt đối, nhưng thường tạo phụ thuộc classpath/serialization, khó dùng với JConsole hoặc client khác, và làm lộ chi tiết domain.

Management contract nên ưu tiên dữ liệu tổng hợp, schema ổn định và có định nghĩa ràng buộc rõ. Nếu cần dữ liệu cấu trúc, cân nhắc MXBean/Open Types theo hợp đồng phù hợp.

## 12. ObjectName phải phản ánh vai trò quản trị

Không dùng class Java làm hợp đồng duy nhất:

\`\`\`text
com.example.internal:type=RedisOrderCacheService
\`\`\`

Nếu mục tiêu là quản trị logical cache, một tên ổn định hơn:

\`\`\`text
app.management:type=Cache,name=orders
\`\`\`

Client quản trị không cần biết \`RedisOrderCacheService\` đã đổi thành \`CaffeineOrderCacheService\` nếu contract JMX không thay đổi.

Bề mặt quản trị cần được quản lý như một API nhỏ:

- ObjectName.
- Attribute names và types.
- Operation names, parameter signatures và return types.
- Notification types nếu có.
- Authentication/authorization expectations.
- Semantics, side effects và lifecycle.

Nên tránh đổi các phần này vô tình theo việc refactor implementation.

## 13. Khi nào cần HTTP, gRPC hoặc message queue thay vì JMX?

### HTTP hoặc gRPC

Phù hợp khi:

- Nhiều service hoặc người dùng cần gọi nghiệp vụ.
- Có hợp đồng request/response rõ ràng.
- Cần gateway, auth theo user, rate limiting và versioning.
- Cần tích hợp từ nhiều ngôn ngữ, không chỉ Java.
- Cần tracing hoặc policy quản trị API độc lập với JVM.

### Messaging

Phù hợp khi:

- Có job bất đồng bộ, khối lượng lớn hoặc cần retry.
- Có yêu cầu xử lý có độ tin cậy cao với durable queue.
- Phải tách thời gian gửi yêu cầu khỏi thời gian xử lý.
- Cần dead-letter handling, backpressure hoặc consumer groups.

### Scheduler/workflow system

Phù hợp khi:

- Chạy nghiệp vụ theo lịch hoặc quy trình nhiều bước.
- Cần xem trạng thái, retries, approvals, checkpoints.
- Cần governance riêng cho các hoạt động dài hạn.

### JMX

Phù hợp khi:

- Operator cần đọc trạng thái nội bộ của JVM và ứng dụng.
- Cần điều khiển hữu hạn khi debug hoặc khắc phục sự cố.
- Client dự kiến là JConsole, monitoring agent hoặc công cụ JMX.
- Tần suất thao tác thấp và quyền sử dụng được giới hạn chặt.

**Lựa chọn dựa trên yêu cầu**, không phải chỉ dựa vào cách nào viết ít code hơn.

## 14. Spring Boot Actuator và JMX

Spring Boot Actuator cung cấp các endpoint phục vụ vận hành như health, info và metrics tùy dependency/cấu hình. Endpoint có thể được expose qua HTTP hoặc JMX theo chính sách exposure tương ứng.

\`\`\`text
Actuator endpoint model
      |
      +--> HTTP exposure
      |
      +--> JMX exposure -> MBeanServer
\`\`\`

Điều này không làm Actuator trở thành business API. Một custom Actuator endpoint có write operation vẫn cần cân nhắc tác dụng phụ và security.

Các cấu hình như:

\`\`\`properties
management.endpoints.jmx.exposure.include=health,info
\`\`\`

điều khiển Actuator JMX exposure cho phiên bản Boot phù hợp, **không tự mở remote JMX port**. Spring \`@ManagedResource\` và Actuator \`@Endpoint\` là hai cách mô tả quản trị khác nhau.

Nếu bài toán là metrics/time-series hoặc health check, cân nhắc Actuator và hệ thống observability thay vì tạo một MBean nghiệp vụ tùy biến cho mọi use case.

## 15. Rủi ro về performance và throughput

JMX invocation đi qua hạ tầng quản trị và có thể phát sinh metadata lookup, serialization hoặc network I/O với remote connector.

Không nên dùng đường:

\`\`\`text
API request -> remote JMX -> business processing
\`\`\`

cho hàng nghìn request sản phẩm mỗi giây chỉ vì có thể gọi method Java qua JMX.

Rủi ro:

- Hệ thống monitoring cạnh tranh tài nguyên với business traffic.
- Một connector có thể trở thành bottleneck.
- Operation dài gây timeout, block thread hoặc tạo áp lực bộ nhớ.
- Chẩn đoán lỗi khó vì không có contract API nghiệp vụ đầy đủ.
- Retry có thể nhân đôi tác dụng phụ.
- Khi JMX connector lỗi, đường nghiệp vụ bị ngắt theo.

Đường business nên có SLA, concurrency controls, backpressure và transport thích hợp. JMX không được thiết kế như một thay thế tổng quát cho hệ thống giao dịch phân tán.

## 16. Rủi ro về identity và multi-tenancy

Một client JMX có thể xác thực vào connector bằng account quản trị. Nhưng danh tính đó không tự là end-user identity của từng business request.

Ví dụ business API cần kiểm tra:

\`\`\`text
User A được xem order #123?
Tenant B được đổi trạng thái item này?
Partner C có quota gọi API?
\`\`\`

Khi chuyển sang JMX, nhiều ứng dụng vô tình chỉ kiểm tra “ai có quyền kết nối JMX”, bỏ qua authorization theo domain object.

Không thiết kế:

\`\`\`java
@ManagedOperation
public Order getOrder(String orderId) { ... }
\`\`\`

như một đường truy xuất dữ liệu khách hàng chỉ vì team vận hành muốn tiện debug. Thay bằng metrics tổng hợp hoặc diagnostic có chính sách redaction/authorization phù hợp.

Đối với thông tin nhạy cảm, việc có ObjectName và method quản trị không thay thế privacy controls.

## 17. Audit cho thao tác quản trị

Operation thay đổi trạng thái cần ghi:

- Thời gian.
- ObjectName.
- Operation hoặc writable attribute.
- Danh tính được xác thực nếu có, và nguồn identity.
- Tham số đã được allowlist/masking.
- Kết quả: accepted, success, failed, denied.
- Correlation ID hoặc job ID.

Ví dụ audit event:

\`\`\`json
{
  "event": "management.operation",
  "objectName": "app.management:type=WorkerPool,name=orders",
  "operation": "pause",
  "actor": "jmx-operator",
  "actorSource": "authenticated-connector",
  "outcome": "SUCCESS"
}
\`\`\`

Đây là schema minh họa do ứng dụng thiết kế, không phải event tự động do Spring JMX tạo.

Nếu nhiều operator dùng shared credentials, backend không thể tự xác định người cụ thể chỉ từ tài khoản chung. Không tin một tham số \`requestedBy\` do client gửi như danh tính đã xác thực.

## 18. Job bất đồng bộ: trả request ID, không trả kết quả giả

Một operation quản trị đôi khi yêu cầu tác vụ nặng:

\`\`\`java
@ManagedOperation
public String requestReindex() {
    return jobCoordinator.scheduleReindex();
}
\`\`\`

Nếu method chỉ enqueue, kết quả JMX nên có nghĩa **đã chấp nhận yêu cầu** chứ không phải “đã reindex thành công”.

Một giao diện hợp lý:

\`\`\`java
@ManagedOperation
public String requestReindex() {
    return jobCoordinator.scheduleReindex();
}

@ManagedOperation
public String reindexStatus(String jobId) {
    return jobCoordinator.status(jobId);
}
\`\`\`

\`jobCoordinator\` là dependency ứng dụng giả định. Trong production phải có cơ chế tránh job trùng, giới hạn số job đang chạy và xử lý timeout.

Đối với workflow có độ tin cậy cao, cần lưu trạng thái qua hệ thống job phù hợp. JMX chỉ có thể là cổng vận hành để **yêu cầu/quan sát**, không nên tự đảm nhiệm toàn bộ workflow orchestration.

## 19. Xử lý retry và idempotency

Một client remote gọi:

\`\`\`java
connection.invoke(
    objectName,
    "requestReindex",
    new Object[0],
    new String[0]
);
\`\`\`

Có thể xảy ra:

\`\`\`text
Server nhận request
     |
     v
Job được enqueue
     |
     X response bị mất vì mạng
     |
Client timeout
\`\`\`

Client không thể chắc job chưa chạy. Nếu retry mù, hai job có thể cùng được enqueue.

Giải pháp có thể là:

- Dùng request ID do client quản trị tạo và service xác minh.
- Cung cấp operation tra cứu trạng thái của request.
- Thiết kế operation idempotent nếu phù hợp.
- Audit việc chấp nhận và hoàn thành riêng.
- Hạn chế retry khi chưa biết kết quả trước.

JMX không tự cung cấp idempotency-key protocol giống một business API được thiết kế riêng.

## 20. Vòng đời MBean và tính ổn định

JMX MBean có thể bị unregister khi:

- Spring ApplicationContext đóng.
- Exporter thay thế registration.
- Ứng dụng restart.
- Management module được reload.
- MBean được tạo/hủy động.

Nếu một hệ thống nghiệp vụ quan trọng phụ thuộc vào một ObjectName duy nhất để xử lý lệnh, lifecycle này có thể tạo sự cố.

Một business API cần availability và service routing được thiết kế ở mức dịch vụ, không phụ thuộc MBean đăng ký trên một JVM cụ thể.

\`RegistrationPolicy.REPLACE_EXISTING\` giải quyết xung đột ObjectName, không phải load balancing, failover hay zero-downtime upgrade.

## 21. Kiểm thử bề mặt quản trị, không chỉ happy path

Giả sử management facade chỉ nên công bố:

\`\`\`text
Attributes:
  PendingCount (read-only)
  ActiveWorkers (read-only)

Operations:
  pause()
  resume()
\`\`\`

Một integration test có thể đọc \`MBeanInfo\`:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=WorkerPool,name=orders"
);

MBeanInfo info = server.getMBeanInfo(name);

Set<String> operations = Arrays.stream(
    info.getOperations()
)
    .map(op -> op.getName())
    .collect(Collectors.toSet());

assertTrue(operations.contains("pause"));
assertTrue(operations.contains("resume"));
assertFalse(operations.contains("processCustomerPayment"));
\`\`\`

Đoạn này cần import các class Java/JMX và khởi tạo \`server\` từ integration-test context. Khi cần kiểm tra toàn bộ hợp đồng, so thêm signature và kiểu dữ liệu; assert một tên không tồn tại chỉ là kiểm tra tối thiểu.

Kiểm thử nên bao gồm:

1. ObjectName được đăng ký đúng.
2. Chỉ những attribute/operation được dự kiến xuất hiện.
3. Validation từ chối tham số ngoài giới hạn.
4. Operation có tác dụng phụ đúng phạm vi.
5. Audit ghi nhận kết quả.
6. Security integration chặn caller không đủ quyền.
7. Runtime error không để lại state hỏng.
8. Lifecycle startup/shutdown không tạo MBean trùng.

## 22. Quản trị quyền theo mức độ rủi ro

Không cần mọi người có quyền JMX đều được gọi mọi operation.

Một phân loại:

| Vai trò | Phạm vi phù hợp |
|---|---|
| Read-only monitoring | Đọc attribute/metrics không nhạy cảm |
| Operator | Một số thao tác pause/resume/reload có kiểm soát |
| Administrator | Thao tác cấu hình quan trọng theo approval |
| Automation account | Những operation cụ thể và có ràng buộc |
| Developer debug | Môi trường thử nghiệm, không mặc định production |

JMX connector có cơ chế security riêng; chi tiết authorization theo ObjectName/operation phụ thuộc hạ tầng, JDK, connector hoặc custom layer. Không mặc định chỉ cần kết nối là tất cả role được phân tách đúng.

Hãy bảo vệ đường quản trị bằng network isolation, authentication, TLS và hạn chế operation ở chính design của MBean.

## 23. Khi nào cần xóa management operation?

Một operation ban đầu hữu ích khi debug có thể trở thành rủi ro nếu tồn tại vĩnh viễn.

Ví dụ:

\`\`\`java
@ManagedOperation
public void forceCompleteAllPendingOrders() { ... }
\`\`\`

Nếu thao tác không còn nhu cầu vận hành rõ ràng hoặc quá nguy hiểm, nên loại khỏi management surface theo kế hoạch thay đổi hợp đồng.

Trước khi xóa:

- Kiểm kê tool/runbook/automation đang dùng.
- Xem xét hoạt động audit gần đây.
- Thông báo deprecation và migration nếu có client lâu dài.
- Chọn API nghiệp vụ hoặc workflow thích hợp nếu thực sự cần chức năng đó.
- Cập nhật kiểm thử MBeanInfo để bảo vệ bề mặt mới.

Không giữ một backdoor quản trị chỉ vì “có thể một ngày sẽ cần”.

## 24. Một kiến trúc tham chiếu

\`\`\`text
                     External clients
                            |
                 Business API Gateway
                            |
               HTTP/gRPC authentication
                            |
                  Business services
                            |
         +------------------+------------------+
         |                                     |
   Database / event bus                 Job scheduler
         ^
         |
   WorkerCoordinator
         ^
         |
   Management facade
         ^
         |
     MBeanServer
         ^
         |
  Restricted JMX connector
         ^
         |
        Operator
\`\`\`

Có thể chia sẻ business services phía sau, nhưng **đường nghiệp vụ** vẫn đi qua chính sách và transport của nó. **Đường quản trị** được giới hạn vào những khả năng vận hành đã định nghĩa.

## 25. Anti-pattern và cách sửa

### Anti-pattern A: Chuyển endpoint HTTP thành JMX vì “dễ kết nối JVM”

**Vấn đề:** HTTP endpoint có security, validation, tracing và versioning; JMX call có thể bỏ qua những lớp đó.

**Cách sửa:** giữ business endpoint. Nếu cần giám sát trạng thái endpoint, expose metrics/health qua JMX riêng.

### Anti-pattern B: Expose toàn bộ bean để tiện debug

**Vấn đề:** method có thể chứa chức năng nhạy cảm hoặc không ổn định.

**Cách sửa:** tạo \`@ManagedResource\` facade chỉ gồm methods đã duyệt.

### Anti-pattern C: Dùng MBean như integration point giữa các microservice

**Vấn đề:** liên kết chặt với JVM, ObjectName, RMI và class serialization, khó autoscaling và failover.

**Cách sửa:** dùng HTTP/gRPC/messaging hoặc workflow theo yêu cầu hệ thống.

### Anti-pattern D: Chạy một business batch dài qua JConsole

**Vấn đề:** timeout, retries và job lifecycle không rõ.

**Cách sửa:** dùng scheduler/job system; JMX chỉ request hoặc inspect state khi cần.

### Anti-pattern E: Dùng shared JMX account cho thao tác dữ liệu cá nhân

**Vấn đề:** khó truy vết danh tính, phạm vi quyền và privacy.

**Cách sửa:** dùng business/admin API có identity và authorization được thiết kế, hoặc quản lý privileged operations qua approval workflow.

## 26. Checklist thiết kế management API

- [ ] Mục tiêu operation là quan sát/điều khiển vận hành, không phải use case nghiệp vụ thường xuyên.
- [ ] Có lý do rõ ràng vì sao phải expose qua JMX.
- [ ] Hợp đồng JMX tách khỏi implementation/service interface nội bộ.
- [ ] ObjectName có ý nghĩa và ổn định.
- [ ] Chỉ expose attribute/operation cần thiết.
- [ ] Không trả secret, dữ liệu cá nhân hoặc object graph nghiệp vụ lớn.
- [ ] Kiểu tham số/kiểu trả về phù hợp với client quản trị.
- [ ] Input được validate với khoảng và allowlist.
- [ ] Tác dụng phụ có giới hạn, có cách xác minh kết quả.
- [ ] Operation bất đồng bộ có job ID và status riêng.
- [ ] Có audit và security theo mức độ rủi ro.
- [ ] Có chính sách retry/idempotency khi cần.
- [ ] Không yêu cầu throughput/SLA của business API từ JMX connector.
- [ ] Có integration test kiểm tra metadata và hành vi.
- [ ] Không sử dụng JMX như backdoor vượt business authorization.
- [ ] Có owner và kế hoạch deprecation cho management API.

## 27. Bài tập thực hành

**Bối cảnh:** ứng dụng có \`InventoryService\` với:

\`\`\`java
InventoryResult reserve(
    String sku,
    int quantity,
    String customerId
);

void release(String reservationId);

int currentStock(String sku);
\`\`\`

Team vận hành muốn dùng JConsole để “làm mọi việc nhanh”.

**Câu hỏi A:** Có nên export \`reserve\` và \`release\` trực tiếp qua JMX không?

Thông thường không. Đây là các use case nghiệp vụ gắn customer/reservation, cần authorization, transaction, idempotency và audit. Nên giữ trong business API/workflow.

**Câu hỏi B:** Nên expose gì để hỗ trợ vận hành?

Ví dụ management facade có:

\`\`\`java
@ManagedAttribute
public long getPendingReservations() { ... }

@ManagedAttribute
public boolean isReservationConsumerPaused() { ... }

@ManagedOperation
public void pauseReservationConsumer() { ... }

@ManagedOperation
public void resumeReservationConsumer() { ... }
\`\`\`

Những method này quản lý luồng xử lý, không trực tiếp thay đổi một reservation cụ thể.

**Câu hỏi C:** Nếu thực sự cần sửa một reservation lỗi trong production?

Dùng một admin workflow/business API có authorization, approval, audit và idempotency phù hợp. JMX không nên trở thành shortcut để bypass những yêu cầu đó.

## 28. Câu hỏi tự kiểm tra

1. Vì sao \`@ManagedOperation\` không nên được thêm vào mọi method public của service?
2. Tại sao JMX connector không thay thế một business API gateway?
3. JMX phù hợp với thao tác nào hơn: đọc queue depth hay tạo đơn hàng mới?
4. Management facade giúp tách domain API và management API ra sao?
5. Vì sao \`String\`/primitive thường dễ dùng hơn DTO nghiệp vụ trong JMX?
6. Khi một operation chỉ enqueue job, vì sao không nên trả “completed” ngay?
7. Nếu remote JMX timeout, client có biết operation đã chạy hay chưa không?
8. Vì sao ObjectName ổn định chưa đủ bảo đảm compatibility?
9. Khi nào nên chọn HTTP/gRPC/messaging thay cho JMX?
10. Làm sao kiểm tra không expose nhầm method nguy hiểm sau một lần refactor?

## 29. Ghi nhớ

\`\`\`text
Business API
   -> user-facing use cases
   -> domain authorization, transactions, idempotency
   -> normal request traffic

JMX Management API
   -> runtime visibility and limited control
   -> ObjectName, attributes, operations, notifications
   -> restricted operator/monitoring traffic

Không dùng JMX như business API thay thế.
\`\`\`

**Nguyên tắc cốt lõi:** **JMX là kênh quản trị, không phải đường thực thi nghiệp vụ thay thế.** Hãy công bố một management facade nhỏ, có ObjectName ổn định, có validation, audit và quyền phù hợp. Giữ các use case nghiệp vụ ở API/workflow được thiết kế cho throughput, identity, transaction, idempotency và khả năng mở rộng.