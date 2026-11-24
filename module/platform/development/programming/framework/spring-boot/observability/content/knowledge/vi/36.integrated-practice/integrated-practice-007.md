# Thêm baggage và MDC correlation

Trong một hệ thống Spring Boot có nhiều service, `traceId` giúp liên kết các span thuộc cùng một request và `spanId` xác định operation đang được ghi nhận. Tuy nhiên, khi điều tra một luồng nghiệp vụ, đội vận hành đôi khi cần thêm một số ngữ cảnh nhỏ như loại khách hàng, kênh xử lý hoặc nhóm luồng để đọc log và lần theo request dễ hơn. Distributed tracing cung cấp **baggage** để mang những cặp key-value này qua ranh giới service; logging dùng **Mapped Diagnostic Context (MDC)** để tự động gắn ngữ cảnh hiện tại vào từng log event.

Với Spring Boot, Micrometer Observation và Micrometer Tracing có thể kết hợp baggage propagation với MDC correlation. Bài thực hành này xây dựng một luồng checkout: service nhận thông tin phân loại request đã được xác thực, đặt baggage trong phạm vi xử lý, truyền baggage đến service downstream và đưa trường baggage cùng trace ID/span ID vào logs. Ví dụ dùng Spring Boot 3 với Micrometer Tracing; hãy xác minh dependency và cấu hình theo phiên bản ứng dụng thực tế.

## 1. Phân biệt trace context, baggage và MDC

Ba khái niệm có liên quan nhưng đảm nhiệm các việc khác nhau:

| Thành phần | Nội dung | Phạm vi và mục đích |
| --- | --- | --- |
| Trace context | Trace ID, span ID hiện tại, parent relationship và sampling flags | Liên kết các operation trong cùng một distributed trace |
| Baggage | Các cặp key-value được truyền cùng trace context | Mang ngữ cảnh nghiệp vụ nhỏ qua các service, ví dụ `tenant-tier=premium` |
| MDC | Map key-value gắn với log event trong execution context hiện tại | Giúp mỗi dòng log mang trace ID, span ID hoặc correlation field |

Ví dụ một request có thể truyền hai header theo W3C:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: tenant-tier=premium,channel=web
```

`traceparent` mang thông tin để tiếp tục trace. `baggage` mang các thuộc tính bổ sung được cho phép. Các HTTP client/server đã được instrument sẽ inject và extract context theo propagation format đã cấu hình. Ứng dụng không nên tự ghép hoặc sửa header `traceparent` và `baggage` trong code nghiệp vụ.

MDC là ngữ cảnh dành cho logging tại process hiện tại. MDC không tự truyền qua HTTP hoặc message broker. Baggage có thể được propagate qua các transport được instrument; cấu hình correlation cho phép một số trường baggage xuất hiện trong MDC. Vì vậy, baggage hỗ trợ chia sẻ ngữ cảnh giữa service, còn MDC giúp ngữ cảnh đó xuất hiện trên log của từng service.

`traceId` cũng không luôn thay thế được business correlation ID. Một workflow nghiệp vụ kéo dài qua nhiều request, message hoặc retry có thể tạo nhiều trace khác nhau. Khi cần nối các hoạt động đó, dùng một correlation ID nghiệp vụ được quản lý riêng và truyền qua message metadata hoặc baggage theo chính sách. Không tạo thêm ID nếu trace ID hiện tại đã trả lời được câu hỏi điều tra.

## 2. Khai báo baggage cần propagate và đưa vào MDC

Spring Boot cung cấp cấu hình Micrometer Tracing để khai báo các baggage field cần truyền từ service này sang service khác và các field cần thêm vào MDC.

Ví dụ `application.yml`:

```yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
        - channel
      correlation:
        fields:
          - tenant-tier
          - channel

logging:
  pattern:
    level: "%5p [${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},tenantTier=%X{tenant-tier:-},channel=%X{channel:-}]"
```

Ý nghĩa của cấu hình:

- `remote-fields` khai báo các baggage field được phép truyền qua ranh giới process theo propagation mechanism của Micrometer Tracing.
- `correlation.fields` khai báo các baggage field cần đưa vào MDC để logging backend có thể hiển thị chúng.
- `logging.pattern.level` thêm `traceId`, `spanId` và các key MDC vào phần level/prefix của logback pattern.

Spring Boot thường tự đưa `traceId` và `spanId` vào MDC khi Micrometer Tracing được bật và logging integration hoạt động. Việc thêm `tenant-tier` hoặc `channel` vào MDC cần cấu hình correlation field tương ứng. Nếu dùng Log4j2 hoặc một logging encoder riêng, cách hiển thị MDC sẽ theo pattern/encoder của hệ thống đó.

Chỉ khai báo những trường thật sự cần thiết. Mỗi field trong baggage có thể được gửi qua nhiều service và làm tăng kích thước HTTP header, do đó không đưa toàn bộ thông tin request vào baggage.

## 3. Tạo baggage trong phạm vi xử lý bằng Micrometer Tracing

Không nên lấy trực tiếp mọi header từ client rồi đưa nguyên giá trị vào baggage. Baggage có thể được chuyển tiếp đến các service downstream, vì vậy ứng dụng cần xác thực, chuẩn hóa và giới hạn giá trị tại ranh giới tin cậy.

Ví dụ, gateway hoặc tầng xác thực đã xác định request thuộc nhóm `standard` hay `premium`. Controller đặt baggage `tenant-tier` trong scope của request:

```java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final Tracer tracer;
    private final CheckoutService checkoutService;

    public CheckoutController(
            Tracer tracer,
            CheckoutService checkoutService) {
        this.tracer = tracer;
        this.checkoutService = checkoutService;
    }

    @PostMapping("/checkout")
    public ResponseEntity<CheckoutResult> checkout(
            @RequestHeader(name = "X-Tenant-Tier", required = false)
            String requestedTier,
            @RequestBody CheckoutCommand command) {

        String tenantTier = "premium".equals(requestedTier)
                ? "premium"
                : "standard";

        try (BaggageInScope baggage = tracer.createBaggageInScope(
                "tenant-tier", tenantTier)) {
            CheckoutResult result = checkoutService.checkout(command);
            return ResponseEntity.ok(result);
        }
    }
}
```

`createBaggageInScope` đặt giá trị vào context hiện tại và trả về một scope cần đóng. `try-with-resources` bảo đảm scope được khôi phục kể cả khi service ném exception. Các lời gọi được instrument thực hiện bên trong scope có thể tiếp tục sử dụng baggage này. Ví dụ giả định `X-Tenant-Tier` đã được gateway bảo vệ; trong hệ thống thực tế, nên lấy tier từ kết quả xác thực hoặc dữ liệu server-side thay vì tin một header tùy ý từ Internet.

Nếu cần thêm `channel`, có thể tạo thêm baggage scope hoặc xây dựng một helper quản lý nhiều field. Giữ danh sách key cố định và value có miền giá trị hữu hạn như `web`, `mobile` hoặc `partner`.

### Không giữ baggage scope lâu hơn operation

Baggage scope phải có vòng đời rõ ràng. Đóng scope sau khi xử lý xong giúp tránh rò rỉ ngữ cảnh sang request tiếp theo khi thread được tái sử dụng. Không lưu `BaggageInScope` vào field singleton, không giữ scope trong object dùng chung và không đóng scope trước khi một operation đồng bộ cần nó hoàn tất.

Ví dụ trên dùng Spring MVC với lời gọi đồng bộ. Với WebFlux hoặc phương thức trả về `Mono`/`Flux`, không bọc việc tạo publisher bằng `try-with-resources` rồi đóng scope ngay khi publisher được trả về; subscription có thể diễn ra sau đó. Hãy dùng Reactor Context và cơ chế context propagation tương thích với phiên bản Spring Boot/Micrometer để scope tồn tại trong quá trình reactive thực thi.

## 4. Quan sát baggage và MDC trong log

Giả sử `CheckoutService` gọi một payment client đã được instrument:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final PaymentClient paymentClient;

    public CheckoutService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public CheckoutResult checkout(CheckoutCommand command) {
        log.info("Starting checkout");
        PaymentResult payment = paymentClient.authorize(command);
        log.info("Payment authorization completed");
        return CheckoutResult.from(payment);
    }
}
```

Khi tracing và logging integration hoạt động, log có thể có dạng:

```text
INFO [checkout,trace=4bf92f3577b34da6a3ce929d0e0e4736,span=00f067aa0ba902b7,tenantTier=premium,channel=web] Starting checkout
INFO [checkout,trace=4bf92f3577b34da6a3ce929d0e0e4736,span=00f067aa0ba902b7,tenantTier=premium,channel=web] Payment authorization completed
```

Hai log event có thể có cùng trace ID và span ID nếu được ghi trong cùng span hiện tại. Khi lời gọi payment tạo client span, log trong phần thực thi span đó có thể mang span ID tương ứng với client operation. Log ở payment service sẽ có cùng trace ID nhưng span ID thuộc service đó. Nhờ vậy, có thể tìm tất cả log của một trace bằng trace ID, sau đó thu hẹp vào operation bằng span ID.

Nếu log không có `traceId` hoặc `spanId`, kiểm tra tracing bridge, sampling, instrumentation và logging pattern. Nếu trace ID có nhưng `tenant-tier` vắng mặt, kiểm tra baggage đã được tạo trong đúng scope, field có nằm trong `correlation.fields` và logging pattern có dùng đúng tên MDC key hay không.

## 5. Propagate baggage qua HTTP client và service downstream

Baggage chỉ được truyền khi propagation được cấu hình và HTTP client/server tham gia instrumentation. Trong Spring Boot, dùng client được instrument bởi Micrometer Tracing hoặc cấu hình observation convention/interceptor phù hợp cho client đang dùng. Không tự copy toàn bộ header inbound sang outbound vì có thể chuyển tiếp header không tin cậy hoặc dữ liệu nhạy cảm.

Luồng tổng quát:

```text
Client
  |
  | HTTP request
  v
Checkout API
  | tạo span server
  | đặt baggage tenant-tier=premium
  |
  | instrumented HTTP client
  | inject trace context + baggage
  v
Payment API
  | extract trace context + baggage
  | tạo span server con
  | baggage xuất hiện trong MDC nếu đã cấu hình correlation
  v
Payment service
```

Để kiểm tra propagation, thực hiện request qua hai service và xác minh:

1. Trace backend hiển thị cùng trace ID ở checkout và payment.
2. Payment server span là hậu duệ của client span phù hợp trong checkout trace.
3. Baggage field đã khai báo được nhận ở payment service.
4. Log của cả hai service có trace ID; log có baggage field nếu service đó bật correlation field.
5. Khi request kết thúc, baggage không xuất hiện nhầm trong một request độc lập chạy tiếp trên cùng worker thread.

Nếu HTTP client tự tạo span nhưng không inject baggage, kiểm tra propagation type và instrumentation của đúng client. Các thư viện HTTP tự tạo hoặc interceptor tùy biến có thể cần tích hợp Observation/Tracing riêng.

## 6. Bảo đảm context qua executor và xử lý bất đồng bộ

MDC và một số cơ chế tracing dựa trên thread-local context. Khi chuyển công việc sang thread pool, thread mới không tự động kế thừa context của thread gọi. Nếu không propagate context, log trong tác vụ nền có thể mất trace ID, span ID và baggage; trong tình huống xấu, code dùng ThreadLocal thủ công còn có thể để sót giá trị từ tác vụ trước.

Với Spring Framework 6.1 trở lên, có thể dùng `ContextPropagatingTaskDecorator` cho executor do ứng dụng quản lý:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
```

Đảm bảo tác vụ `@Async` hoặc tác vụ được submit thực sự sử dụng executor này. Với Spring Framework cũ hơn, dùng giải pháp context propagation tương thích với phiên bản Micrometer/Spring đang chạy và kiểm thử trên executor thực tế. Không tự sao chép tất cả MDC map vào thread pool rồi giữ lại sau khi task kết thúc.

Với Reactor, context gắn với subscription thay vì gắn cố định vào một thread. Dùng cơ chế tích hợp Reactor Context và Micrometer Context Propagation phù hợp phiên bản; không giả định `MDC.put` ở đầu pipeline sẽ tồn tại trên mọi scheduler. Kiểm thử cả `publishOn`, `subscribeOn`, retry và callback bất đồng bộ vì chúng có thể đổi thread thực thi.

## 7. Khi nào cần business correlation ID riêng?

Trace ID thường đủ để gom log của một distributed request. Nhưng một workflow có thể kéo dài qua queue, batch hoặc nhiều request độc lập. Ví dụ một đơn hàng được tạo ở request đầu tiên, thanh toán qua message vài phút sau và hoàn tất bởi một consumer khác. Các phần này có thể có trace riêng nhưng vẫn thuộc cùng một nghiệp vụ.

Khi đó, có thể tạo `correlationId` nghiệp vụ có định dạng ổn định, được kiểm soát ở service tin cậy và truyền trong message metadata hoặc baggage đã được allowlist. Mỗi service đưa ID này vào MDC để log có thể truy vấn xuyên workflow. Không dùng ID này làm metric tag.

Nếu cần tạo correlation ID từ HTTP header, chỉ chấp nhận giá trị từ gateway tin cậy hoặc xác thực định dạng nghiêm ngặt; nếu không, sinh ID mới ở biên tin cậy. Giới hạn độ dài và ký tự để tránh log injection hoặc header bất thường. Ví dụ helper đơn giản cho MDC trong một servlet filter:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        // Giả định gateway tin cậy đã ghi đè header này trước khi chuyển tiếp.
        String candidate = request.getHeader("X-Correlation-ID");
        String correlationId = candidate != null
                && SAFE_ID.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        response.setHeader("X-Correlation-ID", correlationId);
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", correlationId)) {
            filterChain.doFilter(request, response);
        }
    }
}
```

Ví dụ này minh họa MDC cho một request servlet đồng bộ. Regex trong code chỉ kiểm tra định dạng và độ dài, không xác thực nguồn gửi; chỉ dùng candidate khi gateway tin cậy đã xác thực và ghi đè header. Nếu ứng dụng nhận traffic trực tiếp từ Internet, hãy sinh ID mới thay vì tin `X-Correlation-ID` do client cung cấp. Nếu correlation ID cần đi qua async hoặc service khác, phải propagate nó có chủ đích qua message metadata hoặc baggage và tiếp tục đặt vào MDC tại process nhận. `MDC` tự nó không truyền ID qua mạng hoặc thread pool. Chỉ giữ filter riêng khi có use case workflow rõ ràng; nếu trace ID đã đủ, thêm một correlation ID nữa chỉ làm log phức tạp hơn.

## 8. Bảo vệ baggage và MDC khỏi dữ liệu không an toàn

Baggage được gửi qua các service nên có thể làm lộ dữ liệu rộng hơn dự kiến. MDC thường được ghi vào log tập trung, nơi có nhiều người và công cụ truy cập. Áp dụng các quy tắc sau:

- Chỉ propagate các field có tên nằm trong allowlist `remote-fields`.
- Không đưa access token, session cookie, password, API key, email, số điện thoại hoặc dữ liệu cá nhân vào baggage.
- Không dùng baggage làm cơ chế xác thực, phân quyền hoặc bằng chứng về danh tính. Service nhận phải xác thực request bằng cơ chế bảo mật riêng.
- Xem baggage inbound từ bên ngoài là dữ liệu không tin cậy; xác thực, chuẩn hóa và giới hạn giá trị trước khi dùng cho logic hoặc log.
- Giữ số lượng field và kích thước value nhỏ để tránh vượt giới hạn header của proxy/server.
- Không đưa baggage có cardinality cao vào metric tag. Dùng giá trị hữu hạn như `tenant-tier` thay vì tenant ID nếu chỉ cần phân nhóm.
- Tránh ghi baggage vào MDC nếu field không cần xuất hiện trong log. Mỗi correlation field có thể làm tăng kích thước mọi log event.
- Kiểm tra log masking, quyền truy cập, retention và quy trình xóa dữ liệu theo chính sách của tổ chức.

Đặc biệt, không đưa toàn bộ `baggage` header vào log. Chỉ ghi các field được chọn, đã kiểm tra và có mục đích vận hành rõ ràng.

## 9. Kiểm thử baggage propagation và MDC correlation

Kiểm thử nên xác nhận hành vi qua ranh giới service và ranh giới thread, không chỉ xác nhận một dòng log ở controller.

Một bộ kiểm tra tích hợp có thể gồm:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Request hợp lệ với tier `premium` | Baggage `tenant-tier=premium` được tạo trong scope và xuất hiện trong log |
| Request có tier không được hỗ trợ | Giá trị được chuẩn hóa thành `standard`; không propagate chuỗi tùy ý |
| Gọi payment qua HTTP client đã instrument | Payment nhận cùng trace context và baggage được allowlist |
| Log ở service downstream | Có trace ID/span ID; baggage field xuất hiện nếu correlation đã bật |
| Service ném exception | Scope được đóng; request tiếp theo không nhận baggage cũ |
| Tác vụ chạy qua executor | Context được truyền nếu executor có context propagation decorator |
| Request không có tracing context | Ứng dụng xử lý theo cấu hình tracing; log không được chứa trace ID giả hoặc baggage cũ |
| Baggage chứa giá trị quá dài hoặc không hợp lệ | Giá trị bị từ chối hoặc chuẩn hóa ở biên tin cậy |

Ví dụ kiểm thử hành vi nghiệp vụ có thể dùng `MockMvc` để gửi request với các tier khác nhau, kiểm tra log capture hoặc spy service để xác nhận baggage có trong scope. Kiểm thử propagation đầy đủ cần hai ứng dụng hoặc một test setup có HTTP server/client instrumented; chỉ mock `Tracer` không chứng minh header được inject/extract đúng.

Khi xác minh log, không chỉ tìm `traceId` trong một dòng. Hãy kiểm tra cùng trace ID xuất hiện ở hai service, span ID thay đổi theo operation, baggage chỉ có trong phạm vi đã cấu hình và correlation ID nghiệp vụ (nếu có) được giữ qua workflow cần thiết.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Log có trace ID nhưng không có baggage | Chưa khai báo `correlation.fields`, sai tên key hoặc baggage chưa được đặt trong scope | Kiểm tra cấu hình, tên field và vị trí tạo scope |
| Baggage có ở service đầu nhưng mất ở service sau | Thiếu `remote-fields`, HTTP client không được instrument hoặc propagation format không thống nhất | Kiểm tra remote field, client/server instrumentation và propagation type |
| Baggage xuất hiện ở request tiếp theo | Scope không được đóng hoặc code tự quản lý ThreadLocal sai | Dùng `BaggageInScope` với try-with-resources và kiểm tra async boundary |
| Log trong async task thiếu trace ID | Context không được truyền sang executor | Cấu hình context propagation cho executor và kiểm thử task thực tế |
| Baggage header quá lớn | Có quá nhiều field hoặc value dài | Giảm allowlist, giới hạn kích thước và chỉ truyền dữ liệu cần thiết |
| Log chứa giá trị do client tự đặt | Tin trực tiếp baggage hoặc correlation header inbound | Xác thực nguồn, validate và chuẩn hóa tại gateway/service biên |
| Có nhiều ID khác nhau gây khó truy vấn | Dùng trace ID, request ID và business correlation ID không có quy ước | Xác định vai trò từng ID, chỉ giữ loại thật sự cần và dùng tên MDC thống nhất |

## 11. Checklist triển khai

- [ ] Micrometer Tracing và instrumentation của HTTP client/server được bật đúng phiên bản.
- [ ] Các baggage field cần truyền được khai báo trong `management.tracing.baggage.remote-fields`.
- [ ] Các baggage field cần xuất hiện trong logs được khai báo trong `management.tracing.baggage.correlation.fields`.
- [ ] Log pattern hiển thị `traceId`, `spanId` và các MDC key cần thiết.
- [ ] Baggage được tạo trong scope có vòng đời rõ ràng và được đóng sau operation.
- [ ] Baggage inbound được xác thực/chuẩn hóa và không chứa secret hoặc dữ liệu cá nhân.
- [ ] HTTP client/server downstream tiếp tục cùng trace context và nhận đúng baggage allowlist.
- [ ] Executor và Reactor pipeline có context propagation phù hợp.
- [ ] Business correlation ID chỉ được thêm khi trace ID không đủ cho workflow nhiều request/message.
- [ ] Không dùng baggage hoặc correlation ID làm metric tag có cardinality cao.
- [ ] Integration test xác minh propagation, MDC và việc không rò rỉ context giữa các request.

Khi kết hợp baggage và MDC đúng cách, đội vận hành có thể nhìn thấy ngữ cảnh nghiệp vụ đã chọn trong log của nhiều service và liên kết từng log event với distributed trace tương ứng. Micrometer Tracing quản lý scope và propagation, Spring Boot cấu hình field cần truyền và correlation, còn MDC chỉ phục vụ log event tại process hiện tại. Giữ baggage nhỏ, được kiểm soát và có vòng đời rõ ràng để việc correlation hỗ trợ điều tra mà không làm lộ dữ liệu hoặc tăng chi phí không cần thiết.
