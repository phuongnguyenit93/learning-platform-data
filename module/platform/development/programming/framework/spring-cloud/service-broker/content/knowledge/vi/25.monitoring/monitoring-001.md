# Log có cấu trúc theo platform, instance, binding và operation

Trong module **SPRING_CLOUD_SERVICE_BROKER**, một request Open Service Broker API (OSB API) có thể đi qua nhiều thành phần trước khi hoàn tất: platform gửi HTTP request, broker xác thực và kiểm tra quyền, application service cập nhật trạng thái, database lưu instance/binding/operation, worker xử lý bất đồng bộ rồi provider adapter gọi hạ tầng. Khi xảy ra timeout hoặc lỗi, một dòng log chỉ ghi “provision failed” không đủ để xác định request thuộc foundation nào, instance nào, binding nào hay operation nào.

Log có cấu trúc (structured logging) giải quyết vấn đề bằng cách ghi mỗi sự kiện dưới dạng các field có tên và kiểu dữ liệu ổn định, thường được serialize thành JSON. Thay vì phải phân tích chuỗi message tự do, người vận hành có thể lọc theo platform, service instance, binding, operation, trace hoặc kết quả. Cách tổ chức này đặc biệt hữu ích khi broker phục vụ nhiều tenant, nhiều Cloud Foundry foundation hoặc Kubernetes cluster, đồng thời xử lý các operation bất đồng bộ.

Bài học này trình bày schema log cho vòng đời OSB, cách liên kết request với operation và provider call, cách truyền ngữ cảnh qua thread/queue, cấu hình logging trong Spring, bảo vệ dữ liệu nhạy cảm và vận hành log ở quy mô lớn. Mục tiêu là truy vết được một sự cố xuyên suốt hệ thống mà không biến log thành nơi lưu credentials hoặc dữ liệu cá nhân.

## 1. Structured logging khác log chuỗi tự do như thế nào?

Log chuỗi tự do thường ghi thông tin bằng một message:

~~~text
Provision failed for instance instance-7f3a on production because provider timed out
~~~

Con người có thể đọc được, nhưng hệ thống khó lọc chính xác nếu mỗi class viết message theo cách khác nhau. Tên field, thứ tự từ, cách viết ID và định dạng lỗi có thể thay đổi giữa các phiên bản.

Structured log biểu diễn cùng sự kiện bằng các field:

~~~json
{
  "timestamp": "2026-11-27T10:30:12.451Z",
  "level": "ERROR",
  "event.name": "osb.provision.provider_timeout",
  "platform.id": "cf-prod",
  "service.instance.id": "instance-7f3a",
  "service.id": "service-postgresql",
  "plan.id": "plan-standard",
  "operation.id": "op-92b1",
  "provider.name": "postgresql",
  "outcome": "RETRYABLE_FAILURE",
  "duration_ms": 30000
}
~~~

Các field có tên ổn định cho phép truy vấn như:

- Tìm tất cả lỗi provision của một platform.
- Theo dõi một service instance qua các lần update và deprovision.
- Tìm các binding liên quan đến một instance.
- Tập hợp các log của một operation bất đồng bộ.
- So sánh timeout theo provider hoặc operation type.
- Xác định request nào đã tạo provider call và kết quả cuối cùng.

Structured logging không yêu cầu mọi log phải có tất cả field. Mỗi event có một tập field chung và một tập field riêng theo loại sự kiện. Schema cần quy định field nào bắt buộc, field nào tùy chọn và giá trị nào được phép.

## 2. Phân biệt platform, tenant, instance, binding và operation

Broker cần giữ các định danh ở đúng cấp. Không dùng một ID chung để đại diện cho nhiều đối tượng.

| Field | Đại diện | Ví dụ |
|---|---|---|
| **platform.id** | Platform/foundation đã được xác thực hoặc chuẩn hóa | cf-prod |
| **platform.instance_id** | Một platform instance nếu integration hỗ trợ định danh này | foundation-prod-01 |
| **tenant.id** | Tenant nội bộ sở hữu tài nguyên | tenant-payments |
| **service.instance.id** | ID service instance do platform cung cấp | instance-7f3a |
| **service.id** | Offering trong catalog | service-postgresql |
| **plan.id** | Plan được chọn | plan-standard |
| **service.binding.id** | ID binding do platform cung cấp | binding-billing |
| **operation.id** | Token/ID của operation bất đồng bộ | op-92b1 |
| **request.id** | Định danh một HTTP request cụ thể | req-a81d |
| **trace_id** | Trace phân tán nối nhiều span | 4bf92f... |
| **provider.resource.id** | Resource thực tế tại provider | db-991 |

Các ID này có quan hệ nhưng không thay thế lẫn nhau. Một service instance có thể có nhiều binding và nhiều operation theo thời gian. Một operation có thể phát sinh nhiều provider request. Một HTTP request retry có thể được nối với operation cũ nếu idempotency xác định đó là cùng một ý định.

Trong môi trường nhiều foundation, service.instance.id có thể trùng giữa hai platform. Khi truy vấn log, cần kết hợp với platform.id hoặc platform namespace đã xác thực. Không giả định instance ID là duy nhất toàn hệ thống.

Không đưa toàn bộ object context vào một field JSON duy nhất rồi kỳ vọng truy vấn có thể hiểu được. Hãy chuẩn hóa các thuộc tính cần dùng thành field riêng, đồng thời chỉ giữ snapshot tối thiểu nếu có lý do audit.

## 3. Thiết kế schema chung cho mọi event

Một log event nên có phần chung giúp mọi service trong broker dùng cùng cách truy vấn.

| Nhóm | Field gợi ý | Ý nghĩa |
|---|---|---|
| Thời gian | @timestamp hoặc timestamp | Thời điểm event xảy ra theo UTC |
| Mức độ | level | DEBUG, INFO, WARN, ERROR |
| Nguồn phát | service.name, service.version, service.environment | Ứng dụng và phiên bản |
| Sự kiện | event.name, event.category, event.action | Loại sự kiện và hành động |
| Request | request.id, http.request.method, http.route, http.response.status_code | HTTP request |
| Trace | trace_id, span_id, trace_flags | Liên kết distributed tracing |
| Platform | platform.id, platform.instance_id | Nguồn platform |
| Ownership | tenant.id | Tenant đã resolve và được phép ghi log |
| OSB resource | service.instance.id, service.binding.id, service.id, plan.id | Resource lifecycle |
| Operation | operation.id, operation.type, operation.state | Xử lý bất đồng bộ |
| Provider | provider.name, provider.resource.id, provider.request.id | Tích hợp hạ tầng |
| Kết quả | outcome, duration_ms, retry_count | Kết quả và hiệu năng |
| Lỗi | error.type, error.code, error.message | Phân loại lỗi đã làm sạch |

Có thể dùng tên field theo OpenTelemetry semantic conventions hoặc một schema nội bộ tương thích. Quan trọng nhất là chọn một quy ước thống nhất và tài liệu hóa nó. Không để mỗi module tự đặt instanceId, instance_id, sid hoặc resource cho cùng một khái niệm.

### 3.1. Field bắt buộc và field tùy chọn

Một schema có thể quy định:

- Mọi event đều có timestamp, level, service name và event name.
- HTTP event có request ID, method, route và status code.
- Event lifecycle có platform ID và service instance ID.
- Event binding có binding ID.
- Event async có operation ID và operation type.
- Provider event có provider name; resource ID chỉ ghi nếu không nhạy cảm và cần thiết.
- Error event có error type và outcome.

Không điền chuỗi "null" hoặc "unknown" vào mọi field chỉ để JSON đồng nhất. Field không có giá trị nên được bỏ qua hoặc biểu diễn null theo quy ước schema. Nếu không xác định được platform, có thể ghi trạng thái resolution như platform.resolution="UNRESOLVED" thay vì gán một foundation mặc định.

## 4. Event name nên mô tả hành động ổn định

Tên event cần phản ánh hành động nghiệp vụ, không phụ thuộc tên class hoặc message tự do.

| Event name | Khi nào ghi |
|---|---|
| osb.request.received | Broker nhận request |
| osb.request.rejected | Request bị từ chối trước lifecycle side effect |
| osb.catalog.served | Trả catalog |
| osb.provision.accepted | Provision được chấp nhận |
| osb.provision.started | Worker bắt đầu provision |
| osb.provision.completed | Provision hoàn tất |
| osb.provision.failed | Provision thất bại |
| osb.instance.updated | Update instance hoàn tất |
| osb.binding.created | Binding được tạo |
| osb.binding.revoked | Binding đã thu hồi |
| osb.deprovision.completed | Deprovision hoàn tất |
| osb.operation.polled | Platform đọc trạng thái operation |
| provider.request.sent | Adapter gửi request provider |
| provider.request.completed | Provider trả kết quả |
| quota.reservation.created | Tạo reservation |
| quota.reservation.released | Giải phóng reservation |

Event name nên ổn định qua các phiên bản. Nếu đổi tên event, cần cân nhắc dashboard, alert, truy vấn và pipeline downstream đang sử dụng.

Không dùng event name làm nơi nhúng ID, tenant hoặc thông tin động. Ví dụ osb.provision.instance-7f3a.failed làm tăng số lượng event type và khó truy vấn. Hãy dùng event.name="osb.provision.failed" và field service.instance.id riêng.

## 5. Một vòng đời OSB cần nhiều event liên kết

Một request provision có thể tạo reservation, operation, outbox event, provider call và kết quả cuối. Không nên chỉ ghi một log sau khi hoàn thành vì khi lỗi giữa chừng sẽ không biết đã tới bước nào.

Ví dụ timeline:

~~~text
10:30:00.100  osb.request.received
10:30:00.115  osb.provision.accepted
10:30:00.130  operation.created
10:30:00.150  outbox.event.published
10:30:00.220  osb.provision.started
10:30:00.350  provider.request.sent
10:30:12.451  provider.request.completed
10:30:12.470  osb.provision.completed
~~~

Các event liên kết bằng request ID, trace ID, operation ID, platform ID và instance ID. Mỗi event có thể do process hoặc worker khác phát ra, nhưng vẫn truy vấn được cùng một lifecycle.

### 5.1. Request accepted khác operation completed

Với operation bất đồng bộ, HTTP 202 chỉ có nghĩa broker đã chấp nhận request để xử lý theo contract. Nó không có nghĩa provider đã tạo xong database.

Nên ghi các event riêng:

- osb.provision.accepted: broker đã ghi nhận operation.
- osb.provision.started: worker claim operation.
- provider.request.completed: provider call đã trả kết quả.
- osb.provision.completed: trạng thái instance được commit thành công.

Nếu provider trả timeout, log cần thể hiện timeout là kết quả của provider call; không ghi provision completed chỉ vì broker đã trả HTTP 202.

### 5.2. Retry phải có attempt metadata

Với provider call hoặc worker retry, có thể ghi retry_count, attempt, next_retry_at và error.type. Không ghi một event mới với operation ID khác mỗi lần retry nếu đó vẫn là cùng operation. Giữ operation identity ổn định và dùng attempt number để phân biệt lần thực thi.

## 6. Liên kết request, trace và operation

Ba loại định danh thường cần thiết:

- **request.id:** một lần HTTP request đến broker.
- **trace_id/span_id:** nối các bước phân tán trong cùng trace.
- **operation.id:** một lifecycle operation có thể tồn tại lâu hơn HTTP request.

Ví dụ platform gửi provision và nhận HTTP 202. HTTP request kết thúc, nhưng worker tiếp tục chạy trong vài phút. Worker không còn cùng thread hoặc process với request ban đầu. Vì vậy operation ID phải được lưu bền vững để nối log sau khi request kết thúc.

Một event request:

~~~json
{
  "timestamp": "2026-11-27T10:30:00.100Z",
  "level": "INFO",
  "event.name": "osb.provision.accepted",
  "request.id": "req-a81d",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "platform.id": "cf-prod",
  "tenant.id": "tenant-payments",
  "service.instance.id": "instance-7f3a",
  "operation.id": "op-92b1",
  "operation.type": "PROVISION",
  "outcome": "ACCEPTED"
}
~~~

Một event worker:

~~~json
{
  "timestamp": "2026-11-27T10:30:00.220Z",
  "level": "INFO",
  "event.name": "osb.provision.started",
  "request.id": "req-a81d",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "platform.id": "cf-prod",
  "tenant.id": "tenant-payments",
  "service.instance.id": "instance-7f3a",
  "operation.id": "op-92b1",
  "operation.type": "PROVISION",
  "attempt": 1,
  "outcome": "STARTED"
}
~~~

Trace ID có thể được truyền qua message headers nếu tracing instrumentation hỗ trợ. Operation ID vẫn cần tồn tại độc lập vì trace có thể kết thúc, bị sampling hoặc không còn được lưu sau thời gian retention. Log phải có operation ID để điều tra lifecycle lâu dài.

## 7. Correlation ID từ client và trust boundary

Platform hoặc gateway có thể gửi correlation header, ví dụ X-Correlation-ID. Header này hữu ích để nối log giữa nhiều thành phần, nhưng là dữ liệu đầu vào từ bên ngoài.

Broker cần:

- Giới hạn độ dài.
- Chỉ chấp nhận tập ký tự cho phép.
- Loại bỏ CR/LF và ký tự điều khiển để ngăn log injection.
- Không dùng correlation ID làm authentication hoặc authorization.
- Nếu header thiếu hoặc sai định dạng, tạo ID nội bộ.
- Ghi rõ nguồn correlation.source nếu cần phân biệt client-provided và generated.

Không phản chiếu một chuỗi tùy ý từ request vào log message. Nếu gateway có trách nhiệm ghi đè correlation ID, chỉ tin header từ gateway đã xác thực theo trust boundary.

Correlation ID và traceparent cũng không đồng nghĩa. Correlation ID là khóa truy vấn ứng dụng; traceparent tuân theo W3C Trace Context và được instrumentation sử dụng để tạo trace/span. Có thể lưu cả hai khi chúng phục vụ mục đích khác nhau.

## 8. Truyền MDC qua Spring request và worker

SLF4J MDC thường dùng ThreadLocal để gắn key/value vào log trong phạm vi thread. Với Spring MVC, có thể đặt request ID, platform ID, instance ID hoặc operation ID vào MDC trong filter/interceptor rồi xóa sau request.

Ví dụ filter minh họa:

~~~java
public class OsbLoggingFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestId = validatedOrGeneratedRequestId(request);
        MDC.put("request.id", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("request.id");
            MDC.remove("platform.id");
            MDC.remove("service.instance.id");
            MDC.remove("service.binding.id");
            MDC.remove("operation.id");
        }
    }
}
~~~

Đây là pseudocode: cần bổ sung các helper validate header, resolve platform scope sau authentication và xử lý exception theo cấu hình thực tế. Không lấy platform ID trực tiếp từ query string rồi ghi vào MDC trước khi xác thực principal.

MDC không tự động truyền an toàn qua mọi thread pool, @Async, scheduler hoặc message listener. Khi thread được tái sử dụng, MDC cũ còn sót lại có thể làm log của request mới bị gắn nhầm tenant hoặc instance.

### 8.1. TaskDecorator cho executor

Spring TaskDecorator có thể sao chép context đã được chuẩn hóa sang task async và khôi phục MDC trước đó sau khi task kết thúc.

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Chỉ copy field đã được allowlist và làm sạch. Không đưa raw authorization header, access token, originating identity payload hoặc toàn bộ request context vào MDC. Với queue worker chạy sau thời gian dài, tốt hơn nên lưu correlation/operation/platform/resource identifiers trong message metadata đã chuẩn hóa, sau đó tạo MDC mới trong consumer.

### 8.2. Reactor và reactive pipeline

MDC dựa trên ThreadLocal không tự nhiên đi theo Reactor Context khi execution đổi thread. Nếu broker dùng WebFlux/Reactor, hãy dùng cơ chế context propagation tương thích phiên bản Spring/Reactor và OpenTelemetry instrumentation. Không giả định MDC.put ở đầu pipeline sẽ có mặt ở mọi operator sau publishOn hoặc subscribeOn.

## 9. Truyền context qua message queue

Worker bất đồng bộ cần biết operation nào đang chạy và resource thuộc platform nào. Message nên chứa các identifier cần thiết, không chứa toàn bộ HTTP request.

Ví dụ message metadata:

~~~json
{
  "event_id": "evt-881a",
  "event_type": "osb.provision.requested",
  "platform_id": "cf-prod",
  "tenant_ref": "tenant-payments",
  "instance_id": "instance-7f3a",
  "operation_id": "op-92b1",
  "correlation_id": "corr-19f2",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "created_at": "2026-11-27T10:30:00.150Z"
}
~~~

Message metadata nên được validate lại ở consumer. Queue là một trust boundary khác; không giả định mọi message đều do producer đáng tin cậy tạo ra. Consumer nên kiểm tra event type, schema version, platform namespace và operation ownership trước khi thực hiện provider side effect.

Không serialize password, provider token hoặc binding credentials vào message để tiện log. Worker có thể lấy secret qua reference đã lưu trong secret manager sau khi xác thực quyền truy cập.

## 10. Log cho binding mà không làm lộ credentials

Binding response có thể chứa username, password, endpoint, certificate hoặc token. Các giá trị này tuyệt đối không được log nguyên văn.

Một event binding an toàn:

~~~json
{
  "timestamp": "2026-11-27T10:31:14.002Z",
  "level": "INFO",
  "event.name": "osb.binding.created",
  "platform.id": "cf-prod",
  "tenant.id": "tenant-payments",
  "service.instance.id": "instance-7f3a",
  "service.binding.id": "binding-billing",
  "credential.mode": "PER_BINDING",
  "permission.profile": "read_write",
  "secret.reference.id": "vault-ref-71a2",
  "outcome": "SUCCESS"
}
~~~

Có thể log secret reference ID nếu nó không tiết lộ đường dẫn hoặc quyền truy cập nhạy cảm. Không log secret value, credential JSON, Authorization header, private key hoặc connection string có password.

Không log toàn bộ request/response body của endpoint bind trong production. Nếu cần debug, hãy ghi các field allowlist như role, provider type và permission profile sau validation; bỏ các field có khả năng chứa secret.

## 11. Redaction và phân loại dữ liệu nhạy cảm

Trước khi ghi log, cần phân loại field:

| Nhóm dữ liệu | Ví dụ | Chính sách |
|---|---|---|
| Định danh kỹ thuật | instance ID, binding ID, operation ID | Có thể log theo access policy |
| Platform/tenant | foundation, tenant reference | Log đã chuẩn hóa, giới hạn quyền |
| Cấu hình không nhạy cảm | plan, role, storage tier | Allowlist theo schema |
| PII | email, username, user GUID | Hạn chế hoặc pseudonymize |
| Secret | password, token, private key, certificate private part | Không log |
| Network detail | host, internal IP, connection string | Chỉ log khi cần và đã đánh giá |
| Raw payload | request body, context đầy đủ | Không log mặc định |
| Provider response | raw body/headers | Parse thành error code an toàn |

Redaction nên diễn ra trước khi event tới appender hoặc collector, không dựa vào việc dashboard che giá trị sau khi dữ liệu đã được lưu. Nếu framework hỗ trợ structured arguments, hãy dùng field allowlist thay vì serialize toàn bộ object domain.

Không dựa vào regex chung để tìm mọi secret. Tốt nhất là không đưa secret vào logging call ngay từ đầu. Redaction là lớp phòng vệ bổ sung cho những trường hợp message hoặc exception vô tình chứa dữ liệu nhạy cảm.

## 12. Chống log injection và dữ liệu không đáng tin

Các field như correlation ID, context namespace, provider error message hoặc originating identity có thể chứa chuỗi do bên ngoài gửi. Nếu đưa trực tiếp vào log message, attacker có thể chèn newline hoặc ký tự điều khiển để tạo dòng giả hoặc phá cấu trúc JSON.

Biện pháp:

- Dùng JSON encoder có escaping đúng chuẩn.
- Validate độ dài và ký tự của identifier.
- Không nối chuỗi raw vào message.
- Loại bỏ CR, LF và control characters ở field text không cho phép chúng.
- Chuẩn hóa Unicode khi cần để tránh các dạng biểu diễn gây nhầm lẫn.
- Giới hạn kích thước exception/provider message.
- Không serialize raw HTTP headers.
- Giữ giá trị gốc chỉ khi có lý do điều tra và đã mã hóa/kiểm soát.

Không tự viết JSON bằng string concatenation. Dùng logging framework và encoder để xử lý escaping.

## 13. Logging trong Spring Boot

Spring Boot có thể cấu hình log level, pattern và appender. Để xuất JSON, có thể dùng encoder tương thích với Logback, chẳng hạn một thư viện JSON encoder được dự án lựa chọn. Phiên bản thư viện phải tương thích với Spring Boot/Logback hiện tại.

Ví dụ cấu hình Logback minh họa:

~~~xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <includeMdcKeyName>request.id</includeMdcKeyName>
            <includeMdcKeyName>platform.id</includeMdcKeyName>
            <includeMdcKeyName>tenant.id</includeMdcKeyName>
            <includeMdcKeyName>service.instance.id</includeMdcKeyName>
            <includeMdcKeyName>service.binding.id</includeMdcKeyName>
            <includeMdcKeyName>operation.id</includeMdcKeyName>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
~~~

Đây là ví dụ cấu hình phụ thuộc encoder. Kiểm tra cú pháp và các property hỗ trợ theo đúng phiên bản thư viện được chọn. Nếu dùng Spring Boot structured logging tích hợp ở phiên bản mới, có thể ưu tiên tính năng native thay vì thêm encoder khác. Tránh cấu hình hai encoder cùng serialize MDC khiến field bị lồng hoặc lặp.

### 13.1. Dùng parameterized logging

Nên dùng placeholder để tránh tạo chuỗi khi log level không bật:

~~~java
log.info(
    "OSB operation completed: type={}, state={}, durationMs={}",
    operationType,
    operationState,
    durationMs
);
~~~

Với structured arguments, ghi field riêng theo encoder đã chọn. Không nhúng mọi dữ liệu vào một message dài. Message nên giải thích event; field cung cấp dữ liệu có thể truy vấn.

### 13.2. Log exception có kiểm soát

Khi log exception, ghi error.type, mã lỗi nội bộ đã chuẩn hóa và stack trace trong log nội bộ có quyền truy cập phù hợp. Không trả stack trace cho platform trong error response.

Provider exception có thể chứa URL, request header hoặc body. Trước khi log exception message, cần kiểm tra thư viện/provider adapter có đưa credential vào message hay không. Có thể log exception class, provider status code và một error category an toàn thay cho raw message.

## 14. Phân biệt log, metric, trace và audit

Bốn loại telemetry phục vụ các mục tiêu khác nhau:

| Loại | Câu hỏi chính | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra ở một thời điểm? | Instance provision thất bại vì provider timeout |
| Metric | Sự kiện/giá trị thay đổi theo thời gian thế nào? | Tỷ lệ provision lỗi trong 5 phút |
| Trace | Một request đi qua những thành phần nào? | HTTP → service → DB → queue → worker → provider |
| Audit | Ai đã thực hiện hành động có ý nghĩa và kết quả là gì? | Actor A được phép deprovision instance B |

Không dùng log thay metric cho dashboard số lượng lớn. Cũng không coi log thông thường là audit trail có tính bất biến. Audit có thể cần storage riêng, quyền ghi append-only, retention và quy trình truy cập chặt hơn.

Trace giúp phân tích latency giữa service, nhưng không thay operation ID. Một operation có thể kéo dài qua nhiều trace hoặc nhiều lần retry. Operation ID cần được giữ trong database và log để nối lifecycle qua thời gian.

## 15. Log level và mức độ chi tiết

Một policy log level giúp kiểm soát dung lượng và tín hiệu:

| Level | Khi sử dụng | Ví dụ |
|---|---|---|
| ERROR | Operation thất bại và cần hành động | Provider không thể tạo resource sau retry policy |
| WARN | Điều kiện bất thường nhưng hệ thống vẫn phục hồi | Retry provider lần thứ hai, reconciliation phát hiện drift |
| INFO | Sự kiện lifecycle quan trọng | Provision accepted/completed, binding revoked |
| DEBUG | Chi tiết kỹ thuật khi điều tra | Query timing, policy decision details đã làm sạch |
| TRACE | Dữ liệu cực chi tiết, chỉ bật ngắn hạn | Protocol diagnostics có kiểm soát |

Không ghi cùng một lỗi ở ERROR tại mọi layer. Nếu provider adapter đã log ERROR và application service lại log cùng exception ở ERROR, một sự cố có thể tạo nhiều bản ghi giống nhau. Hãy xác định layer sở hữu log cuối cùng, còn layer khác có thể bổ sung context ở DEBUG hoặc rethrow typed exception.

Không để DEBUG/TRACE bật lâu trong production nếu có thể làm lộ payload hoặc tạo dung lượng lớn. Dynamic log level cần có authorization, audit và thời hạn tự động khôi phục.

## 16. Truy vấn log theo lifecycle

Khi schema ổn định, operator có thể lần theo một sự cố theo nhiều hướng.

### 16.1. Theo platform và instance

Tìm tất cả event của một instance trong một foundation:

~~~text
platform.id = "cf-prod"
AND service.instance.id = "instance-7f3a"
~~~

Nếu cùng instance ID xuất hiện trên nhiều foundation, điều kiện platform là bắt buộc để tránh gộp nhầm.

### 16.2. Theo binding

~~~text
platform.id = "cf-prod"
AND service.instance.id = "instance-7f3a"
AND service.binding.id = "binding-billing"
~~~

Có thể thấy create binding, credential reference, retrieve và revoke mà không cần xem secret value.

### 16.3. Theo operation

~~~text
operation.id = "op-92b1"
~~~

Truy vấn này có thể nối request ban đầu, worker attempt, provider call và terminal state. Nếu operation được retry, lọc thêm attempt hoặc event name để phân biệt từng lần.

### 16.4. Theo provider error

~~~text
provider.name = "postgresql"
AND error.type = "ProviderTimeoutException"
AND outcome = "RETRYABLE_FAILURE"
~~~

Dùng field chuẩn hóa thay vì parse message tự do. Điều này giúp phát hiện provider outage và so sánh giữa các version adapter.

## 17. Cardinality và chi phí lưu trữ

Log có thể chứa nhiều ID duy nhất. Đây là điều bình thường với log index, nhưng cần cẩn thận khi đưa ID vào metric labels hoặc dashboard dimensions.

| Field | Log field | Metric label |
|---|---|---|
| platform.id | Có | Thường phù hợp nếu số platform hữu hạn |
| service.id | Có | Phù hợp nếu catalog nhỏ |
| plan.id | Có | Phù hợp nếu plan hữu hạn |
| service.instance.id | Có khi cần | Tránh label cardinality cao |
| service.binding.id | Có khi cần | Tránh |
| operation.id | Có | Tránh |
| request.id | Có | Tránh |
| tenant.id | Có theo policy | Thường tránh hoặc dùng nhóm tenant |
| provider.name | Có | Phù hợp nếu provider hữu hạn |

Log volume tăng theo request rate, event count và payload size. Cần:

- Tránh ghi cùng một event ở mọi layer.
- Giới hạn stack trace cho lỗi lặp có tần suất cao.
- Dùng sampling cho diagnostic events không thiết yếu.
- Không sample audit event bắt buộc.
- Thiết lập retention theo loại log.
- Nén và partition theo thời gian.
- Theo dõi dropped logs, queue backlog và ingestion delay.
- Tách security/audit log khỏi application debug log nếu policy yêu cầu.

Không bỏ log lifecycle quan trọng chỉ để giảm chi phí. Hãy giảm field thừa, payload raw và duplicate events trước.

## 18. Correlation trong môi trường nhiều replica và nhiều nền tảng

Broker có thể chạy nhiều replica trên Kubernetes. Một request có thể vào pod A, tạo operation, rồi worker ở pod B xử lý. Vì vậy MDC chỉ là context tạm thời trong process; định danh cần truy vết phải được lưu trong database hoặc message.

Các nguyên tắc:

- Request ID được tạo ở API boundary.
- Trace context được truyền qua HTTP và messaging instrumentation.
- Operation ID được lưu bền vững.
- Platform ID và tenant scope được chuẩn hóa sau authentication.
- Instance/binding ID được lấy từ route và xác minh ownership.
- Worker dựng lại logging context từ operation record.
- Provider request ID được lưu khi provider trả về.
- Mọi replica dùng cùng schema field và timezone UTC.

Không dựa vào pod name hoặc thread name làm khóa chính để tìm lifecycle. Chúng có thể hữu ích như service.instance hoặc process.thread.name trong chẩn đoán, nhưng không thay thế OSB identifiers.

## 19. Kiểm thử structured logging

Logging schema cũng cần test. Một số lỗi chỉ xuất hiện khi field bị thiếu, encoder không serialize MDC hoặc async context bị rò sang task khác.

| Nhóm test | Điều cần xác minh |
|---|---|
| Schema | Event có timestamp, level, event name và field bắt buộc |
| Platform scope | Log có platform ID đã xác thực |
| Resource scope | Instance/binding ID khớp request |
| Async propagation | Worker log giữ operation ID và trace context phù hợp |
| MDC cleanup | Request sau không nhận MDC của request trước |
| Secret redaction | Password/token/private key không xuất hiện |
| Error safety | Provider exception không lộ raw secret |
| Injection | CR/LF trong correlation/context không tạo log giả |
| JSON encoding | Mọi event là JSON hợp lệ và field type ổn định |
| Cardinality | ID động không bị đưa vào metric label |
| Retry | Attempt number tăng nhưng operation ID không đổi |
| Multi-platform | Cùng instance ID ở hai platform được phân biệt |

Một test hữu ích là gửi hai request đồng thời cho hai platform khác nhau, dùng cùng instance ID nhưng khác platform ID. Sau khi xử lý, đọc log output và xác minh mỗi event được gắn đúng namespace. Test tiếp theo chạy hai task trên cùng executor để xác nhận MDC đã được xóa hoặc khôi phục sau khi task trước hoàn tất.

Không chỉ kiểm tra rằng logger được gọi. Hãy kiểm tra JSON output cuối cùng sau encoder vì field naming, escaping và MDC serialization có thể khác với dữ liệu truyền vào logging API.

## 20. Checklist triển khai

Trước khi phát hành structured logging, hãy xác nhận:

- [ ] Có schema chung và event naming convention được tài liệu hóa.
- [ ] Platform, tenant, instance, binding và operation là các field riêng.
- [ ] Request ID, trace ID và operation ID không bị dùng thay thế nhau.
- [ ] Platform ID được ghi sau khi xác thực và chuẩn hóa.
- [ ] Instance/binding ID được scope theo platform khi cần.
- [ ] Event accepted, started, provider result và completed được phân biệt.
- [ ] Async worker nhận operation/correlation context từ message hoặc store.
- [ ] MDC được làm sạch sau request/task và truyền qua executor có kiểm soát.
- [ ] Reactive context dùng cơ chế tương thích thay vì giả định ThreadLocal.
- [ ] Không log Authorization header, credentials, private key hoặc raw binding body.
- [ ] Correlation/context field được validate và chống log injection.
- [ ] Provider error được chuẩn hóa trước khi ghi.
- [ ] Log, metric, trace và audit có mục đích và retention riêng.
- [ ] ID cardinality cao không được đưa vào metric labels.
- [ ] Có kiểm thử JSON schema, async propagation, redaction và multi-platform isolation.
- [ ] Có giới hạn volume, retention, access control và alert cho dropped logs.

Log có cấu trúc giúp theo dõi một lifecycle OSB từ platform request đến database, worker và provider. Khi mỗi event mang platform, instance, binding và operation identifiers đã được xác minh, người vận hành có thể truy vấn sự cố xuyên nhiều replica mà không phụ thuộc vào message tự do. Kết hợp schema ổn định, trace/correlation, MDC được quản lý đúng vòng đời và redaction trước khi ghi, Spring Cloud Service Broker có thể cung cấp khả năng quan sát sâu mà vẫn bảo vệ credentials và dữ liệu tenant.
