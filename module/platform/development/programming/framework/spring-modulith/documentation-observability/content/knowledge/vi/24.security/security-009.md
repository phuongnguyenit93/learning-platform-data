# Kiểm tra rò rỉ qua log correlation

> **Chương:** Bảo mật  
> **Bối cảnh:** Spring Modulith giúp quan sát ranh giới application module và tương tác giữa các phần trong ứng dụng Spring Boot. Micrometer Tracing có thể đưa `traceId` và `spanId` vào MDC để log của nhiều module được tìm theo cùng một trace. Khả năng này rút ngắn thời gian điều tra, nhưng log correlation cũng có thể làm lộ dữ liệu nhạy cảm, mang dữ liệu không đáng tin cậy qua service boundary hoặc khiến log bị giả mạo. Bài này hướng dẫn thiết kế correlation an toàn và kiểm tra rò rỉ trong toàn bộ đường đi của log.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách Spring Boot đưa `traceId` và `spanId` vào log correlation.
2. Phân biệt trace context, baggage, correlation ID và danh tính đã xác thực.
3. Xác định các điểm có thể rò rỉ secret, PII hoặc dữ liệu nghiệp vụ qua log.
4. Ngăn log injection và giả mạo log entry từ dữ liệu đầu vào.
5. Giữ MDC/context đúng khi request đi qua executor, async listener và Reactor.
6. Thiết kế allowlist, redaction, quyền truy cập, retention và audit cho log pipeline.
7. Kiểm thử rò rỉ bằng synthetic requests, log scanning và concurrent workloads.

## 1. Log correlation giải quyết vấn đề gì?

Một request có thể đi qua nhiều module:

```text
POST /orders
  -> orders.CheckoutService
  -> pricing.QuoteService
  -> payments.PaymentService
  -> publish OrderPlaced
  -> inventory.OrderPlacedListener
```

Mỗi module có thể ghi log ở thời điểm khác nhau. Nếu log không có thông tin liên kết, người vận hành phải tìm theo timestamp, thread hoặc nội dung message và dễ ghép nhầm các request chạy đồng thời.

Với Micrometer Tracing, Spring Boot có thể đưa `traceId` và `spanId` vào MDC. Log correlation ID mặc định được tạo từ hai giá trị đó, giúp:

- Tìm các log thuộc cùng một trace.
- Phân biệt từng span/operation trong trace.
- Đối chiếu log với trace backend.
- Theo dõi lời gọi qua module hoặc service boundary.
- Điều tra lỗi async nếu context được truyền đúng.

Ví dụ:

```text
2026-11-27 10:15:20.100 INFO [shop-service,4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7] orders.CheckoutService : Order accepted
2026-11-27 10:15:20.125 INFO [shop-service,4bf92f3577b34da6a3ce929d0e0e4736,8a3f4e1c2d9b7a10] payments.PaymentService : Payment authorized
```

Hai log có cùng `traceId` nhưng `spanId` khác nhau vì chúng thuộc hai span khác nhau. Đây là hành vi bình thường. Không yêu cầu toàn bộ log trong một trace phải có cùng cả hai giá trị.

## 2. Spring Boot tạo correlation ID như thế nào?

Khi Micrometer Tracing được cấu hình, Spring Boot mặc định đưa correlation ID vào log. Correlation ID được tạo từ các giá trị MDC:

- `traceId`: định danh trace.
- `spanId`: định danh span hiện tại.

Spring Boot 3.5 và 4.x có thể tùy chỉnh format bằng `logging.pattern.correlation`.

Ví dụ:

```yaml
logging:
  pattern:
    correlation: "[shop-service,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
```

Dấu cách ở cuối pattern giúp tách correlation ID khỏi tên logger trong format mặc định. Nếu pattern tùy chỉnh đã chứa application name thì có thể tắt trường application name mặc định để tránh lặp.

Nếu dùng tên MDC key tùy chỉnh, pattern phải tham chiếu đúng key thực tế. Một số cấu hình tracer/bridge có quy tắc MDC riêng; kiểm tra log output của phiên bản đang chạy thay vì giả định mọi implementation giống nhau.

### 2.1. Correlation ID không phải access token

`traceId` và `spanId` là định danh phục vụ quan sát:

- Không chứng minh người gọi đã đăng nhập.
- Không chứng minh quyền truy cập một resource.
- Không thay thế session ID hoặc authentication principal.
- Không nên dùng làm khóa cấp quyền hoặc quyết định nghiệp vụ.

Một người biết `traceId` không vì thế có quyền xem trace hoặc log. Backend vẫn phải kiểm soát quyền truy cập theo user/team/tenant và chính sách dữ liệu.

### 2.2. Correlation ID có thể xuất hiện dù trace không được lưu

Sampling quyết định trace/span nào được record hoặc export. Log correlation và trace export là hai đường dữ liệu khác nhau. Tùy tracer và sampling configuration, log có thể có correlation ID nhưng trace không xuất hiện trong backend vì sampling hoặc export failure.

Ngược lại, một log không có correlation ID có thể đến từ startup/shutdown, scheduler hoặc code chạy ngoài trace scope. Không coi mọi log thiếu correlation ID là lỗi bảo mật; xác định log nào bắt buộc phải gắn context.

## 3. Phân biệt trace context, baggage và correlation metadata

| Thành phần | Mục đích | Quy tắc bảo mật |
| --- | --- | --- |
| `traceId` | Liên kết các span trong một trace | Dùng để tìm kiếm, không dùng làm danh tính |
| `spanId` | Xác định một operation/span | Không dùng làm credential hoặc authorization |
| `traceparent` | Truyền trace ID, parent ID và flags qua boundary | Dữ liệu từ bên ngoài vẫn phải được coi là untrusted |
| `tracestate` | Truyền vendor-specific trace state | Chỉ chấp nhận format/size phù hợp với propagator |
| Baggage | Truyền key/value metadata qua nhiều service | Chỉ allowlist field; không chứa secret/PII |
| Request/correlation ID riêng | Hỗ trợ tìm request trong log | Validate, giới hạn kích thước và phân biệt ID do client cung cấp |
| Authenticated principal | Danh tính đã được security layer xác minh | Ghi theo chính sách audit riêng, không suy ra từ trace context |

### 3.1. Không ghi toàn bộ baggage vào log

Baggage có thể được tự động truyền qua các HTTP request được instrument. Một field được thêm ở ingress có thể đến các service downstream hoặc third-party API.

Không đưa các giá trị sau vào baggage:

- Access token, API key, password hoặc session secret.
- Email, số điện thoại, địa chỉ hoặc thông tin cá nhân không cần thiết.
- Payment data hoặc nội dung request.
- Customer ID/tenant ID nếu không có mục đích, căn cứ và kiểm soát phù hợp.

Chỉ truyền các field đã được duyệt và cần thiết cho telemetry. Baggage không có cơ chế integrity mặc định để chứng minh giá trị đến từ service đáng tin cậy. Không dùng baggage để quyết định quyền truy cập hoặc tin cậy một actor.

### 3.2. Trace context từ client là dữ liệu không đáng tin cậy

Request bên ngoài có thể gửi `traceparent`, `tracestate` hoặc correlation header riêng. Propagator kiểm tra cấu trúc theo format, nhưng việc header hợp lệ không chứng minh nguồn gửi đáng tin.

Tại public ingress:

- Chỉ chấp nhận propagation formats được hệ thống hỗ trợ.
- Không log nguyên văn mọi header trace/baggage.
- Không dùng trace ID do client gửi làm bằng chứng audit identity.
- Đặt chính sách rõ ràng về việc tiếp tục remote trace context hay tạo trace mới ở ranh giới tin cậy.
- Giới hạn kích thước và số lượng metadata được chuyển tiếp.
- Không để sampled flag hoặc metadata bên ngoài làm vượt ngân sách telemetry mà không có kiểm soát.

Nếu cần giữ correlation ID do client cung cấp, ghi nó thành trường riêng có tên thể hiện nguồn gốc, sau khi validate và giới hạn độ dài. Không ghi đè `traceId` nội bộ bằng một chuỗi tùy ý.

## 4. Các đường rò rỉ thường gặp

### 4.1. Log toàn bộ HTTP request/response

Các middleware, filter hoặc debug interceptor có thể ghi:

- Authorization header.
- Cookie và Set-Cookie.
- Query parameters.
- Request/response body.
- Multipart upload metadata hoặc file path.
- Exception message chứa input.

Những trường này có thể chứa token, password, dữ liệu cá nhân, payment data hoặc nội dung nghiệp vụ. Không bật full request/response logging ở production như một cách mặc định để tăng khả năng correlation.

### 4.2. Log baggage hoặc MDC tùy biến

Một field được đưa vào baggage hoặc MDC có thể xuất hiện trong nhiều log downstream. Nếu field chứa email, user ID, tenant secret hoặc token, một cấu hình correlation tiện lợi có thể mở rộng phạm vi rò rỉ sang nhiều service.

Kiểm tra cả:

- MDC keys do tracing bridge tạo.
- MDC keys do ứng dụng thêm.
- Baggage fields được đưa vào MDC.
- Structured logging customizers.
- Logging pattern/layout.

### 4.3. Log exception và SQL

Stack trace có thể chứa:

- SQL query và bind parameters.
- URL nội bộ hoặc connection string.
- File path.
- Header/request metadata.
- Exception message chứa dữ liệu đầu vào.

Không tự động coi stack trace là dữ liệu an toàn. Giữ thông tin cần chẩn đoán nhưng redaction/format ở nơi phù hợp; không ghi toàn bộ object hoặc request payload chỉ để có thêm ngữ cảnh.

### 4.4. Log injection và log forging

Nếu input có CR/LF hoặc ký tự điều khiển được ghép vào log text, attacker có thể tạo thêm dòng log giả hoặc làm sai cấu trúc sự kiện.

Ví dụ không an toàn:

```java
logger.warn("Login failed for user " + username);
```

Parameterized logging tốt hơn về cách giữ message template:

```java
logger.warn("Login failed for user {}", username);
```

Nhưng placeholder không tự loại bỏ CR/LF hoặc ký tự điều khiển. Cần dùng structured logging encoder/layout escape giá trị đúng format, giới hạn độ dài và validate/sanitize field từ trust zone khác.

## 5. Thiết kế log an toàn

### 5.1. Dùng allowlist cho field

Một log nghiệp vụ thường chỉ cần:

| Field | Ví dụ | Ghi chú |
| --- | --- | --- |
| `timestamp` | Thời điểm UTC | Dùng timestamp nhất quán |
| `service.name` | `shop-service` | Tên service cố định |
| `module.identifier` | `orders` | Module ID hữu hạn |
| `event.name` | `order.accepted` | Tên sự kiện ổn định |
| `traceId` | Trace identifier | Dùng correlation khi có |
| `spanId` | Span identifier | Có thể khác giữa các log trong cùng trace |
| `actor.type` | `customer`, `service`, `admin` | Chỉ ghi loại actor nếu hữu ích |
| `actor.ref` | Reference đã được phê duyệt | Không mặc định ghi email/username |
| `result` | `success`, `denied`, `failed` | Giá trị hữu hạn |
| `error.type` | Exception class/type đã chuẩn hóa | Tránh message động |

Không đưa toàn bộ object domain vào log. Chọn từng field có mục đích vận hành hoặc audit rõ ràng.

### 5.2. Ví dụ structured log

Với SLF4J 2 fluent API:

```java
log.atInfo()
    .addKeyValue("event.name", "order.accepted")
    .addKeyValue("module.identifier", "orders")
    .addKeyValue("result", "success")
    .addKeyValue("order.ref", safeOrderReference)
    .log("Order accepted");
```

Chọn JSON encoder/layout hỗ trợ structured key-value để giá trị được encode đúng định dạng. `safeOrderReference` cần là reference đã được duyệt, không phải dữ liệu nhạy cảm nguyên bản.

Ví dụ cấu hình structured console logging của Spring Boot ở phiên bản hỗ trợ:

```yaml
logging:
  structured:
    format:
      console: ecs
```

Structured logging không tự redaction. Vẫn cần allowlist, data classification, giới hạn kích thước và kiểm tra output thực tế.

### 5.3. Không log các trường sau

- Password, access token, refresh token, API key, private key.
- Authorization, Cookie, Set-Cookie hoặc session secret.
- Payment card data và bank credentials.
- Request/response body chứa dữ liệu khách hàng.
- Email, phone, address hoặc government identifier nếu không có căn cứ và kiểm soát.
- SQL bind values, connection strings hoặc secret trong exception.
- Toàn bộ baggage hoặc toàn bộ request headers.

Nếu cần liên kết với actor hoặc customer, dùng reference đã được pseudonymize/approve theo chính sách dữ liệu. Không tự băm một giá trị nhạy cảm rồi mặc định nó vô danh; giá trị băm ổn định vẫn có thể liên kết một cá nhân qua nhiều hệ thống.

## 6. Context propagation và nguy cơ MDC bị rò giữa request

Spring Boot/Micrometer quản lý trace scope và MDC correlation. Khi code chuyển sang thread khác, context có thể không được truyền nếu executor/callback không hỗ trợ propagation.

Có hai lỗi cần phân biệt:

1. **Context bị mất:** log trong worker thiếu `traceId`/`spanId`.
2. **Context bị rò:** worker thread tái sử dụng còn giữ MDC của request trước và log request mới dưới correlation ID sai.

Lỗi thứ hai nghiêm trọng hơn vì có thể gắn log của user A vào trace của user B, làm sai điều tra và có thể tiết lộ quan hệ hoạt động.

### 6.1. Dùng context propagation cho executor

Với Spring Framework hỗ trợ `ContextPropagatingTaskDecorator`, có thể cấu hình executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncConfiguration {

    @Bean
    TaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("context-aware-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Gắn đúng executor cho `@Async` hoặc task submission đang cần propagation. Kiểm tra Spring Framework/Micrometer Context Propagation version và các `ThreadLocalAccessor` được đăng ký trong ứng dụng.

Không tự sao chép toàn bộ MDC vào thread pool bằng một map rồi quên khôi phục giá trị trước đó. Thread pool tái sử dụng thread; mọi context scope cần được đóng/khôi phục ngay cả khi task ném exception.

### 6.2. Spring Modulith async listener

`@ApplicationModuleListener` có semantics bất đồng bộ và transaction riêng theo cấu hình Spring Modulith. Không mặc định rằng log trong listener luôn mang cùng trace context với event publisher.

Xác định rõ:

- Listener có được kỳ vọng kế thừa trace context không?
- Executor/dispatcher nào thực thi listener?
- Context có được capture khi submit và restore khi chạy không?
- Listener có thể chạy lại sau restart/retry không?
- Nếu trace tách riêng, log có metadata an toàn để liên hệ với publication/event không?

Không dùng raw event payload hoặc dữ liệu nhạy cảm làm correlation metadata chỉ để ghép log publisher và listener.

### 6.3. Reactor và callback

Reactor dùng Reactor Context; MDC dựa trên ThreadLocal. Khi chuyển scheduler hoặc kết hợp callback với executor, context cần cơ chế propagation phù hợp. Kiểm tra:

- Automatic/context-propagation mode của stack đang dùng.
- Custom callback có capture/restore context đúng không.
- Log trước và sau `publishOn`/`subscribeOn` có correlation đúng không.
- Context có bị giữ lại sau khi reactive chain kết thúc không.

Không kết luận propagation hoạt động chỉ vì log ở thread HTTP có correlation ID.

## 7. Trust boundary khi nhận correlation headers

### 7.1. W3C Trace Context

Header `traceparent` truyền trace ID, parent span ID và trace flags. Propagator xử lý format chuẩn, nhưng trace context vẫn là metadata do một process khác cung cấp.

Ở gateway/public ingress:

- Validate và parse theo propagator chuẩn.
- Giới hạn số lượng và kích thước header.
- Không ghi nguyên văn giá trị lỗi vào log.
- Không dùng trace ID để xác thực actor.
- Không cho phép baggage tùy ý đi xuyên tới mọi downstream service.
- Quyết định rõ remote parent nào được tin cậy và chính sách sampling tương ứng.

### 7.2. Correlation header riêng

Nếu ứng dụng nhận `X-Correlation-ID`:

1. Xác định nguồn gửi có đáng tin không.
2. Validate charset và độ dài.
3. Loại CR, LF và ký tự điều khiển.
4. Giữ tên trường riêng, ví dụ `client.correlation_id`.
5. Không dùng giá trị này thay cho trace ID hoặc authenticated principal.
6. Không phản chiếu nguyên văn giá trị không hợp lệ vào response/log.

Nếu cần ID nội bộ để truy vết request, tạo ID ở ingress bằng generator phù hợp và giữ nó tách biệt với giá trị client gửi.

### 7.3. Baggage forwarding

Baggage có thể được instrumentation tự động gửi qua HTTP. Trước khi bật remote baggage fields:

- Xác định service nào nhận từng field.
- Kiểm tra có third-party API hoặc trust boundary nào trong đường đi.
- Chỉ allowlist key và value cần thiết.
- Không đưa secret, credential hoặc PII vào baggage.
- Đặt giới hạn kích thước và số field.
- Kiểm tra log/trace downstream để bảo đảm không có field ngoài ý muốn.

Không dùng baggage làm nơi truyền authorization, tenant permissions hoặc quyết định policy.

## 8. Kiểm tra log correlation có làm lộ dữ liệu không

Một quy trình kiểm tra cần xem cả source code, log output và log pipeline.

### 8.1. Kiểm tra source/configuration

Tìm các điểm:

- `logger.info/debug/warn/error` có ghi request, response hoặc domain object không.
- Logging filters/interceptors có ghi headers/body không.
- Có custom MDC fields hoặc baggage correlation fields không.
- Có exception handler log `exception.getMessage()` chứa input không.
- Có SQL logging hoặc bind parameter logging trong production không.
- Có log pattern/JSON customizer thêm toàn bộ MDC không.
- Có async executor nào không propagate/restore context không.

Đặc biệt kiểm tra cấu hình debug được bật tạm thời trong incident và chưa được tắt sau đó.

### 8.2. Kiểm tra output log thực tế

Gửi một request synthetic có:

- Trace context hợp lệ.
- Một baggage field giả đã được allowlist.
- Một giá trị input chứa CR/LF và ký tự điều khiển.
- Một chuỗi dài vượt giới hạn dự kiến.
- Marker giả đại diện cho token/email/password (không dùng secret thật).

Sau đó kiểm tra:

- Log record vẫn là một sự kiện có cấu trúc hợp lệ.
- Giá trị điều khiển được encode/sanitize.
- Không có marker nhạy cảm trong log output.
- Correlation ID đúng trace/span của request.
- Không có log từ request khác gắn nhầm context.
- Baggage không xuất hiện ở service không được phép nhận.

### 8.3. Kiểm tra song song để phát hiện MDC bleed

Chạy đồng thời hai request với trace ID khác nhau và buộc chúng dùng chung executor thread pool. Ghi log tại:

- Trước khi submit task.
- Đầu task.
- Sau một async boundary.
- Trong finally/completion path.
- Ở task kế tiếp trên thread có thể được tái sử dụng.

Kết quả mong đợi:

- Mỗi log có context của đúng request/task.
- Không log nào của request A xuất hiện dưới trace ID của request B.
- Task độc lập không mang MDC cũ.
- Sau exception/cancellation, context được restore.

Lặp lại test với task thành công, ném exception, timeout và cancellation.

## 9. Redaction và data minimization

### 9.1. Redact tại nguồn

Ưu tiên không tạo log chứa secret/PII. Redaction tại Collector là lớp phòng thủ bổ sung, vì dữ liệu có thể đã đi qua:

- Application memory.
- Async log queue.
- stdout/container runtime.
- Local agent hoặc sidecar.
- Network transport.
- Collector processor.

Nếu dữ liệu bị cấm đã được ghi ở ứng dụng, redact sau đó không làm cho việc thu thập ban đầu trở nên an toàn.

### 9.2. Redaction policy

| Trường | Hành động |
| --- | --- |
| Authorization/Cookie | Loại bỏ hoàn toàn |
| Password/API key/token | Loại bỏ hoàn toàn; không chỉ mask một phần nếu không cần |
| Request/response body | Không ghi mặc định |
| Email/phone/address | Loại bỏ hoặc pseudonymize theo policy được duyệt |
| SQL bind parameters | Tắt hoặc redact |
| Exception message | Chuẩn hóa; không đưa input nhạy cảm vào message |
| Trace ID/span ID | Giữ để correlation theo access policy |
| Module ID/event name | Giữ nếu là metadata kỹ thuật được phép |

### 9.3. Không coi masking là anonymization

Mask một phần email hoặc hash customer ID vẫn có thể cho phép liên kết người dùng giữa nhiều log. Đánh giá khả năng re-identification và quyền truy cập của log store. Chỉ giữ định danh khi có mục đích, căn cứ và thời hạn cụ thể.

## 10. Bảo vệ log pipeline

### 10.1. Quyền truy cập

Log có thể tiết lộ cấu trúc module, tên service, nội bộ hạ tầng và hoạt động người dùng. Giới hạn:

- Ai được tìm kiếm log production.
- Ai được xem raw headers/exception details nếu có.
- Ai được export/download log.
- Ai được thay đổi retention hoặc logging level.
- Ai được đọc audit/security logs.

Tách quyền đọc, ghi, quản trị và xóa. Ghi audit access cho các thao tác tìm kiếm/export nhạy cảm theo chính sách của tổ chức.

### 10.2. Bảo vệ khi truyền và lưu

- Dùng TLS cho log transport qua mạng không tin cậy.
- Mã hóa at rest theo khả năng của backend.
- Giới hạn quyền trên file/stdout collection và log store.
- Bảo vệ log khỏi sửa/xóa trái phép.
- Theo dõi log pipeline bị dừng hoặc mất kết nối.
- Đồng bộ thời gian giữa các service/host.
- Giới hạn queue/disk để log flood không gây cạn tài nguyên ứng dụng.

### 10.3. Retention và disposal

Ghi retention riêng cho application logs, security audit logs, traces và bản sao/backup. Không giữ log lâu hơn mức cần thiết, đồng thời không xóa trước thời hạn phải giữ theo policy. Xác định cách xử lý khi có yêu cầu xóa dữ liệu và cách lifecycle áp dụng cho backup/export.

### 10.4. Logging failure

Không để lỗi log pipeline vô tình làm lộ thông tin qua fallback console hoặc exception. Đối với log vận hành thông thường, thường cần tránh làm hỏng business request khi backend log tạm thời lỗi; với security audit events bắt buộc, cần chính sách durability/availability riêng. Quyết định fail-open hay fail-closed phải dựa trên loại sự kiện và yêu cầu nghiệp vụ, không dùng một quy tắc cho mọi log.

## 11. Phân biệt correlation logs và security audit logs

Correlation giúp tìm các dòng log cùng trace; audit log ghi lại actor, action, object và outcome theo yêu cầu kiểm toán.

| Tiêu chí | Operational correlation log | Security audit log |
| --- | --- | --- |
| Mục tiêu | Debug và theo dõi request | Ghi nhận sự kiện bảo mật/hoạt động có trách nhiệm |
| Trace ID | Hữu ích để nối log/trace | Trường bổ sung, không phải bằng chứng actor |
| Actor identity | Có thể không cần | Cần danh tính đã được xác minh theo policy |
| Action/result | Mô tả xử lý kỹ thuật | Ghi rõ hành động và kết quả được kiểm soát |
| Retention/access | Theo log operations policy | Theo audit/security policy riêng |
| Integrity | Bảo vệ log store | Có thể cần kiểm soát chống sửa/xóa và audit access chặt hơn |

Ví dụ audit event nên ghi actor reference đã được xác thực, action, resource reference an toàn, outcome và timestamp. Không suy ra actor từ `traceId`, baggage hoặc correlation header.

## 12. Runbook khi phát hiện rò rỉ qua log correlation

### Bước 1 — Khoanh vùng dữ liệu

- Xác định field bị lộ: token, PII, baggage, request body hay correlation metadata.
- Xác định service/module, môi trường và thời gian bắt đầu.
- Kiểm tra log có bị chuyển tiếp tới third-party hoặc tenant khác không.
- Xác định các index, archive, backup và export có chứa dữ liệu.

### Bước 2 — Ngăn phát sinh thêm

- Tắt hoặc sửa đúng logger/filter/customizer gây rò.
- Loại field khỏi baggage propagation nếu không cần.
- Chặn request/response body logging ở production.
- Redact field tại nguồn và kiểm tra structured encoder.
- Giới hạn quyền truy cập log store trong khi xử lý.

### Bước 3 — Đánh giá phạm vi bản sao

- Tìm các bản log trong central store, sidecar, archive và backup.
- Xác định thời hạn retention và quy trình purge phù hợp.
- Kiểm tra quyền truy cập/download đã xảy ra.
- Nếu secret/credential bị lộ, kích hoạt quy trình rotation/revocation tương ứng.
- Nếu dữ liệu cá nhân bị lộ, chuyển theo quy trình incident/privacy của tổ chức.

Không đưa lại giá trị secret hoặc PII vào ticket/chat chỉ để minh họa bằng chứng. Dùng record ID, field name và redacted sample.

### Bước 4 — Xác minh sửa lỗi

- Chạy synthetic request có marker giả.
- Kiểm tra log output và downstream baggage.
- Chạy concurrent async test để tìm MDC bleed.
- Quét log mới theo pattern nhạy cảm đã được phê duyệt.
- Kiểm tra log pipeline vẫn nhận security events cần thiết.
- Lưu cấu hình/version, kết quả kiểm tra và owner xác nhận.

## 13. Ví dụ checklist review code

Khi review thay đổi liên quan logging/tracing:

- [ ] Message template cố định; không nối chuỗi input trực tiếp.
- [ ] Không log authorization, cookie, token, password hoặc request body.
- [ ] Không serialize toàn bộ domain object vào log.
- [ ] Field có nguồn từ client đã validate, giới hạn kích thước và encode.
- [ ] Structured logging encoder escape CR/LF/control characters.
- [ ] MDC chỉ chứa field allowlist.
- [ ] Baggage chỉ chứa key/value đã được duyệt.
- [ ] Trace/correlation ID không được dùng làm identity hoặc authorization.
- [ ] Executor/async listener/Reactive flow đã kiểm tra context propagation.
- [ ] Context scope được restore sau success, exception, timeout và cancellation.
- [ ] Log access, transport, retention và export phù hợp policy.
- [ ] Có test phát hiện leakage và log injection.

## 14. Bài tập tự kiểm tra

**Câu 1.** Hai log có cùng `traceId` nhưng `spanId` khác nhau. Điều này có phải lỗi correlation không?

**Câu 2.** Một request có `traceparent` hợp lệ. Có thể tin rằng người gửi là service nội bộ không? Vì sao?

**Câu 3.** Vì sao không nên đưa email hoặc access token vào baggage rồi cấu hình để baggage xuất hiện trong MDC?

**Câu 4.** Parameterized logging có ngăn hoàn toàn log injection bằng CR/LF không?

**Câu 5.** Một async worker không có correlation ID. Cần kiểm tra những điểm nào trước khi kết luận có lỗi?

**Câu 6.** Một log của request A xuất hiện với trace ID của request B trên thread pool dùng chung. Đây là loại lỗi gì và cần test thêm điều gì?

**Câu 7.** Vì sao trace ID không thể thay thế actor identity trong security audit log?

**Câu 8.** Redaction tại Collector có đủ nếu application đã ghi token vào stdout không?

**Câu 9.** Sampling loại trace khỏi backend. Điều đó có nhất thiết có nghĩa log correlation ID cũng biến mất không?

### Gợi ý đáp án

1. Không. Các operation khác nhau trong cùng trace thường có span ID riêng; điều quan trọng là trace ID liên kết đúng và quan hệ span được tạo đúng.
2. Không. Header có thể đến từ client bên ngoài; format hợp lệ không chứng minh nguồn gửi hoặc danh tính.
3. Baggage có thể được tự động truyền tới downstream/third-party và có thể xuất hiện trong log; token/email tạo rủi ro lộ bí mật và dữ liệu cá nhân.
4. Không. Placeholder giữ template nhưng không tự sanitize CR/LF; cần structured encoder, validation và giới hạn kích thước.
5. Kiểm tra task có được kỳ vọng nhận context không, executor được dùng, context capture/restore, async listener semantics và Reactor/callback boundary.
6. Đây là MDC/context bleed hoặc stale ThreadLocal. Test concurrent requests, thread reuse, exception, cancellation và cleanup/restore.
7. Trace ID chỉ là correlation metadata; nó không xác minh principal, authentication hoặc quyền truy cập.
8. Không. Dữ liệu đã đi qua process, stdout và có thể local buffer/agent trước Collector; phải ngăn hoặc redact tại nguồn.
9. Không nhất thiết. Log correlation và trace export là hai pipeline; tùy tracer/sampling configuration, MDC IDs vẫn có thể được ghi trong log dù trace không được lưu.

## 15. Checklist kiểm tra rò rỉ qua log correlation

- [ ] Đã xác nhận Spring Boot/Micrometer Tracing version và MDC key names.
- [ ] Đã kiểm tra log correlation format thực tế.
- [ ] Trace ID và span ID chỉ dùng cho correlation, không dùng làm credential/identity.
- [ ] Không log toàn bộ request/response headers hoặc body.
- [ ] Không log Authorization, Cookie, token, password, API key hoặc payment data.
- [ ] Baggage được allowlist và không mang secret/PII không cần thiết.
- [ ] Correlation header từ client được validate, giới hạn và ghi tách nguồn.
- [ ] Structured logging encoder escape CR/LF/control characters.
- [ ] Input logged được giới hạn độ dài và không thể tạo log record giả.
- [ ] MDC/context được truyền đúng qua executor, async listener và Reactor.
- [ ] Không có MDC bleed giữa hai request chạy đồng thời.
- [ ] Redaction được thực hiện tại nguồn; Collector chỉ là lớp bảo vệ bổ sung.
- [ ] Log store có access control, secure transport, retention và audit.
- [ ] Đã thử synthetic leakage markers và kiểm tra log output/downstream.
- [ ] Đã có runbook xử lý leakage, rotation/revocation và purge bản sao.

## 16. Ghi nhớ

Log correlation của Spring Boot/Micrometer Tracing thường dùng `traceId` và `spanId` trong MDC. Các ID này giúp liên kết log với trace, nhưng không xác minh danh tính hay quyền truy cập. Baggage và correlation headers có thể đến từ bên ngoài, được truyền qua nhiều service và xuất hiện trong log; chỉ allowlist metadata cần thiết, không đưa secret/PII vào đó.

Ngăn rò rỉ tại nguồn: không log credentials, request/response body hoặc toàn bộ domain object; dùng structured logging encoder, giới hạn độ dài và kiểm tra CR/LF. Kiểm tra context propagation trên executor, async listener và Reactor để tránh mất context hoặc MDC bleed giữa request. Bảo vệ log store bằng access control, TLS, retention và audit. Khi phát hiện rò rỉ, khoanh vùng mọi bản sao, ngăn phát sinh thêm, rotation/revocation nếu secret bị lộ và xác minh bằng synthetic tests.

### Tài liệu tham khảo

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): correlation IDs trong log, MDC và `logging.pattern.correlation`.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging patterns, MDC và structured logging.
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html): propagation giữa ThreadLocal, Observation và Reactor context.
- [Micrometer Tracing — Span and Baggage Scopes](https://docs.micrometer.io/tracing/reference/context-contracts.html): quản lý span/baggage scope và context trên thread.
- [OpenTelemetry — Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/): propagation behavior và security considerations của baggage.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context qua service boundaries và baggage.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại bỏ, log injection, access control và retention.
