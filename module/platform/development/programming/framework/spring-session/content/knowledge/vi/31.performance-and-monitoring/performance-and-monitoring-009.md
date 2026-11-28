# Metric, trace và ghi log tương quan mà không công bố định danh thô

Spring Session lưu trạng thái phiên ở một kho dùng chung như Redis hoặc JDBC để nhiều instance có thể phục vụ cùng một người dùng. Khi sự cố xảy ra, nhóm vận hành cần biết request nào đã đọc hoặc ghi session, repository nào chậm, lỗi phát sinh ở node nào và phiên đã hết hạn hay bị thu hồi. Việc quan sát này phải được thực hiện mà không đưa session ID, cookie, token, user ID hoặc dữ liệu nhận dạng thô vào metric, trace hay log.

Session ID là bearer credential: người có ID còn hiệu lực có thể thử tiếp tục phiên. Vì vậy, log nguyên ID để tìm kiếm nhanh tạo ra rủi ro chiếm quyền phiên. Đưa ID vào metric tag còn làm tăng cardinality, khiến hệ thống metrics tốn bộ nhớ và khó tổng hợp. Trace attribute và baggage cũng có thể được sao chép qua nhiều dịch vụ, exporter và hệ thống lưu trữ.

Bài này xây dựng cách quan sát Spring Session bằng ba tín hiệu bổ trợ: metric đo xu hướng và độ trễ, trace theo dõi đường đi của một request, log có cấu trúc ghi ngữ cảnh cần thiết. Trọng tâm là dùng nhãn có cardinality thấp, trace ID/request ID để tương quan, che dữ liệu nhạy cảm, và chỉ dùng định danh giả danh có kiểm soát khi thực sự cần điều tra.

## 1. Ba tín hiệu quan sát có vai trò khác nhau

Metrics, traces và logs trả lời những câu hỏi khác nhau:

| Tín hiệu | Câu hỏi chính | Ví dụ trong Spring Session |
|---|---|---|
| Metric | Điều gì đang tăng, giảm hoặc vượt ngưỡng? | Tỷ lệ repository timeout, độ trễ save, số lỗi serialization |
| Trace | Một request đã đi qua những thành phần nào và chậm ở đâu? | HTTP request → WebSession → Redis GET → handler → Redis write |
| Log | Điều gì đã xảy ra trong một trường hợp cụ thể? | Repository save thất bại vì timeout ở node phiên bản V2 |
| Event | Có thay đổi vòng đời nào cần phản ứng? | Session expired, deleted hoặc created |

Không dùng log để thay metric cho một xu hướng dài hạn. Không dùng metric để lưu từng session ID. Không tạo trace span cho mọi thao tác nhỏ nếu chi phí vượt giá trị chẩn đoán.

Một thiết kế tốt dùng metric để phát hiện vấn đề, trace để định vị đoạn chậm, log để giải thích sự kiện đã xảy ra. Cả ba dùng chung trace ID hoặc request ID khi có thể, nhưng không cần chia sẻ session ID.

## 2. Những định danh không được ghi thô

Các trường sau cần được coi là nhạy cảm trong telemetry:

- Session ID, cookie value và header mang session ID.
- Authorization header, access token, refresh token và CSRF token.
- User ID, email, số điện thoại hoặc username nếu không cần thiết.
- Principal, SecurityContext và authorities đầy đủ.
- Nội dung session attributes như cart, hồ sơ, lựa chọn hoặc trạng thái nghiệp vụ.
- Query string có thể chứa token, mã xác thực hoặc thông tin cá nhân.
- Payload request/response có dữ liệu đăng nhập hoặc dữ liệu người dùng.

Đặc biệt, không log nguyên request/response headers khi có Cookie hoặc Authorization. Không ghi nguyên đối tượng HttpServletRequest, ServerWebExchange, WebSession hoặc SecurityContext bằng cách gọi toString() không kiểm soát.

Ví dụ log nguy hiểm:

~~~java
log.debug("Session loaded: {}", session);
log.info("Incoming Cookie header: {}", request.getHeader("Cookie"));
log.info("Authenticated principal: {}", authentication);
~~~

Các dòng trên có thể đưa session ID, thuộc tính, principal hoặc dữ liệu xác thực vào log tùy implementation. Thay vào đó, ghi operation, repository, outcome, duration, application version và request correlation ID.

## 3. Dùng nhãn metric có cardinality thấp

Metric backend như Prometheus tạo một time series cho mỗi tổ hợp metric name và label values. Nếu thêm session ID, user ID hoặc request ID làm label, mỗi phiên/request có thể tạo một series mới. Số series tăng nhanh và gây áp lực lên memory, CPU, storage và query.

Nhãn phù hợp thường là các tập giá trị nhỏ, ổn định:

| Nhãn | Ví dụ giá trị phù hợp |
|---|---|
| repository | redis, jdbc |
| operation | create, find, save, delete |
| outcome | success, not_found, timeout, unavailable, error, cancelled |
| application_version | v1, v2 hoặc release cố định |
| region | ap-southeast-1, eu-west-1 |
| node_pool | web-a, web-b |
| error_category | timeout, connection, serialization, unknown |

Không dùng làm label:

- sessionId
- userId
- email
- username
- requestId
- traceId
- raw URL hoặc query string
- exception message
- giá trị attribute
- IP đầy đủ nếu không có lý do vận hành và chính sách riêng

Tên exception class cũng có thể có cardinality cao nếu ứng dụng có exception động hoặc proxy-generated class. Ưu tiên map về một tập error_category cố định.

Ví dụ metric hợp lý:

~~~text
spring_session_repository_operations_total{
  repository="redis",
  operation="find",
  outcome="success"
}

spring_session_repository_operation_seconds_bucket{
  repository="redis",
  operation="save",
  outcome="success",
  le="0.1"
}
~~~

Ví dụ không an toàn và không mở rộng được:

~~~text
spring_session_save_total{session_id="a7f..."}
http_requests_total{user_id="user-93821"}
~~~

Một quy tắc thực tế: nếu label có thể nhận một giá trị mới cho mỗi người dùng hoặc mỗi request, nó không phù hợp với metric dimension.

## 4. Chọn metric quan trọng cho Spring Session

Không cần tạo hàng trăm metric. Hãy bắt đầu từ các thao tác ảnh hưởng trực tiếp tới độ tin cậy và độ trễ:

| Metric | Loại | Mục đích |
|---|---|---|
| repository operations | Counter hoặc Timer count | Đếm create/find/save/delete |
| repository operation duration | Timer/Histogram | Theo dõi p50, p95, p99 |
| repository errors | Counter | Đếm timeout, unavailable, serialization |
| session expired/deleted | Counter | Quan sát vòng đời và cleanup |
| session created | Counter | Theo dõi tốc độ tạo phiên |
| active session estimate | Gauge | Theo dõi quy mô tổng thể nếu có nguồn số liệu hiệu quả |
| storage connection pool | Gauge | Theo dõi pool cạn hoặc connection chờ |
| Redis command latency | Timer | Phân biệt chậm ở repository và Redis |
| JDBC query latency | Timer | Phân biệt chậm ở repository và database |
| session serialization size | Distribution summary | Phát hiện payload lớn, nếu đo không chứa dữ liệu |

Timer thường đã cung cấp count và total time; không cần tạo counter riêng cho cùng một operation trừ khi có mục đích rõ ràng. Histogram bucket và percentile nên được cấu hình theo SLA, không bật mọi bucket cho mọi metric.

### Các phép đo nên tách riêng

- find hit và find miss: miss là kết quả nghiệp vụ bình thường, không nhất thiết là error.
- save success, save failure và save timeout.
- delete success và delete not found nếu cần.
- serialization failure và storage connection failure.
- session expired event và session deleted event.
- thời gian chờ connection pool và thời gian thực thi lệnh.

Không coi not_found là lỗi hệ thống. Tỷ lệ miss tăng bất thường có thể báo hiệu cookie không được gửi, session bị xóa, namespace lệch hoặc TTL quá ngắn, nhưng cần đối chiếu trace và log.

## 5. Cấu hình Actuator và Micrometer

Spring Boot Actuator tích hợp Micrometer để công bố metrics cho hệ thống quan sát. Dependency và endpoint cụ thể tùy stack; ví dụ cấu hình Prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: spring-session-service
~~~

Nếu dùng Prometheus registry, thêm dependency registry phù hợp với Spring Boot version của dự án. Không expose endpoint metrics công khai nếu chưa có kiểm soát mạng/xác thực. Endpoint có thể tiết lộ cấu trúc hệ thống, tên pool, phiên bản và trạng thái vận hành.

Micrometer cung cấp MeterRegistry để tạo Counter, Timer, Gauge và DistributionSummary. Đặt tên metric theo convention nhất quán và dùng đơn vị thời gian chuẩn do Micrometer hỗ trợ.

Không thêm tag động từ request vào management.metrics.tags. Global tags nên là application, environment hoặc region có số giá trị hữu hạn.

## 6. Đo thời gian thao tác repository đồng bộ

Với Servlet SessionRepository đồng bộ, có thể bọc repository bằng decorator để đo operation. Ví dụ dưới đây minh họa cách đo thời gian và phân loại outcome; cần điều chỉnh generic type/import theo phiên bản Spring Session.

~~~java
final class TimedSessionRepository<S extends Session>
        implements SessionRepository<S> {

    private final SessionRepository<S> delegate;
    private final MeterRegistry registry;
    private final String repositoryName;
    private final Function<RuntimeException, String> classifier;

    TimedSessionRepository(
            SessionRepository<S> delegate,
            MeterRegistry registry,
            String repositoryName,
            Function<RuntimeException, String> classifier) {
        this.delegate = delegate;
        this.registry = registry;
        this.repositoryName = repositoryName;
        this.classifier = classifier;
    }

    private <T> T record(
            String operation,
            Supplier<T> action) {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            T result = action.get();
            if ("find".equals(operation) && result == null) {
                outcome = "not_found";
            }
            return result;
        } catch (RuntimeException error) {
            outcome = classifier.apply(error);
            throw error;
        } finally {
            sample.stop(Timer.builder(
                    "spring.session.repository.operation")
                .tag("repository", repositoryName)
                .tag("operation", operation)
                .tag("outcome", outcome)
                .register(registry));
        }
    }

    private void recordVoid(String operation, Runnable action) {
        record(operation, () -> {
            action.run();
            return Boolean.TRUE;
        });
    }

    @Override
    public S createSession() {
        return record("create", delegate::createSession);
    }

    @Override
    public void save(S session) {
        recordVoid("save", () -> delegate.save(session));
    }

    @Override
    public S findById(String id) {
        return record("find", () -> delegate.findById(id));
    }

    @Override
    public void deleteById(String id) {
        recordVoid("delete", () -> delegate.deleteById(id));
    }
}
~~~

Đoạn code minh họa cần các import tương ứng như Session, SessionRepository, MeterRegistry, Timer, Supplier và Function. Hàm classifier phải ánh xạ exception của Redis/JDBC về một tập outcome nhỏ, cố định, ví dụ timeout, unavailable, serialization hoặc error. Không dùng exception message hoặc class name động làm tag.

Lưu ý:

- Không đưa id vào record(), tag hoặc log.
- Không bắt exception rồi trả kết quả giả; decorator phải ném lại lỗi.
- Không tạo một Timer riêng cho từng session.
- Đăng ký decorator đúng cách để không tạo vòng lặp delegate trỏ lại chính decorator.
- Tránh instrument trùng nếu driver hoặc framework đã tự công bố cùng một phép đo.
- Nếu save được gọi rất thường xuyên, đo cả overhead của instrumentation.

Với implementation có exception checked, cần điều chỉnh functional interface để giữ đúng chữ ký và không làm mất nguyên nhân.

## 7. Đo publisher reactive mà không làm mất cancellation

Với ReactiveSessionRepository, không đo thời gian bằng cách bắt đầu Timer khi tạo Mono rồi dừng ngay lập tức. I/O chỉ chạy khi publisher được subscribe. Có thể đặt instrumentation trong Mono.defer và kết thúc khi publisher phát complete, error hoặc cancel.

Ví dụ cho thao tác find:

~~~java
Mono<Session> findTimed(String id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        AtomicReference<String> outcome =
                new AtomicReference<>("success");

        return delegate.findById(id)
            .doOnSuccess(session -> {
                if (session == null) {
                    outcome.set("not_found");
                }
            })
            .doOnError(error ->
                outcome.set(classify(error)))
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    outcome.set("cancelled");
                }

                sample.stop(Timer.builder(
                        "spring.session.repository.operation")
                    .tag("repository", "redis")
                    .tag("operation", "find")
                    .tag("outcome", outcome.get())
                    .register(registry));
            });
    });
}
~~~

Ví dụ này giả định các field registry và delegate đã được khai báo. Với Mono<S>, doOnSuccess nhận null khi publisher hoàn tất rỗng; đó là lý do có thể phân loại not_found. Với Mono<Void> của save, giá trị null là kết quả hoàn tất bình thường, không được phân loại thành miss.

Cancellation chỉ cho biết subscriber đã hủy publisher. Nó không chứng minh Redis/database chưa ghi. Outcome cancelled là một tín hiệu telemetry, không phải kết luận về trạng thái bền vững.

## 8. Phân biệt miss, expired và lỗi

Từ góc độ quan sát, ba trường hợp này nên được phân loại khác nhau:

| Outcome | Ý nghĩa | Metric/error policy |
|---|---|---|
| success | Repository trả session | Thành công |
| not_found | ID không có hoặc đã hết hạn | Miss bình thường |
| expired | Repository xác định session hết hạn | Event/counter riêng nếu có thể phân biệt |
| timeout | Không nhận kết quả đúng hạn | Lỗi hạ tầng |
| unavailable | Redis/JDBC không truy cập được | Lỗi hạ tầng |
| serialization | Không đọc/ghi được payload | Lỗi dữ liệu hoặc tương thích |
| cancelled | Publisher bị hủy | Ghi nhận cancellation, không kết luận rollback |
| error | Lỗi khác | Phân tích theo exception category |

Một repository đơn giản có thể chỉ trả null/empty cho cả session không tồn tại và đã hết hạn. Nếu implementation không cung cấp lý do riêng, đừng suy diễn rằng có thể đo expired chính xác. Có thể dùng event expiration từ backend hoặc metric cleanup, nhưng cần ghi rõ nguồn và giới hạn của số liệu.

## 9. Theo dõi session lifecycle event

Spring Session có các event như session created, deleted và expired tùy repository và cơ chế phát event. Listener có thể tăng counter hoặc phát log cấu trúc.

Ví dụ:

~~~java
@Component
class SessionLifecycleMetrics {

    private final Counter created;
    private final Counter deleted;
    private final Counter expired;

    SessionLifecycleMetrics(MeterRegistry registry) {
        this.created = registry.counter("spring.session.lifecycle",
                "event", "created");
        this.deleted = registry.counter("spring.session.lifecycle",
                "event", "deleted");
        this.expired = registry.counter("spring.session.lifecycle",
                "event", "expired");
    }

    @EventListener
    void onCreated(SessionCreatedEvent event) {
        created.increment();
    }

    @EventListener
    void onDeleted(SessionDeletedEvent event) {
        deleted.increment();
    }

    @EventListener
    void onExpired(SessionExpiredEvent event) {
        expired.increment();
    }
}
~~~

Tên event/package và khả năng phát event phụ thuộc Spring Session module/version. Cần kiểm tra event classes thực tế trong dependency. Một số repository cần keyspace notifications, listener container hoặc cấu hình bổ sung để nhận expiration event. JDBC cleanup không nhất thiết phát event giống Redis expiration.

Event có thể bị phát lặp hoặc mất trong một số tình huống phân tán. Không dùng event stream làm nguồn sự thật duy nhất về session còn tồn tại. Repository lookup và trạng thái lưu trữ mới là cơ sở xác định session hợp lệ.

Không ghi event object nguyên vẹn nếu nó chứa session ID hoặc dữ liệu attributes. Listener nên chỉ tăng counter theo loại event, repository và node pool.

## 10. Tạo trace cho request và repository operation

Trace theo dõi một request xuyên qua các thành phần. Một trace có thể gồm:

~~~mermaid
flowchart TD
    A[HTTP server span] --> B[WebSession lookup span]
    B --> C[Redis GET / JDBC SELECT span]
    A --> D[Application handler span]
    D --> E[Session save span]
    E --> F[Redis write / JDBC UPDATE span]
~~~

Trace nên giúp trả lời:

- Request bắt đầu ở node/version nào?
- Thời gian nằm ở handler, repository hay storage driver?
- Có retry hoặc timeout không?
- Save có hoàn tất trước response commit không?
- Lỗi xảy ra ở thao tác find, serialize, save hay delete?
- Trace có đi qua gateway hoặc service khác không?

Dùng Micrometer Observation/Micrometer Tracing hoặc OpenTelemetry instrumentation tương thích với Spring Boot. Khi đã có auto-instrumentation cho HTTP, Redis hoặc JDBC, hãy kiểm tra trace hiện tại trước khi thêm span thủ công. Span trùng nhau gây nhiễu và tăng chi phí.

Span nên mô tả operation và repository type, ví dụ spring.session.find hoặc spring.session.save. Không đặt session ID, user ID, cookie hoặc raw URL làm span attribute.

## 11. Trace ID và span ID dùng để tương quan

Trace ID nhận diện một trace; span ID nhận diện một đoạn công việc trong trace. Các giá trị này được tạo cho telemetry và không phải session credential. Chúng có thể xuất hiện trong log để liên kết log với trace backend.

Khi request đi qua các service, trace context thường được truyền bằng W3C Trace Context headers như traceparent. Hãy để tracing library quản lý propagation và validate header theo chuẩn.

Không nhầm:

- traceId: định danh một trace quan sát.
- spanId: định danh một span trong trace.
- requestId: định danh request trong phạm vi hệ thống hoặc gateway.
- sessionId: định danh phiên, là credential nhạy cảm.

Trace ID có thể có phạm vi rộng và được lưu trong nhiều hệ thống. Dù không phải credential, vẫn cần hạn chế thông tin nhạy cảm trong trace attributes và baggage. Không đưa session ID vào baggage để dễ tìm trace.

## 12. Dùng Observation cho thao tác session tùy chỉnh

Nếu cần tạo span/observation cho custom repository, có thể dùng Micrometer Observation. Ví dụ cho một thao tác đồng bộ:

~~~java
Observation observation = Observation
    .createNotStarted("spring.session.repository.find", observationRegistry)
    .lowCardinalityKeyValue("repository", "redis")
    .lowCardinalityKeyValue("operation", "find");

return observation.observe(() -> delegate.findById(id));
~~~

Ví dụ không thêm ID vào observation. Các low-cardinality key cần là giá trị hữu hạn. Nếu cần thêm exception category, dùng một tập giá trị đã chuẩn hóa và tránh exception message.

Observation có thể được xuất thành metric và trace tùy handler được cấu hình. Vì vậy, tag đưa vào observation cần tuân thủ cùng quy tắc cardinality và privacy như metric/span.

Với reactive publisher, không tạo observation rồi kết thúc ngay trước khi publisher thực thi. Hãy dùng reactive observation operator hoặc đặt observation trong Mono.defer và kết thúc nó khi publisher kết thúc. Đảm bảo cancellation cũng được ghi nhận. Không giữ một Observation mở sau khi request đã kết thúc.

## 13. Log có cấu trúc và trường tương quan

Log có cấu trúc giúp truy vấn theo field thay vì phân tích chuỗi tự do. Các field hữu ích:

- timestamp
- level
- service
- environment
- applicationVersion
- instance hoặc nodePool
- operation
- repository
- outcome
- durationMs
- traceId
- spanId
- requestId
- errorCategory

Không ghi session ID, cookie, token, principal hoặc attributes. Không log raw URL có query string chưa được làm sạch.

Ví dụ JSON log an toàn:

~~~json
{
  "timestamp": "2026-11-26T09:15:30Z",
  "level": "WARN",
  "service": "spring-session-service",
  "applicationVersion": "v2",
  "nodePool": "web-a",
  "operation": "session.save",
  "repository": "redis",
  "outcome": "timeout",
  "durationMs": 2000,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "req-7a12",
  "errorCategory": "timeout"
}
~~~

Các giá trị trong ví dụ là giả lập. Không thêm trường sessionId hoặc cookie vào JSON. Nếu requestId do client gửi, validate độ dài/ký tự và không dùng nó để xác thực hoặc phân quyền. Có thể tạo request ID nội bộ mới ở gateway để tránh log injection.

## 14. MDC trong Servlet và Reactor Context trong WebFlux

Trong Servlet MVC, request thường chạy trên một thread trong thời gian xử lý. MDC (Mapped Diagnostic Context) có thể giữ traceId/spanId/requestId để logger tự thêm vào mỗi dòng log. Cần xóa MDC sau request để tránh rò rỉ context khi thread được tái sử dụng.

Trong WebFlux, execution có thể chuyển thread giữa các operator. ThreadLocal/MDC không tự động đi theo reactive chain. Không tự set MDC ở một operator rồi giả định các operator sau luôn thấy giá trị đó.

Cách an toàn:

- Dùng Micrometer Tracing/Observation tích hợp context propagation.
- Dùng Reactor Context cho dữ liệu tương quan trong reactive pipeline.
- Bật context propagation theo hướng dẫn của Spring Boot/Reactor version đang dùng.
- Không truyền session ID trong Reactor Context.
- Kiểm tra log ở cả thread switch, retry và async callback.
- Tránh tự viết ThreadLocal bridge nếu không hiểu lifecycle cleanup.

Một ví dụ đọc trace context từ Reactor Context cần phụ thuộc API tracing cụ thể; ưu tiên để logging/tracing integration tự bổ sung traceId/spanId. Nếu cần requestId tùy chỉnh, đặt nó trong Reactor Context và dùng cơ chế context propagation tương thích, không dùng static mutable field.

## 15. Tương quan request mà không dùng session ID

Có thể dùng request ID hoặc trace ID để nối log, trace và metric event:

1. Gateway tạo hoặc xác nhận request ID.
2. Tracing library tạo trace/span context.
3. Application log ghi requestId, traceId và spanId.
4. Repository span là child của request span.
5. Metric tổng hợp theo operation/outcome, không theo request ID.
6. Khi điều tra, tìm traceId trong trace backend rồi mở log cùng traceId.

Một request có thể truy cập nhiều session trong các tình huống quản trị hoặc batch; session ID không phải khóa tương quan phù hợp cho mọi log. Request ID mô tả một lần xử lý, còn trace ID mô tả đường đi quan sát.

Nếu cần nối nhiều request thuộc cùng một phiên trong điều tra, không đưa raw session ID vào log. Hãy xem xét fingerprint giả danh có HMAC và thời gian lưu giới hạn, theo phần tiếp theo.

## 16. Pseudonymization bằng HMAC khi thực sự cần

Trong một số sự cố, nhóm vận hành cần nhận biết nhiều sự kiện có liên quan tới cùng một session mà không ghi ID gốc. Có thể tạo fingerprint bằng HMAC-SHA-256 với secret key được quản lý riêng:

~~~java
byte[] mac(byte[] key, byte[] sessionIdBytes) {
    Mac hmac = Mac.getInstance("HmacSHA256");
    hmac.init(new SecretKeySpec(key, "HmacSHA256"));
    return hmac.doFinal(sessionIdBytes);
}
~~~

Kết quả có thể được rút gọn để hiển thị trong log, nhưng phải cân nhắc:

- Dùng HMAC có khóa bí mật, không dùng SHA-256(sessionId) đơn thuần.
- Không lưu hoặc log khóa HMAC.
- Quản lý rotation key và key version.
- Giới hạn thời gian lưu fingerprint.
- Không dùng fingerprint làm metric label.
- Hạn chế quyền truy cập log có fingerprint.
- Không ghi fingerprint vào trace baggage.
- Không xem fingerprint là dữ liệu vô danh; nó vẫn cho phép liên kết sự kiện.

Nếu mục tiêu chỉ là debug một request, traceId/requestId thường đủ. Chỉ tạo session fingerprint khi có use case điều tra được phê duyệt và có chính sách retention/access rõ ràng.

## 17. Redaction phải diễn ra ở mọi lớp

Chỉ che log trong application logger là chưa đủ. Session ID có thể bị ghi ở:

- Reverse proxy access log.
- API gateway và WAF.
- Servlet container access log.
- Application logger.
- HTTP client/server wire log.
- Redis command tracing.
- JDBC bind parameter logging.
- APM agent.
- OpenTelemetry collector/exporter.
- Error reporting và crash dump.
- CI test report hoặc screenshot.

Thiết kế redaction theo allowlist: chỉ xuất những field đã được phê duyệt. Denylist đơn thuần dễ bỏ sót header hoặc field mới.

Các trường cần che hoặc loại bỏ:
- Cookie và Set-Cookie.
- Authorization.
- X-Session-Id hoặc header session tùy chỉnh.
- Query parameter chứa token/credential.
- Request/response body đăng nhập.
- Session attributes.
- Principal và SecurityContext.
- Redis key nếu key có chứa session ID.

Đặc biệt, một số Redis repository dùng session ID trong key name. Không bật command logging/trace capture ở mức ghi nguyên key nếu exporter sẽ lưu key vào backend quan sát.

## 18. Log lỗi mà không làm lộ dữ liệu

Khi serialization hoặc repository lỗi, log nên ghi error category và operation:

~~~java
log.warn(
    "Session repository operation failed: repository={}, operation={}, "
        + "outcome={}, traceId={}",
    "redis",
    "save",
    "timeout",
    traceId
);
~~~

Không log:
- Exception message nếu message có thể chứa key/session ID.
- Toàn bộ exception object ở mức không kiểm soát nếu stack/driver message chứa query hoặc key nhạy cảm.
- Session object hoặc attributes.
- Cookie header.
- Raw request URL có query string.

Stack trace có thể hữu ích nhưng cần đánh giá message của thư viện. Có thể log exception class đã phân loại và stack trace sau khi redaction hoặc trong sink hạn chế truy cập. Không xóa hết thông tin lỗi đến mức không thể chẩn đoán; hãy chuẩn hóa và che phần nhạy cảm.

## 19. Alert dựa trên tỷ lệ và độ trễ

Metric cần gắn với SLO. Một số tín hiệu cảnh báo:

| Tín hiệu | Điều cần phát hiện |
|---|---|
| p95/p99 find latency tăng | Redis/JDBC chậm hoặc pool nghẽn |
| save timeout rate tăng | Session persistence có nguy cơ thất bại |
| repository unavailable tăng | Kho session mất kết nối |
| serialization error tăng | Payload/class/serializer không tương thích |
| find miss tăng đột biến | Cookie, namespace, TTL hoặc deploy sai |
| delete/expire event bất thường | Session churn hoặc cleanup lỗi |
| active session estimate tăng nhanh | TTL hoặc cleanup không đúng |
| connection pool pending tăng | Thiếu connection hoặc query chậm |

Dùng tỷ lệ trên cửa sổ thời gian và baseline thay vì alert chỉ vì một lỗi đơn lẻ. Alert cần có runbook: kiểm tra Redis/JDBC health, connection pool, latency, deployment version, serializer, cookie configuration và error category.

Không gửi session ID vào alert message. Nếu cần một ví dụ request, đính traceId/requestId đã được tạo an toàn.

## 20. Kiểm thử không rò rỉ định danh

Telemetry cần test như một phần của integration test:

- Gửi request với session cookie chứa giá trị giả lập.
- Tạo session mới và cập nhật attributes.
- Cố tình gây lỗi repository.
- Thu thập log test appender.
- Kiểm tra metrics exposition không có session ID/user ID.
- Kiểm tra span attributes không chứa cookie hoặc ID.
- Kiểm tra trace baggage không có định danh thô.
- Kiểm tra proxy/access log và APM config theo môi trường staging.

Ví dụ kiểm tra log output:

~~~java
String logOutput = testAppender.getLogs();

assertThat(logOutput).doesNotContain("test-session-secret");
assertThat(logOutput).doesNotContain("Cookie:");
assertThat(logOutput).doesNotContain("Set-Cookie:");
~~~

Chuỗi test-session-secret là marker giả lập. Không dùng ID thật. Cần bảo đảm test appender thu thập cả log của filter, security, repository và client driver chứ không chỉ logger của controller.

Metric test nên đọc MeterRegistry và kiểm tra danh sách tag keys/values không chứa marker. Trace test nên thu thập spans qua in-memory exporter và duyệt toàn bộ attributes, events, links và baggage.

## 21. Kiểm thử metric cardinality

Để phát hiện metric label sai:

1. Gửi nhiều request với session ID khác nhau.
2. Chạy cùng operation/outcome.
3. Kiểm tra số meter/time series không tăng theo số session.
4. Xác nhận tag keys chỉ là operation, repository, outcome và version.
5. Kiểm tra không có requestId, traceId hoặc userId trong labels.
6. Kiểm tra exception message không được dùng làm tag.

Nếu 10.000 session tạo ra 10.000 series mới, metric design đang sai. Số lượng series nên tăng theo số tổ hợp dimension hữu hạn, không tăng theo traffic volume hoặc số người dùng.

## 22. Trace sampling và chi phí

Trace toàn bộ request có thể tốn storage và băng thông. Sampling policy nên cân bằng giữa chi phí và khả năng điều tra:

- Head sampling quyết định sớm ở đầu trace, đơn giản và giảm chi phí.
- Tail sampling có thể giữ trace lỗi/chậm sau khi đã quan sát, nhưng cần collector hỗ trợ và cấu hình cẩn thận.
- Giữ tỷ lệ sampling ổn định để so sánh latency.
- Ưu tiên giữ trace lỗi, timeout hoặc vượt latency threshold nếu chính sách cho phép.
- Không sampling theo session ID hoặc user ID.
- Không đặt raw identifier trong sampling attributes.

Khi trace bị sample out, log vẫn có thể có requestId nhưng không có trace backend record. Runbook cần phân biệt “không tìm thấy trace do sampling” với “trace context không được truyền”.

## 23. Quy tắc bảo vệ dữ liệu trong telemetry

Áp dụng nguyên tắc tối thiểu:

1. Chỉ thu thập dữ liệu cần để chẩn đoán.
2. Ưu tiên operation/outcome thay cho định danh người dùng.
3. Dùng traceId/spanId/requestId để liên kết một lần xử lý.
4. Không đưa session ID, cookie hoặc token vào metric, trace, baggage hay log.
5. Dùng HMAC fingerprint chỉ khi có use case điều tra cụ thể.
6. Không đưa định danh giả danh vào metric label.
7. Redact ở gateway, application, driver instrumentation và exporter.
8. Giới hạn quyền đọc log/trace và thời gian retention.
9. Mã hóa telemetry khi truyền và khi lưu theo chính sách tổ chức.
10. Kiểm thử redaction bằng marker giả lập trước khi release.

Metrics cho biết xu hướng, trace cho biết đường đi của request và log giải thích sự kiện cụ thể. Với Spring Session, hãy đo repository operation bằng các nhãn có cardinality thấp, tạo span cho find/save/delete, rồi ghi log cấu trúc có traceId/spanId/requestId. Không công bố session ID, cookie, token hoặc user identifier thô trong bất kỳ tín hiệu nào. Nếu thực sự cần liên kết nhiều sự kiện của cùng một session, dùng HMAC fingerprint có quản lý khóa và retention chặt chẽ, không dùng nó làm metric label. Redaction cần được kiểm thử xuyên suốt từ proxy tới exporter, vì chỉ che ở ứng dụng không đủ để ngăn rò rỉ.

## Tài liệu tham khảo

- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Metrics Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Session — Session Events](https://docs.spring.io/spring-session/reference/api.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

