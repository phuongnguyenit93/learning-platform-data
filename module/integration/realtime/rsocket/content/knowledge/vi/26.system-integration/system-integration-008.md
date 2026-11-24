# Bảo toàn thời hạn xử lý, danh tính và mã tương quan qua các giao thức

Một request trong hệ thống phân tán có thể đi từ trình duyệt tới API gateway, qua HTTP tới một service, tiếp tục qua RSocket tới service khác rồi phát một message lên broker. Mỗi chặng có giao thức, scheduler và cơ chế xác thực riêng. Nếu chỉ giữ ngữ cảnh trong biến cục bộ, một phần thông tin quan trọng có thể biến mất khi request đi qua ranh giới đó.

Ba loại ngữ cảnh cần được bảo toàn có mục đích khác nhau:

- **Deadline:** thời điểm muộn nhất mà toàn bộ công việc còn có ý nghĩa. Mỗi service phải dùng phần thời gian còn lại, không tự cấp lại toàn bộ timeout.
- **Identity:** người dùng hoặc service đang thực hiện hành động, cùng quyền được ủy quyền. Danh tính phải được xác thực và giữ đúng chủ thể qua từng hop.
- **Correlation và trace context:** thông tin liên kết log, span và sự kiện của cùng một luồng xử lý. Correlation ID phục vụ truy vết nghiệp vụ; trace context phục vụ distributed tracing.

Reactor Context giúp giữ ngữ cảnh trong một pipeline reactive tại một tiến trình. Khi gọi HTTP, RSocket hoặc message broker, ứng dụng phải ánh xạ các giá trị cần truyền sang header, metadata hoặc message envelope của giao thức đích, rồi khôi phục chúng ở phía nhận.

## 1. Nhìn request như một luồng đi qua nhiều giao thức

Ví dụ một người dùng tạo lệnh chuyển tiền. API gateway nhận HTTP request, gọi Account Service qua RSocket để kiểm tra số dư, sau đó gửi yêu cầu xử lý tới Payment Service qua message broker.

~~~mermaid
flowchart LR
    U[Browser] -->|HTTP + bearer token + traceparent| G[API gateway]
    G -->|RSocket metadata| A[Account Service]
    A -->|Message headers / envelope| B[Message broker]
    B --> P[Payment Service]
    G -.->|Một deadline end-to-end| D[Deadline]
    G -.->|Một chủ thể được ủy quyền| I[Identity]
    G -.->|Một trace liên tục| T[Trace context]
~~~

Ở mỗi ranh giới, hệ thống cần trả lời ba câu hỏi:

1. Request còn bao nhiêu thời gian trước deadline?
2. Ai là chủ thể thực hiện hành động và service hiện tại được phép làm gì thay mặt họ?
3. Làm sao nối log và trace của chặng hiện tại với các chặng trước?

Nếu không có hợp đồng truyền ngữ cảnh, mỗi service có thể tự tạo timeout mới, dùng nhầm service account làm người dùng cuối hoặc tạo correlation ID khác. Khi đó request không còn một giới hạn thời gian, một danh tính và một trace thống nhất.

## 2. Deadline end-to-end khác timeout của từng hop

Timeout của một lời gọi là giới hạn thời gian cho riêng lời gọi đó. Deadline là mốc kết thúc chung của toàn request. Ví dụ request có deadline sau 2 giây; gateway dùng 300 ms, service A dùng 500 ms, service B dùng 700 ms. Service B chỉ còn khoảng 500 ms, không được bắt đầu một timeout 2 giây mới.

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| End-to-end deadline | Toàn bộ request qua nhiều service | Hoàn tất trước 14:30:02 UTC |
| Per-hop timeout | Một lời gọi HTTP/RSocket cụ thể | Chờ Account Service tối đa 400 ms |
| Local execution timeout | Một thao tác trong service | Query database tối đa 150 ms |
| Queue expiration | Thời điểm message không còn được xử lý | Bỏ message đã quá hạn khi consumer nhận |

Deadline nên được truyền dưới dạng thời điểm tuyệt đối có múi giờ UTC hoặc một hợp đồng timeout budget được định nghĩa rõ. Khi nhận deadline tuyệt đối, service tính thời gian còn lại từ đồng hồ của chính nó, sau đó dùng thời lượng đó làm timeout cục bộ.

Không serialize giá trị System.nanoTime() sang service khác. Đây là đồng hồ monotonic chỉ có ý nghĩa trong tiến trình hiện tại. Dùng nó để đo elapsed time tại một máy; dùng Instant/epoch deadline hoặc một timeout budget theo giao thức để trao đổi giữa các máy.

## 3. Tạo deadline ở ingress và tính phần thời gian còn lại

Gateway là nơi phù hợp để đặt deadline nếu client không cung cấp một deadline đáng tin cậy. Nếu nhận deadline từ client, cần kiểm tra định dạng, giới hạn tối đa và chính sách clock skew. Không cho phép client yêu cầu thời gian vô hạn.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public record RequestDeadline(Instant expiresAt) {

    public Duration remaining(Clock clock) {
        return Duration.between(clock.instant(), expiresAt);
    }

    public boolean isExpired(Clock clock) {
        return !expiresAt.isAfter(clock.instant());
    }
}
~~~

Các key dùng trong ví dụ có thể được khai báo tập trung:

~~~java
public final class ContextKeys {

    private ContextKeys() {
    }

    public static final Object DEADLINE = new Object();
    public static final Object CORRELATION_ID = new Object();
}
~~~

Gateway có thể áp dụng thời hạn mặc định và giới hạn thời hạn do client yêu cầu:

~~~java
Instant now = clock.instant();
Duration serviceMaximum = Duration.ofSeconds(3);

Instant deadline = requestedDeadline
    .map(value -> value.isBefore(now.plus(serviceMaximum))
        ? value
        : now.plus(serviceMaximum))
    .orElse(now.plus(serviceMaximum));

RequestDeadline requestDeadline = new RequestDeadline(deadline);
~~~

requestedDeadline là giá trị đã được parse và kiểm tra từ request. Nếu client gửi deadline đã hết hạn, gateway nên từ chối sớm hoặc trả lỗi deadline exceeded theo hợp đồng API.

Ở mỗi service, tính lại thời gian còn lại ngay trước khi gọi dependency:

~~~java
Duration remaining = requestDeadline.remaining(clock);

if (remaining.isZero() || remaining.isNegative()) {
    return Mono.error(new DeadlineExceededException());
}

return downstreamCall()
    .timeout(remaining);
~~~

Reactor timeout dùng một thời lượng tương đối cho subscription hiện tại. Thời gian chờ thực tế được đo bởi scheduler/clock nội bộ phù hợp; không cần truyền timestamp monotonic qua mạng. Nên tính remaining ngay lúc subscription chạy thay vì tính khi dựng publisher từ lâu trước đó.

~~~java
public Mono<AccountResult> checkAccount(String accountId) {
    return Mono.deferContextual(context -> {
        RequestDeadline deadline =
            context.get(ContextKeys.DEADLINE);
        Duration remaining = deadline.remaining(clock);

        if (remaining.isZero() || remaining.isNegative()) {
            return Mono.error(new DeadlineExceededException());
        }

        return accountClient.check(accountId)
            .timeout(remaining);
    });
}
~~~

Nếu dependency có timeout riêng nhỏ hơn remaining, hãy dùng giới hạn nhỏ hơn. Timeout per-hop không được vượt quá thời gian còn lại của request.

## 4. Đồng hồ, clock skew và thời gian trên mạng

Deadline tuyệt đối giúp service phía sau biết mốc kết thúc chung, nhưng đồng hồ các máy có thể lệch nhau. Nếu đồng hồ consumer chậm hơn, consumer có thể nghĩ request còn thời gian dù deadline thực tế đã qua. Nếu đồng hồ nhanh hơn, request có thể bị dừng sớm.

Các nguyên tắc thực tế:

- Đồng bộ đồng hồ máy chủ bằng NTP hoặc cơ chế thời gian chuẩn của nền tảng.
- Chấp nhận sai lệch nhỏ theo một chính sách được định nghĩa; không cộng thêm một khoảng thời gian lớn tùy tiện.
- Giới hạn deadline tối đa tại ingress và tại service nhận.
- Tính thời lượng còn lại khi bắt đầu mỗi hop, không tái sử dụng timeout gốc.
- Dùng monotonic clock cho phép đo thời gian đã trôi qua trong cùng tiến trình.

Có thể truyền thêm timeout budget để các hệ thống có clock không đồng bộ trao đổi thời lượng tương đối. Tuy nhiên budget được gửi đi không tự trừ thời gian truyền trên mạng nếu receiver chỉ bắt đầu đếm khi nhận message. Vì vậy, nếu yêu cầu deadline nghiêm ngặt, dùng absolute deadline với đồng hồ được đồng bộ hoặc một giao thức deadline chuẩn đã xác định rõ cách tính và sai số.

Không nên tự cộng thêm network latency ước đoán ở mỗi hop nếu không có mô hình đo lường đáng tin cậy; điều đó có thể làm timeout bị trừ hai lần hoặc kéo dài sai deadline.

## 5. Truyền deadline qua HTTP

HTTP không định nghĩa một header deadline chung cho mọi ứng dụng. Các service nội bộ có thể thống nhất một header riêng, ví dụ X-Request-Deadline chứa timestamp ISO-8601 UTC. Nếu dùng gRPC, có thể dùng cơ chế deadline/timeout của gRPC thay vì tự tạo header HTTP.

Ví dụ WebClient đọc deadline từ Reactor Context, đưa nó vào header và đặt timeout theo phần thời gian còn lại:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public Mono<InventoryResult> checkInventory(
    String sku,
    String delegatedAccessToken
) {
    return Mono.deferContextual(context -> {
        RequestDeadline deadline =
            context.get(ContextKeys.DEADLINE);
        String correlationId =
            context.get(ContextKeys.CORRELATION_ID);
        Duration remaining = deadline.remaining(clock);

        if (remaining.isZero() || remaining.isNegative()) {
            return Mono.error(new DeadlineExceededException());
        }

        return webClient.get()
            .uri("/inventory/{sku}", sku)
            .header("X-Request-Deadline", deadline.expiresAt().toString())
            .header("X-Correlation-ID", correlationId)
            .headers(headers -> headers.setBearerAuth(delegatedAccessToken))
            .retrieve()
            .bodyToMono(InventoryResult.class)
            .timeout(remaining);
    });
}
~~~

Trong ví dụ này, traceparent nên được inject bởi tracing instrumentation đang dùng thay vì tự tạo một giá trị tùy ý. X-Correlation-ID là header nội bộ của ứng dụng; nó không thay thế W3C Trace Context.

Service nhận HTTP request phải parse deadline, kiểm tra giá trị tối đa, rồi dựng lại RequestDeadline trong pipeline. Không tin header deadline đến từ Internet nếu chưa giới hạn và xác thực nguồn.

## 6. Truyền deadline và identity qua RSocket

RSocket mang dữ liệu ứng dụng trong payload và metadata. Có thể dùng composite metadata để gửi route, authentication metadata, deadline và correlation ID trong cùng request. Mỗi loại metadata cần MIME type và codec tương ứng được cấu hình ở cả hai phía.

Ví dụ client Spring gửi deadline và correlation ID qua custom metadata, còn access token qua Bearer Authentication Metadata Extension:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<OrderView> lookupOrder(
    RSocketRequester requester,
    String orderId,
    RequestDeadline deadline,
    String correlationId,
    String delegatedAccessToken
) {
    return Mono.defer(() -> {
        Duration remaining = deadline.remaining(clock);
        if (remaining.isZero() || remaining.isNegative()) {
            return Mono.error(new DeadlineExceededException());
        }

        return requester.route("orders.lookup")
            .metadata(deadline.expiresAt().toString(), DEADLINE_MIME_TYPE)
            .metadata(correlationId, CORRELATION_MIME_TYPE)
            .metadata(delegatedAccessToken, AUTHENTICATION_MIME_TYPE)
            .data(new OrderLookupRequest(orderId))
            .retrieveMono(OrderView.class)
            .timeout(remaining);
    });
}
~~~

DEADLINE_MIME_TYPE và CORRELATION_MIME_TYPE là MIME type custom do ứng dụng định nghĩa và phải có metadata encoder/extractor tương ứng. AUTHENTICATION_MIME_TYPE phải dùng MIME type của RSocket Bearer Token Authentication mà Spring Security cấu hình. Không gộp token vào custom correlation metadata.

Ví dụ khai báo MIME type và ánh xạ custom metadata thành message header ở server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.codec.CharSequenceEncoder;
import org.springframework.core.codec.StringDecoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import io.rsocket.metadata.WellKnownMimeType;

@Configuration
public class RSocketMetadataConfig {

    public static final MimeType DEADLINE_MIME_TYPE =
        MimeTypeUtils.parseMimeType("message/x.acme.deadline.v1");
    public static final MimeType CORRELATION_MIME_TYPE =
        MimeTypeUtils.parseMimeType("message/x.acme.correlation.v1");
    public static final MimeType AUTHENTICATION_MIME_TYPE =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
            .encoder(CharSequenceEncoder.allMimeTypes())
            .decoder(StringDecoder.allMimeTypes())
            .metadataExtractorRegistry(registry -> {
                registry.metadataToExtract(
                    DEADLINE_MIME_TYPE, String.class, "requestDeadline");
                registry.metadataToExtract(
                    CORRELATION_MIME_TYPE, String.class, "correlationId");
            })
            .build();
    }
}
~~~

Trong ứng dụng thật, đặt các hằng số vào một lớp dùng chung và đăng ký encoder/decoder tương thích ở client lẫn server. Nếu dự án đã có String encoder/decoder phù hợp, tránh đăng ký trùng. Metadata xác thực được Spring Security xử lý riêng, không đăng ký lại thành custom header thông thường.

Các ví dụ requester và handler có thể import tĩnh ba hằng số public từ RSocketMetadataConfig để giữ MIME type thống nhất.

Ở phía server, metadata extractor ánh xạ custom metadata thành message headers. Adapter đọc deadline và correlation ID từ headers, kiểm tra deadline, sau đó dùng contextWrite để đặt giá trị vào pipeline reactive. Spring Security xử lý authentication metadata và cung cấp principal đã xác thực cho handler.

~~~java
import java.security.Principal;
import java.time.Duration;
import java.time.Instant;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Mono;

@MessageMapping("orders.lookup")
public Mono<OrderView> lookup(
    OrderLookupRequest request,
    @Header("requestDeadline") String deadlineValue,
    @Header("correlationId") String correlationId,
    Principal principal
) {
    RequestDeadline deadline =
        new RequestDeadline(Instant.parse(deadlineValue));

    return Mono.defer(() -> {
        Duration remaining = deadline.remaining(clock);
        if (remaining.isZero() || remaining.isNegative()) {
            return Mono.error(new DeadlineExceededException());
        }

        return orderService.findForSubject(
                request.orderId(),
                principal.getName()
            )
            .timeout(remaining);
    }).contextWrite(context -> context
        .put(ContextKeys.DEADLINE, deadline)
        .put(ContextKeys.CORRELATION_ID, correlationId)
    );
}
~~~

Tên header requestDeadline và correlationId phải khớp với tên mà MetadataExtractor đăng ký. Ví dụ trên mô tả phần handler sau khi metadata đã được ánh xạ; cấu hình extractor và codec phụ thuộc phiên bản Spring RSocket của ứng dụng.

## 7. Bảo toàn identity: xác thực, ủy quyền và delegation

Identity trả lời ai đang thực hiện hành động. Authorization trả lời chủ thể đó có được phép thực hiện hành động hiện tại hay không. Khi gateway gọi service thay mặt người dùng, cần bảo toàn cả danh tính người dùng cuối lẫn danh tính service đang thực hiện lời gọi.

Có ba mô hình thường gặp:

| Mô hình | Credential tới service sau | Ý nghĩa |
|---|---|---|
| Service-to-service | Client credentials của service gọi | Service tự thực hiện hành động theo quyền của nó |
| On-behalf-of / token exchange | Token được cấp cho service với subject là người dùng | Service hành động thay mặt người dùng theo audience/scope được ủy quyền |
| Trusted identity assertion | Assertion nội bộ có chữ ký hoặc được bảo vệ bởi hạ tầng tin cậy | Truyền subject/actor khi hệ thống có hợp đồng xác minh assertion rõ ràng |

Không chỉ gửi một chuỗi userId trong header rồi coi đó là danh tính đã xác thực. Header có thể bị giả mạo nếu không có ranh giới tin cậy và chữ ký/xác thực phù hợp.

Khi chuyển tiếp access token, kiểm tra audience, issuer, expiry và scope. Không chuyển tiếp token dành cho API khác. Nếu Identity Provider hỗ trợ OAuth 2.0 Token Exchange hoặc on-behalf-of flow, hãy dùng token được cấp cho service đích với quyền tối thiểu.

Service token và user token có vai trò khác nhau. Service token xác định workload gọi; delegated user token xác định chủ thể mà workload được phép đại diện. Service phía sau nên ghi nhận cả subject và actor/client identity khi chính sách audit yêu cầu.

## 8. Truyền identity qua HTTP và RSocket

Qua HTTP, token người dùng thường được gửi trong Authorization: Bearer. Qua RSocket, Spring Security dùng Bearer Token Authentication Metadata Extension. Khi gateway chuyển request từ HTTP sang RSocket, cần lấy token đã xác thực từ security context hoặc thực hiện token exchange, rồi gắn nó vào authentication metadata của đúng request.

~~~java
Mono<OrderView> callRSocketAsCurrentUser(
    RSocketRequester requester,
    String orderId,
    String delegatedToken
) {
    return requester.route("orders.lookup")
        .metadata(
            delegatedToken,
            AUTHENTICATION_MIME_TYPE
        )
        .data(new OrderLookupRequest(orderId))
        .retrieveMono(OrderView.class);
}
~~~

Nếu một RSocket connection được dùng chung cho nhiều người dùng, không đặt user token riêng vào SETUP metadata rồi dùng chung cho tất cả request. Đặt token người dùng vào request metadata của từng tương tác để mỗi stream có identity riêng. SETUP có thể xác thực service/gateway sở hữu kết nối.

Ở phía nhận, dùng Spring Security để xác thực token và lấy Principal/Authentication đã được xác thực. Không lấy userId từ payload để quyết định quyền truy cập dữ liệu.

## 9. Correlation ID và distributed trace là hai khái niệm

Correlation ID là mã do ứng dụng dùng để nhóm các log hoặc sự kiện thuộc một nghiệp vụ. W3C Trace Context định nghĩa traceparent và tracestate để truyền trace/span context giữa các hệ thống. Chúng liên quan nhưng không thể thay thế nhau.

| Giá trị | Mục đích | Ví dụ |
|---|---|---|
| Correlation ID | Tìm tất cả log của một nghiệp vụ/request | order-flow-8f21 |
| traceparent | Nối trace và parent span qua service | 00-{trace-id}-{parent-id}-01 |
| tracestate | Truyền thông tin vendor-specific của tracing | vendor=value |
| Span ID | Xác định một operation cụ thể trong trace | 16-byte identifier |

Một request có thể giữ cùng correlation ID qua nhiều service, nhưng mỗi service thường tạo span riêng và trace instrumentation cập nhật parent/span context theo chuẩn. Không tự sao chép traceparent cũ vào mọi outbound request nếu tracing library đã quản lý propagation; làm vậy có thể khiến span graph sai.

Correlation ID do client gửi vào cần được kiểm tra độ dài và ký tự hợp lệ. Nếu thiếu, gateway tạo ID mới. Không dùng chuỗi tùy ý không giới hạn làm log field vì có thể gây log injection hoặc làm tăng cardinality của metric.

## 10. Truyền correlation và trace qua HTTP, RSocket và broker

Các giao thức có cách mang metadata khác nhau:

| Giao thức | Deadline | Identity | Correlation/trace |
|---|---|---|---|
| HTTP | Header deadline nội bộ hoặc timeout của giao thức | Authorization Bearer / mTLS identity | traceparent, tracestate, X-Correlation-ID |
| RSocket | Custom composite metadata hoặc request envelope | Authentication metadata extension | Custom metadata; tracing instrumentation nếu hỗ trợ |
| Kafka/message broker | Event envelope có expiresAt hoặc TTL của broker | Service identity; actor/subject đã xác minh trong event nếu cần | Message headers traceparent và correlation ID |
| Reactor pipeline | RequestDeadline trong Reactor Context | Spring Security reactive SecurityContext | Correlation ID và tracing context trong Reactor Context |

Reactor Context không tự serialize qua mạng. Ở outbound adapter, đọc các giá trị từ Context rồi ghi chúng vào protocol metadata. Ở inbound adapter, xác thực và parse metadata rồi dựng Context mới cho pipeline local.

Ví dụ helper gắn correlation ID và deadline:

~~~java
public static <T> Mono<T> withRequestContext(
    Mono<T> pipeline,
    RequestDeadline deadline,
    String correlationId
) {
    return pipeline.contextWrite(context -> context
        .put(ContextKeys.DEADLINE, deadline)
        .put(ContextKeys.CORRELATION_ID, correlationId)
    );
}
~~~

Không dùng một static mutable map để lưu context theo request ID. Mọi request đồng thời phải có Context riêng theo subscription.

## 11. Truyền ngữ cảnh qua message broker và xử lý bất đồng bộ

Message broker tạo một ranh giới thời gian khác với lời gọi đồng bộ. Producer có thể gửi message và kết thúc HTTP request trước khi consumer bắt đầu xử lý. Vì vậy cần xác định deadline có còn ý nghĩa ở thời điểm consumer nhận message hay không.

Với command có thời hạn, event envelope có thể chứa:

~~~java
public record PaymentCommand(
    String commandId,
    String accountId,
    long amountInMinorUnits,
    Instant expiresAt,
    String correlationId,
    String subject
) {
}
~~~

Không mặc định dùng deadline ngắn của HTTP request làm thời hạn sống của một công việc bất đồng bộ. Nếu HTTP chỉ xác nhận đã nhận command còn consumer xử lý sau đó, hãy định nghĩa expiresAt theo thời hạn nghiệp vụ riêng. Nếu command phải hoàn tất trong cùng SLA của request đồng bộ, mới truyền deadline end-to-end đó tới consumer.

Producer chỉ đưa subject vào envelope sau khi xác thực danh tính và theo chính sách audit. Consumer vẫn xác thực service producer/broker và kiểm tra tính toàn vẹn, nguồn gốc của message. Một trường subject đơn lẻ không phải credential và không đủ để cấp quyền.

Khi consumer nhận message:

~~~java
public Mono<PaymentResult> handle(PaymentCommand command) {
    RequestDeadline deadline =
        new RequestDeadline(command.expiresAt());

    Duration remaining = deadline.remaining(clock);
    if (remaining.isZero() || remaining.isNegative()) {
        return Mono.error(new CommandExpiredException());
    }

    return paymentService.execute(command)
        .timeout(remaining)
        .contextWrite(context -> context
            .put(ContextKeys.DEADLINE, deadline)
            .put(ContextKeys.CORRELATION_ID, command.correlationId())
        );
}
~~~

Trong hệ thống bất đồng bộ, consumer có thể cần xử lý message sau một thời gian chờ queue. Nếu deadline đã qua, message nên bị loại bỏ, đưa vào dead-letter queue hoặc đánh dấu expired theo chính sách. Không bắt đầu một timeout mới chỉ vì consumer vừa nhận message.

Broker TTL thường điều khiển thời gian lưu message trong queue, không nhất thiết bảo đảm handler dừng đúng deadline nghiệp vụ. Consumer vẫn phải kiểm tra expiresAt trước khi thực hiện tác dụng phụ.

Không đưa raw bearer token vào message lâu sống. Nếu công việc cần tiếp tục thay mặt người dùng sau khi HTTP request kết thúc, hãy lưu audit subject và quyền đã được kiểm tra, hoặc dùng một cơ chế delegation/token exchange có thời hạn phù hợp. Consumer thực hiện authorization lại theo chính sách của nghiệp vụ.

## 12. Retry, cancellation và ngân sách thời gian

Retry tiêu thụ thời gian của cùng request. Nếu mỗi lần retry cấp lại timeout ban đầu, tổng thời gian có thể vượt xa deadline mà client chấp nhận.

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<InventoryResult> checkWithRetry(String sku) {
    return Mono.deferContextual(context -> {
        RequestDeadline deadline =
            context.get(ContextKeys.DEADLINE);

        Duration overallRemaining = deadline.remaining(clock);
        if (overallRemaining.isZero() || overallRemaining.isNegative()) {
            return Mono.error(new DeadlineExceededException());
        }

        return Mono.defer(() -> {
            Duration remaining = deadline.remaining(clock);
            if (remaining.isZero() || remaining.isNegative()) {
                return Mono.error(new DeadlineExceededException());
            }

            return inventoryClient.check(sku)
                .timeout(remaining);
        })
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(50))
                .filter(this::isTransientFailure)
        )
        .timeout(overallRemaining);
    });
}
~~~

Mỗi lần subscribe lại, remaining được tính lại từ deadline chung. Timeout bên trong giới hạn từng lần gọi; timeout bên ngoài giới hạn tổng thời gian, bao gồm cả backoff. Cần giới hạn số lần retry và chỉ retry lỗi tạm thời, không retry lỗi xác thực hoặc validation.

Khi timeout hoặc client cancel, cancellation cần truyền tới outbound HTTP/RSocket publisher để giải phóng stream và tài nguyên nếu transport hỗ trợ. Timeout không đảm bảo đảo ngược một giao dịch đã commit ở service phía sau. Với lệnh ghi, dùng idempotency key và trạng thái giao dịch để xử lý kết quả không chắc chắn.

## 13. Giữ correlation và identity trong log

Log nên giúp người vận hành trả lời request đi qua những service nào, được thực hiện thay mặt ai và hết hạn ở đâu. Một log record có thể chứa:

- correlationId: mã nghiệp vụ xuyên suốt.
- traceId và spanId: do tracing instrumentation quản lý.
- subject: định danh đã xác thực, nếu chính sách log cho phép.
- actor/clientId: service hoặc workload thực hiện lời gọi.
- deadline và remainingMillis: thời hạn tuyệt đối hoặc thời gian còn lại tại hop.
- route/operation và outcome: tên thao tác cùng kết quả.

Không ghi access token, refresh token, mật khẩu hoặc toàn bộ authentication metadata. Subject và tenant cũng có thể là dữ liệu cá nhân; hãy áp dụng masking, retention và access control cho log.

Đối với metric, tránh dùng correlation ID, user ID hoặc order ID làm label có cardinality cao. Dùng metric theo route, outcome và loại lỗi; để ID cụ thể trong log hoặc trace.

## 14. Kiểm thử bảo toàn ngữ cảnh qua nhiều hop

Kiểm thử unit cho từng adapter chưa đủ để chứng minh ngữ cảnh được giữ xuyên suốt. Cần có integration test mô phỏng gateway gọi service qua HTTP/RSocket rồi gửi message tới consumer.

Các trường hợp nên kiểm tra:

1. Deadline ban đầu được giữ nguyên và remaining giảm qua từng hop.
2. Service nhận deadline đã hết hạn từ chối trước khi gọi dependency.
3. Timeout outbound không vượt quá remaining.
4. Retry không reset deadline hoặc vượt số lần cho phép.
5. Token người dùng được chuyển tiếp hoặc exchange đúng audience và scope.
6. Service identity và end-user subject được ghi nhận riêng.
7. Request của hai người dùng chạy đồng thời không bị trộn principal.
8. Correlation ID giữ nguyên qua HTTP, RSocket và message header.
9. traceparent được tracing instrumentation inject/extract đúng chuẩn.
10. Message tới consumer sau expiresAt bị loại bỏ hoặc xử lý theo chính sách expired.
11. Cancellation/timeout dừng stream downstream khi transport hỗ trợ.
12. Log không chứa raw token hoặc dữ liệu nhạy cảm ngoài chính sách.

Ví dụ kiểm tra remaining:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.deferContextual(context -> {
            RequestDeadline deadline =
                context.get(ContextKeys.DEADLINE);
            Clock testClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
            );
            return Mono.delay(deadline.remaining(testClock))
                .thenReturn("completed");
        })
        .contextWrite(context -> context.put(
            ContextKeys.DEADLINE,
            new RequestDeadline(
                Instant.parse("2026-01-01T00:00:02Z")
            )
        ))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("completed")
    .verifyComplete();
~~~

Ví dụ dùng Clock cố định để phép tính remaining có kết quả xác định, còn StepVerifier điều khiển thời gian của Mono.delay. Với test kiểm tra nhiều lần tính lại deadline hoặc timeout ở nhiều hop, hãy dùng một Clock test có thể điều khiển cùng với scheduler ảo để cả hai tiến đồng bộ.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Mỗi service đặt timeout mới bằng timeout ban đầu | Tổng thời gian vượt deadline client | Truyền deadline chung và tính remaining mỗi hop |
| Gửi System.nanoTime() qua mạng | Giá trị không có ý nghĩa ở tiến trình khác | Dùng deadline UTC hoặc hợp đồng budget rõ ràng |
| Tin header userId từ client | Giả mạo danh tính | Xác thực token/assertion và dùng principal đã xác thực |
| Dùng service token thay user identity | Mất ngữ cảnh ủy quyền người dùng | Token exchange/on-behalf-of hoặc assertion tin cậy |
| Dùng correlation ID thay traceparent | Trace graph không chính xác | Dùng W3C Trace Context cùng correlation ID riêng |
| Nghĩ Reactor Context tự đi qua RSocket | Service đích thiếu context | Serialize metadata/payload và dựng Context ở adapter nhận |
| Gửi raw token trong message broker | Credential sống lâu và có thể bị lộ | Tránh chuyển token; dùng delegation/audit context phù hợp |
| Retry sau khi deadline hết hạn | Tạo tải vô ích và phản hồi quá muộn | Kiểm tra remaining trước mỗi lần thử |
| Log toàn bộ headers/metadata | Rò rỉ token và dữ liệu cá nhân | Allowlist field được log và masking |

## 16. Checklist thiết kế hợp đồng ngữ cảnh

Trước khi nối hai service bằng một giao thức khác, hãy thống nhất:

- Tên, định dạng và giới hạn của deadline.
- Clock source, clock skew tolerance và hành vi khi deadline thiếu/hết hạn.
- Cách tính remaining và timeout tối đa cho từng hop.
- Credential nào đại diện cho service, credential nào đại diện cho người dùng.
- Audience, scope và quy trình token exchange/delegation.
- Correlation ID được tạo ở đâu, kiểm tra ra sao và giữ qua các hop thế nào.
- Tracing dùng W3C traceparent/tracestate và instrumentation nào.
- Metadata MIME type hoặc HTTP/message header nào mang từng giá trị.
- Quy tắc xử lý message hết hạn, retry, cancellation và idempotency.
- Trường nào được phép xuất hiện trong log, trace và metric.

Hợp đồng nên được version hóa khi nhiều service hoặc nhóm phát triển cùng sử dụng. Thay đổi tên header, MIME type hoặc schema envelope cần tương thích ngược trong giai đoạn chuyển đổi.

## 17. Kết luận

Bảo toàn deadline, identity và correlation qua nhiều giao thức đòi hỏi một hợp đồng ngữ cảnh xuyên suốt. Deadline được truyền như mốc kết thúc chung và chuyển thành remaining timeout ở từng hop. Identity được xác thực và ủy quyền theo đúng chủ thể, tách biệt service identity với end-user identity. Correlation ID liên kết log nghiệp vụ, còn W3C Trace Context liên kết span trong distributed trace.

Reactor Context giữ các giá trị trong pipeline reactive tại một tiến trình. Khi gọi HTTP, RSocket hoặc message broker, adapter phải serialize các giá trị cần thiết vào header, metadata hoặc envelope, rồi xác thực và dựng Context ở phía nhận. Làm rõ từng ranh giới giúp request không bị kéo dài ngoài deadline, không mất danh tính và vẫn truy vết được khi đi qua nhiều service.
