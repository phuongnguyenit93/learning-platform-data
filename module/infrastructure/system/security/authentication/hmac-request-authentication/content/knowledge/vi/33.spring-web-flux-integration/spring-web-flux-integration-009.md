# Backpressure request body trong Spring WebFlux khi xác thực HMAC

## 1. Bài toán: cần xác minh HMAC trước khi xử lý body

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, một client HTTP tạo chữ ký HMAC từ shared secret và **canonical request**. Hợp đồng ký có thể ràng buộc method, URI, header, key ID, timestamp, nonce và digest của request body. Server phải kiểm tra chữ ký, chống replay bằng timestamp/nonce, trạng thái credential khi key rotation, sau đó mới cho phép nghiệp vụ tiếp tục. Với **Spring WebFlux**, request body không phải một `InputStream` thông thường như Spring MVC, mà thường được biểu diễn thành luồng:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Đây là luồng **reactive**, có cơ chế yêu cầu dữ liệu theo nhu cầu (*demand/backpressure*). Tuy nhiên, một HTTP body hợp lệ về mặt giao thức vẫn có thể lớn hàng gigabyte. Nếu bộ lọc HMAC gom mọi `DataBuffer` vào RAM, hệ thống có thể hết bộ nhớ **ngay cả khi upstream tuân thủ backpressure**.

Bài **Backpressure request body** trong chương **Spring WebFlux integration** tập trung trả lời bốn câu hỏi:

1. **Khi nào** cần đọc body để xác minh HMAC và vì sao phải giữ body cho handler đọc tiếp?
2. **Backpressure** giải quyết điều gì, còn giới hạn byte, timeout và concurrency giải quyết điều gì?
3. Làm sao quản lý vòng đời `DataBuffer` — bao gồm các buffer dùng pooled memory — khi success, error, cancel hoặc client ngắt kết nối?
4. Làm sao kiểm thử pipeline từ WebFlux `WebFilter`, `ReactiveAuthenticationManager`, `SecurityWebFilterChain` đến controller và gateway?

Mục tiêu là hiểu và thiết kế **một luồng xác thực HMAC non-blocking, có giới hạn tài nguyên và không phát sinh side effect trước khi chứng minh toàn vẹn request**.

## 2. Phân biệt backpressure, buffer và giới hạn request body

### Backpressure là gì?

Trong Reactive Streams, một subscriber thông báo số lượng phần tử mà nó muốn nhận qua `request(n)`. Publisher tuân thủ quy ước sẽ không phát ra nhiều phần tử hơn nhu cầu đã yêu cầu. Với WebFlux trên Reactor Netty, điều này giúp phối hợp tốc độ tiêu thụ và sản xuất dữ liệu, cùng các cơ chế điều khiển I/O tương ứng.

Nhưng **một phần tử `DataBuffer` không đồng nghĩa một byte**. Hai request có thể đều phát 10 phần tử nhưng tổng bytes khác nhau rất lớn. Một operator yêu cầu lần lượt các phần tử cũng có thể **tích lũy toàn bộ dữ liệu đã nhận**.

### Ba giới hạn riêng biệt

| Cơ chế | Điều kiểm soát | Điều **không** tự bảo đảm |
| --- | --- | --- |
| Backpressure | Nhu cầu nhận phần tử theo thời điểm | Giới hạn **tổng bytes** của request |
| Per-request body limit | Không giữ body vượt `maxBodyBytes` | Số request lớn chạy đồng thời |
| Concurrency, rate và timeout limit | Tổng số request/heap/connection bị tiêu thụ cùng lúc | Tính đúng đắn của canonical HMAC hoặc replay |

Ví dụ: 1.000 request đồng thời, mỗi request buffer tối đa **1 MiB**, đã có thể giữ gần **1 GiB** raw body trong RAM, chưa tính bản sao, object, Netty direct memory và overhead. Vì vậy, chỉ đặt `maxBodyBytes = 1 MiB` là chưa đủ nếu không giới hạn số request đồng thời.

**Kết luận:** backpressure giúp điều tiết dòng chảy, còn **giới hạn bytes, concurrency, thời gian đọc và chính sách lỗi** mới tạo ranh giới tài nguyên rõ ràng cho bước xác thực.

## 3. Luồng xác thực HMAC trong WebFlux

Một thiết kế có thể dùng `WebFilter` trong `SecurityWebFilterChain`, hoặc `AuthenticationWebFilter` với `ServerAuthenticationConverter` phù hợp. Các thành phần cần được đặt đúng ranh giới:

~~~mermaid
flowchart TD
    C["Client gửi request HMAC"] --> G["Gateway / Reactor Netty"]
    G --> F["WebFlux SecurityWebFilterChain"]
    F --> L["Parse signed headers và giới hạn input"]
    L --> B["Đọc DataBuffer có max byte + timeout"]
    B --> D["Digest raw body bytes + canonical request"]
    D --> A["ReactiveAuthenticationManager / HMAC verifier"]
    A --> K{"Credential, HMAC, timestamp, nonce hợp lệ?"}
    K -->|Không| E["401 / 413 / 503 theo nguyên nhân"]
    K -->|Có| R["Gắn Authentication vào Reactor Context"]
    R --> W["Replayable body cho downstream"]
    W --> P["Authorization tenant/action/resource"]
    P -->|Từ chối| X["403 hoặc policy che resource"]
    P -->|Cho phép| H["WebFlux handler / controller"]
~~~

Các quy tắc bắt buộc:

- Chỉ coi **principal/client** là đã xác thực sau khi dùng đúng secret để kiểm tra chữ ký và các điều kiện credential, timestamp/nonce.
- Body dùng cho `SHA-256` phải là **bytes thực sự nằm trong hợp đồng ký**, không phải JSON được deserialize rồi serialize lại.
- Khi body đã được đọc để xác minh, controller/codec phải tiếp tục nhận đúng body đó, không nhận `Flux.empty()` do stream bị tiêu thụ.
- Chỉ sau xác thực mới đặt `Authentication` tin cậy vào **Reactor Context**; không dùng `ThreadLocal` của Servlet cho WebFlux.
- HMAC đúng vẫn phải qua **authorization**: principal được phép gọi action, tenant và resource cụ thể hay không.

## 4. DataBuffer là gì và tại sao có thể rò rỉ bộ nhớ?

`DataBuffer` là API trừu tượng thao tác trên vùng dữ liệu byte. Trong thực tế, các `DataBuffer` có thể dùng bộ nhớ heap hoặc **pooled/direct buffer** do Netty quản lý. Đối với pooled buffer, việc giữ lại tham chiếu mà không release đúng có thể gây **memory leak** ngoài heap Java.

Ba tình huống nguy hiểm:

- **Thu gom nhưng không release:** code đọc `DataBuffer` vào một mảng byte rồi bỏ qua `DataBufferUtils.release(buffer)` khi cần, đặc biệt trong path lỗi.
- **Release quá sớm:** đưa `DataBuffer` vào luồng downstream rồi release trước khi consumer đọc; kết quả là truy cập dữ liệu không còn hợp lệ.
- **Release hai lần:** cùng một buffer bị release ở cả operator trung gian và `DataBufferUtils.join`/consumer vốn đã chịu trách nhiệm về ownership.

Trong Reactor, `onNext`, `onError`, `onComplete` và `cancel` đều ảnh hưởng đến vòng đời dữ liệu. Một request bị hủy giữa chừng có thể không chạy qua nhánh “happy path” mà lập trình viên dự kiến.

### Ownership của DataBuffer

| Tình huống | Ai cần chịu trách nhiệm? |
| --- | --- |
| Gọi `DataBufferUtils.join(...)` thành công | Caller phải **release joined buffer** sau khi sử dụng |
| `DataBufferUtils.join` hủy/lỗi/giới hạn quá mức | Operator quản lý và release các buffer nó đã tích lũy theo contract |
| Tự lưu các DataBuffer vào `List` | Code tự quản lý ownership, release cả lúc error/cancel |
| Tạo `DataBuffer` từ `bufferFactory.wrap(bytes)` rồi đưa vào HTTP response/handler | Chuyển ownership theo luồng tiêu thụ tương ứng; không release tùy tiện trước consumer |
| Operator bỏ rơi phần tử `DataBuffer` | Cần kiểm tra khả năng discard và xử lý cleanup thích hợp theo operator |

Vì quản lý pooled buffer có thể phức tạp, với **body nhỏ phải verify trước controller**, một chiến lược dễ kiểm soát là: **gom có giới hạn → copy sang `byte[]` → release joined buffer đúng một lần → tạo `DataBuffer` mới để replay**.

## 5. Sai lầm phổ biến: gom body không giới hạn

Ví dụ **không an toàn**:

~~~java
Mono<DataBuffer> allBody =
    DataBufferUtils.join(exchange.getRequest().getBody());
~~~

Overload trên **không đặt giới hạn tổng bytes**. Dù có backpressure, operator vẫn có thể tích lũy toàn bộ request trong bộ nhớ trước khi tạo kết quả.

Một biến thể khác cũng không an toàn:

~~~java
Mono<List<DataBuffer>> allChunks =
    exchange.getRequest().getBody().collectList();
~~~

`collectList()` không bảo đảm giới hạn bytes; nếu tự giữ các pooled `DataBuffer` mà không release đúng ở error/cancel, còn có nguy cơ memory leak.

Tương tự, không dùng `onBackpressureBuffer()` không giới hạn hoặc `cache()` vô điều kiện trên `Flux<DataBuffer>` để “cho controller đọc lại”. Các operator này có thể giữ buffer qua nhiều subscriber, tích lũy bộ nhớ hoặc giữ pooled memory sau khi request kết thúc.

**Biện pháp tối thiểu:** dùng overload `DataBufferUtils.join(Publisher, maxByteCount)` với giới hạn byte dương, đồng thời giới hạn ở ingress/gateway và số request HMAC đang xử lý.

## 6. Đọc body có giới hạn và release an toàn

Ví dụ Java 17, Spring WebFlux trên Reactor, trích xuất toàn bộ body **khi body đủ nhỏ để giữ trong RAM**:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Mono;

public final class BoundedBodyCapture {
    private BoundedBodyCapture() {}

    public static Mono<byte[]> read(
            Publisher<? extends DataBuffer> body,
            int maxBodyBytes) {

        if (maxBodyBytes <= 0) {
            throw new IllegalArgumentException(
                "maxBodyBytes must be positive");
        }

        return Mono.defer(() ->
            DataBufferUtils.join(body, maxBodyBytes)
                .map(joined -> {
                    try {
                        byte[] bytes =
                            new byte[joined.readableByteCount()];
                        joined.read(bytes);
                        return bytes;
                    } finally {
                        // Release joined buffer kể cả khi đọc/copy lỗi.
                        DataBufferUtils.release(joined);
                    }
                })
                // Request không có body vẫn có dữ liệu ký rõ ràng:
                // SHA-256 của mảng bytes rỗng.
                .defaultIfEmpty(new byte[0])
        );
    }
}
~~~

Các điểm cần hiểu:

1. `DataBufferUtils.join(body, maxBodyBytes)` tích lũy tối đa số byte theo giới hạn; khi vượt giới hạn, operator phát `DataBufferLimitException` và quản lý các buffer đã tích lũy.
2. Mã copy dữ liệu từ joined buffer sang `byte[]` một lần rồi **release joined buffer trong `finally`**.
3. `Mono.defer` giúp việc tham gia đọc dữ liệu diễn ra khi subscriber đăng ký, không ngay lúc dựng chuỗi operator.
4. `Mono.empty()` từ body rỗng được chuyển thành `byte[0]` để cả GET không body hoặc POST body rỗng có hash xác định.
5. Chỉ dùng helper này cho **một lần tiêu thụ nguồn request body**. Nó không biến publisher gốc thành nguồn có thể đọc nhiều lần.
6. Giới hạn áp dụng cho dữ liệu tới được `ServerHttpRequest.getBody()`. Nếu proxy giải nén/nén hoặc biến đổi payload, cần xác định **bytes nào là đối tượng được ký** và giới hạn cả trước/sau transformation khi phù hợp.

### Khi vượt giới hạn thì sao?

Nếu body vượt `maxBodyBytes`, `DataBufferLimitException` cần được ánh xạ thành phản hồi **413 Content Too Large** hoặc chính sách lỗi tương đương. Không được:

- Bỏ qua phần bytes vượt quá rồi ký digest của **body bị cắt**;
- Tăng giới hạn tự động theo `Content-Length` do client tự khai;
- Chuyển sang xác minh chỉ các header mà không ký body;
- Tiếp tục controller khi body chưa được xác thực.

Nên đặt giới hạn thêm ở ingress/Netty, yêu cầu timeout đọc và concurrency budget. `maxInMemorySize` ở các codec WebFlux hữu ích cho giải mã body, **không thay thế** giới hạn byte của custom HMAC filter đọc raw `Flux<DataBuffer>`.

## 7. Phát lại body cho controller sau khi HMAC hợp lệ

Với WebFlux, `ServerHttpRequestDecorator` có thể trả về **một publisher mới** phát các bytes đã capture. Điều này cho phép handler/codec đọc body mà filter đã tiêu thụ.

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.core.io.buffer.DataBufferFactory;
import reactor.core.publisher.Flux;

final class HmacReplayableRequest extends ServerHttpRequestDecorator {
    private final byte[] originalBody;
    private final DataBufferFactory bufferFactory;

    HmacReplayableRequest(
            ServerHttpRequest request,
            byte[] originalBody,
            DataBufferFactory bufferFactory) {
        super(request);
        this.originalBody = originalBody.clone();
        this.bufferFactory = bufferFactory;
    }

    @Override
    public Flux<DataBuffer> getBody() {
        // Tạo DataBuffer riêng ở MỖI subscription;
        // không đưa cùng pooled buffer cho hai subscriber.
        return Flux.defer(() ->
            Flux.just(bufferFactory.wrap(originalBody.clone()))
        );
    }
}
~~~

Đây là wrapper dành cho request đã **được buffer toàn bộ có giới hạn**. Trong một pipeline thông thường, chỉ downstream handler/codec sẽ subscribe vào `getBody()`. Việc mỗi subscription có bản copy riêng ngăn một consumer thay đổi vùng nhớ mà consumer khác đang dùng, nhưng vẫn tạo **overhead bộ nhớ**; nên giới hạn body và tránh những subscription không cần thiết.

Khi tạo request decorator, có thể dùng `exchange.getResponse().bufferFactory()` như một nguồn `DataBufferFactory` của môi trường đang xử lý. Việc đưa buffer vào `Flux` chuyển ownership tới consumer WebFlux; **không tự release ngay sau `Flux.just`**, vì buffer sẽ không còn hợp lệ khi codec đọc.

Đối với body rỗng, publisher phát một `DataBuffer` kích thước 0; nếu một component yêu cầu `Flux.empty()` thay thế, phải đảm bảo hợp đồng xử lý body rỗng vẫn nhất quán. Không nên dùng một cached `DataBuffer` duy nhất trên nhiều request hay nhiều subscription.

### Tại sao không gọi getBody hai lần trên request gốc?

`getBody()` của request gốc không phải API hứa cho phép đọc lại. Nếu filter đã subscribe, rồi controller subscribe lần nữa, có thể thấy body rỗng, lỗi I/O hoặc hành vi phụ thuộc adapter. **Phát lại từ bản sao bytes đã capture**, không subscribe lại raw request.

## 8. Vị trí xác thực và Reactor Context trong WebFlux

Spring Security reactive có `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và `ReactiveSecurityContextHolder`. Không dùng `SecurityContextHolder` thread-local của mô hình Servlet để truyền principal qua một reactive pipeline, vì tác vụ có thể chuyển thread.

Ví dụ kiến trúc một custom `WebFilter` (đơn giản hóa):

~~~java
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

record CaptureOutcome(
    byte[] body,
    boolean tooLarge
) {}

record AuthDecision(
    Authentication authentication,
    HttpStatus failureStatus
) {
    static AuthDecision accepted(Authentication value) {
        return new AuthDecision(value, null);
    }
    static AuthDecision rejected(HttpStatus status) {
        return new AuthDecision(null, status);
    }
}

interface ReactiveHmacVerifier {
    // Đọc registry/secret non-blocking, dựng canonical request
    // từ dữ liệu HTTP và raw body, kiểm tra HMAC + timestamp/nonce.
    Mono<Authentication> authenticate(
        ServerWebExchange exchange, byte[] rawBody);
}

interface SafeErrorResponder {
    // Response JSON đã kiểm soát thông tin, không lộ key/secret.
    Mono<Void> reject(ServerWebExchange exchange, HttpStatus status);
}

public final class HmacBodyWebFilter implements WebFilter {
    private static final int MAX_BODY_BYTES = 1024 * 1024;

    private final ReactiveHmacVerifier verifier;
    private final SafeErrorResponder responder;

    public HmacBodyWebFilter(
            ReactiveHmacVerifier verifier,
            SafeErrorResponder responder) {
        this.verifier = verifier;
        this.responder = responder;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        return BoundedBodyCapture
            .read(exchange.getRequest().getBody(), MAX_BODY_BYTES)
            .map(bytes -> new CaptureOutcome(bytes, false))
            .onErrorResume(DataBufferLimitException.class,
                error -> Mono.just(new CaptureOutcome(null, true)))
            .flatMap(captured -> {
                if (captured.tooLarge()) {
                    return responder.reject(
                        exchange, HttpStatus.PAYLOAD_TOO_LARGE);
                }
                byte[] rawBody = captured.body();
                ServerHttpRequest replay =
                    new HmacReplayableRequest(
                        exchange.getRequest(),
                        rawBody,
                        exchange.getResponse().bufferFactory());

                ServerWebExchange mutated =
                    exchange.mutate().request(replay).build();

                // Xử lý lỗi của CHÍNH bước xác thực tại đây;
                // không bắt nhầm lỗi do controller ném thành 401.
                Mono<AuthDecision> decision =
                    verifier.authenticate(mutated, rawBody)
                        .map(AuthDecision::accepted)
                        .onErrorResume(AuthenticationException.class,
                            error -> Mono.just(AuthDecision.rejected(
                                HttpStatus.UNAUTHORIZED)));

                return decision.flatMap(result -> {
                    if (result.failureStatus() != null) {
                        return responder.reject(
                            exchange, result.failureStatus());
                    }

                    Authentication auth = result.authentication();
                    if (auth == null || !auth.isAuthenticated()) {
                        return responder.reject(
                            exchange, HttpStatus.UNAUTHORIZED);
                    }

                    // Context phải nằm trong reactive subscription.
                    return chain.filter(mutated)
                        .contextWrite(
                            ReactiveSecurityContextHolder
                                .withAuthentication(auth));
                });
            });
    }
}
~~~

**Mã này là khung kiến trúc có điều kiện áp dụng**, không phải cấu hình production hoàn chỉnh: cần giới hạn route nào được xác thực bằng filter này, cách tạo canonical URI/header, cách ghi response khi đã committed và cách phân loại lỗi phụ trợ. Lỗi registry/secret manager/replay store **không được biến thành 2xx**; một loại lỗi phụ trợ riêng có thể được chuyển thành 503 bởi bước verifier/responder theo chính sách. Trong mẫu, `DataBufferLimitException` được chuyển thành `CaptureOutcome` ngay trong bước capture trước khi gọi `chain.filter`, nên lỗi từ handler phía sau không bị nhầm thành lỗi body quá lớn của HMAC filter. Những lỗi publisher khác phải được xử lý fail closed, không được coi như body rỗng.

**Giới hạn ví dụ:** `rawBody` tồn tại trong memory tới khi nhánh xử lý không còn tham chiếu. Nếu có nhiều request đồng thời hoặc downstream chậm, footprint có thể cao dù từng request dưới 1 MiB. Filter không hỗ trợ body lớn hoặc streaming không giới hạn.

### Gắn filter trong SecurityWebFilterChain

Với WebFlux, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, **không dùng `HttpSecurity` của Spring MVC**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
class HmacWebFluxSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain hmacChain(
            ServerHttpSecurity http,
            HmacBodyWebFilter hmacFilter) {

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/hmac/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .addFilterAt(
                hmacFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }
}
~~~

Vì `HmacBodyWebFilter` được chèn vào authentication stage, phải kiểm tra **thứ tự filter thực tế** và các handler dành cho authentication/authorization. Nếu WebFilter đồng thời được đăng ký global ngoài `SecurityWebFilterChain`, nó có thể chạy **hai lần**, phát hiện nonce giả là replay. Endpoint khác cần chain phù hợp, có order/matcher rõ ràng. Việc tắt CSRF trong ví dụ chỉ hợp lý cho API máy–máy stateless, **không** dùng cookie/session của trình duyệt để xác thực.

## 9. Reactive HMAC verification: không được block event loop

Sau khi có body bytes, bộ xác thực cần:

1. Tra **đúng key ID** trong credential registry; lấy principal/owner tenant và trạng thái client/key.
2. Lấy secret từ secret manager bằng API bất đồng bộ nếu có; không gọi JDBC đồng bộ, SDK vault blocking hoặc `block()` trên event-loop.
3. Xây canonical request theo hợp đồng: method, raw URI/query, signed header, timestamp, nonce, body SHA-256.
4. Tính HMAC-SHA256 với secret của key ID đã chọn; so sánh chữ ký byte bằng thao tác an toàn về timing.
5. Kiểm tra timestamp bằng đồng hồ server và **đăng ký nonce bằng thao tác nguyên tử** trong kho dùng chung giữa các verifier, sau khi HMAC đúng.
6. Đặt `Authentication` đã xác thực vào Reactor Context, rồi mới chạy authorization.

Phân biệt loại việc:

| Công việc | Cách tổ chức |
| --- | --- |
| HMAC-SHA256 trên body nhỏ đã buffer | Có thể xử lý CPU cục bộ trong giai đoạn xác thực, với giới hạn byte và tải |
| Tra secret qua client non-blocking | Dùng `Mono` từ API bất đồng bộ |
| Thư viện credential/vault chỉ có blocking API | Cô lập bằng scheduler phù hợp như `boundedElastic` với giới hạn và timeout; tốt hơn là dùng driver reactive |
| `Thread.sleep`, `Mono.block()`, `Future.get()` trên event-loop | **Không dùng** |
| Kiểm tra nonce trong Redis/DB | Dùng thao tác atomic insert-if-absent, client không blocking |
| CPU hashing body nhiều MiB cho hàng nghìn request | Đặt body/concurrency budget và đánh giá offload khi cần |

Không dùng `.subscribe()` thủ công trong `WebFilter` để “chạy xác thực nền”, vì filter có thể trả về trước khi xác thực hoàn tất. Mọi công việc bắt buộc phải nằm trong **cùng reactive chain** được trả về, để lỗi và cancellation được quản lý nhất quán.

### Phân biệt xác thực và phân quyền

Nếu client A ký request chọn `tenant-b` bằng secret hợp lệ của A, HMAC có thể đúng nhưng **không chứng minh được quyền của A ở B**. Tính toàn vẹn tenant claim phải được ràng buộc vào canonical request, sau đó kiểm tra owner tenant/delegated grant, action và resource. Effective tenant dùng truy vấn dữ liệu phải đến từ context đã xác thực và phân quyền, không lấy trực tiếp từ `X-Tenant-Id` hay body.

## 10. Canonical request và body raw bytes

Ví dụ:

~~~http
POST /api/hmac/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 5bd283aa-4208-4b12-8c70-b3ac54f84bc0
X-Signature: <base64-hmac-sha256>

{"orderId":"o-301","amount":180000}
~~~

Đây là request minh họa, signature không phải test vector đã tính. Một canonical contract V1 có thể dùng các dòng UTF-8:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/orders?currency=VND
application/json
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
5bd283aa-4208-4b12-8c70-b3ac54f84bc0
<sha256-hex-cua-raw-body-bytes>
~~~

Dòng hash cuối là placeholder. Hợp đồng thực tế phải định nghĩa **các bytes**: `LF` hay `CRLF`, có newline cuối không, query string nào được ký, thứ tự param, xử lý header trùng, percent-encoding, charset, body empty và các transformation trước điểm verify.

### Những thay đổi không được tự động hợp nhất

| Biến thể | Hệ quả nếu ký raw body bytes |
| --- | --- |
| `{"a":1,"b":2}` so với `{"b":2,"a":1}` | Body digest khác |
| Body JSON thêm khoảng trắng | Digest khác |
| Body rỗng so với `{}` | Digest khác |
| `LF` so với `CRLF` | Digest khác |
| Body bị gateway giải nén hoặc đổi charset | Digest có thể khác |
| `X-Tenant-Id` thay sau khi ký | Chữ ký phải khác nếu tenant nằm trong hợp đồng ký |
| URI được proxy rewrite | Canonical target phải lấy theo trust contract của gateway |

Hash body:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class BodyHash {
    static String sha256LowerHex(byte[] rawBody) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(rawBody));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                "SHA-256 not available", e);
        }
    }
}
~~~

Digest SHA-256 của **body rỗng** là `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. Nếu hợp đồng có trường body hash, không bỏ trường đó khi body empty.

### Proxy/gateway không được làm thay đổi thông tin đã ký ngoài hợp đồng

Với WebFlux `ServerHttpRequest`, `getURI().getRawPath()`/`getRawQuery()` có thể hữu ích để xây target, nhưng chỉ đúng **khi ứng dụng thực sự thấy URI mà hợp đồng yêu cầu**. Ingress có thể rewrite path trước khi request tới JVM. Không tin `X-Original-URI` hoặc `X-Forwarded-Host` từ người gọi Internet; gateway cần xóa header tự khai và thiết lập metadata qua kết nối tin cậy.

## 11. Khi body quá lớn: có thực sự xác thực streaming được không?

Nếu body vài GiB, **gom toàn bộ vào RAM để verify trước khi cho controller xử lý** là không phù hợp. Có thể muốn tính HMAC-SHA256 incrementally:

~~~text
for each DataBuffer:
    update SHA-256(body bytes)
onComplete:
    finalize digest
    build canonical request
    verify HMAC
~~~

Cách này **giảm bộ nhớ cho việc tính digest**, nhưng không giải quyết hai vấn đề khác:

1. Nếu sau đó controller vẫn cần chính body gốc, dữ liệu phải được **lưu tạm có giới hạn hoặc truyền lại từ nguồn đáng tin**; không thể dựa vào việc subscribe lại HTTP request.
2. Nếu controller được phép bắt đầu **ghi database, gửi email hoặc chuyển tiền khi chưa nhận hết body/chưa verify HMAC**, dữ liệu có thể đã tạo side effect trước khi chứng minh tính toàn vẹn.

Vì vậy, có ba kiểu kiến trúc:

| Phương án | Khi phù hợp | Đánh đổi |
| --- | --- | --- |
| Buffer body có giới hạn trước khi verify | JSON nhỏ, machine-to-machine API | Dễ kiểm tra HMAC, tốn RAM theo concurrency |
| Stream digest vào storage tạm, verify xong mới replay | Upload lớn cần chữ ký toàn request | Cần quota disk, cleanup, encryption/access control và xử lý cancel |
| Giao thức chunk signing / signed manifest đã thiết kế riêng | Dịch vụ streaming dài | Phức tạp hơn, phải ràng buộc thứ tự, offset, tổng độ dài, end-of-stream và chống replay |

**Chunk signing không phải** chỉ là dùng `Flux<DataBuffer>` và ký mỗi buffer tự phát. HTTP transport có thể chia chunk khác nhau giữa proxy/client; cần một **giao thức ký ở tầng ứng dụng** có version, framing, chain/hash và kiểm thử an toàn độc lập.

Nếu endpoint không cần upload lớn, cách an toàn hơn là **từ chối 413** thay vì cố hỗ trợ một chế độ streaming thiếu hợp đồng bảo mật.

## 12. Timeout, cancellation và client ngắt kết nối

Một request có thể bị hủy khi:

- Client đóng TCP connection giữa chừng;
- Gateway timeout hoặc load balancer cắt kết nối;
- Authentication dependency timeout;
- Controller chủ động cancel subscription;
- Server shutdown hoặc chính sách resource limit từ chối request.

Khi cancellation xảy ra trong lúc `DataBufferUtils.join` đang thu dữ liệu, operator quản lý release các buffer đã tích lũy theo contract. Tuy nhiên, bất kỳ buffer nào **code tự giữ riêng** phải được cleanup bằng cơ chế phù hợp. Không chỉ đặt `doOnComplete` và tin mọi request đều hoàn thành; `cancel` không phải `complete`.

Với code tự tạo buffer hoặc temporary files:

- Dùng `doFinally(signalType -> ...)` hoặc `usingWhen` để thực hiện cleanup khi success, error **và** cancel.
- Không giữ pooled `DataBuffer` trong cache/field toàn cục rồi release ở một nhánh ít gặp.
- Nếu dùng `DataBufferUtils.write` vào file, cần quản lý ownership và release rõ ràng theo API của operator, đồng thời xóa file tạm theo vòng đời request.
- Đặt **read timeout**, dependency timeout, concurrency limit và quota disk; tránh slowloris giữ một request mãi mà không vượt byte limit.
- Cân nhắc metric cho `CANCEL`, `ERROR`, body-size rejection và buffer/resource cleanup.

### Ranh giới timeout và retry

Nếu body được tiêu thụ rồi việc xác thực HMAC timeout, **không** cho downstream tiếp tục với principal “mặc định”. Nếu gateway retry cùng request với cùng nonce sau khi một verifier đã ghi nonce, request mới có thể bị từ chối replay theo thiết kế; cần phân biệt **retry mạng**, **replay protection** và **idempotency** nghiệp vụ.

## 13. Key rotation và nhiều client trên pipeline reactive

Trong một hệ thống có nhiều client/tenant, việc xử lý body chính xác mới chỉ là một nửa công việc.

| Thành phần | Điều kiện an toàn |
| --- | --- |
| Key lookup | Tra đúng `X-Key-Id`; mỗi key version gắn một secret |
| Key rotation | K3/K4 có thể cùng ACTIVE theo cửa sổ; không thử fallback key khi chữ ký sai |
| Revocation | Key REVOKED hoặc hết hạn phải bị từ chối dù HMAC vẫn khớp |
| Client disabled | Chặn mọi credential của client theo chính sách |
| Tenant disabled | Chặn request tới tenant theo policy, kể cả khi secret còn hiệu lực |
| Tenant claim | Ký tenant target và kiểm tra grant; không chỉ tin `X-Tenant-Id` |
| Nonce store | Ghi nguyên tử xuyên node, TTL bao phủ cửa sổ timestamp |
| Secret store | Không đưa secret vào Reactor Context, log hay `Authentication.getCredentials()` sau xác thực |

Nếu registry lưu trạng thái trong cache, event bất đồng bộ + TTL **không tự bảo đảm** thu hồi tức thì. Để cam kết “mọi request bắt đầu sau commit REVOKED đều bị từ chối”, verifier phải kiểm tra trạng thái đủ mới hoặc fail closed khi không chứng minh được. Điều này áp dụng cho WebFlux như với Spring MVC, dù giao thức xử lý I/O khác nhau.

**Phân quyền không nằm trong body capture.** Nó phải dựa trên principal/tenant/action/resource sau khi xác thực; một request HMAC đúng không được phép truy cập dữ liệu client/tenant khác chỉ vì cùng gateway.

## 14. Ma trận kiểm thử request body và backpressure

| Test ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| BP-01 | Body JSON nhỏ ở một `DataBuffer`, HMAC đúng | Handler nhận đúng bytes, response theo quyền |
| BP-02 | Cùng body bị chia thành nhiều `DataBuffer` | Digest/HMAC không phụ thuộc kích thước chunk |
| BP-03 | Body rỗng | SHA-256 rỗng được dùng theo hợp đồng |
| BP-04 | Body `{}` thay cho rỗng | Digest khác, signature cũ không tái sử dụng |
| BP-05 | Thay một byte sau khi ký | HMAC sai, handler không chạy |
| BP-06 | Body đúng bằng `maxBodyBytes` | Được xét tiếp, nếu credential/signature hợp lệ |
| BP-07 | Body vượt giới hạn một byte | `DataBufferLimitException` → 413, không xử lý nghiệp vụ |
| BP-08 | `Content-Length` nhỏ hơn bytes thực tế | Giới hạn áp dụng trên bytes thực sự |
| BP-09 | Không có Content-Length/chunked body | Vẫn áp byte limit và timeout |
| BP-10 | 1.000 request body gần giới hạn | Có concurrency/admission limit, không OOM |
| BP-11 | Client gửi chậm dưới giới hạn bytes | Timeout chặn kết nối chiếm tài nguyên mãi |
| BP-12 | Client cancel giữa các buffer | Không leak pooled memory/temp files |
| BP-13 | HMAC sai | Không ghi nonce, không gọi controller |
| BP-14 | Nonce trùng giữa hai instance | Chỉ lần đầu được chấp nhận |
| BP-15 | Registry/secret manager/replay store mất kết nối | Fail closed, không `block()` event loop |
| BP-16 | Key đã REVOKED | Từ chối dù raw body/HMAC khớp |
| BP-17 | Client A ký target tenant B không có grant | Từ chối authorization, không lộ data B |
| BP-18 | Gateway rewrite URI khác hợp đồng | Phát hiện signature mismatch |
| BP-19 | Client gửi header duplicate hoặc header spoofing | Parser từ chối, không tin `X-Original-URI` |
| BP-20 | Handler subscribe `getBody()` sau filter | Nhận đúng toàn bộ body đã verify |
| BP-21 | Handler/codec subscribe hơn một lần có kiểm soát | Không phát lại cùng pooled buffer đã release |
| BP-22 | `WebFilter` bị đăng ký hai lần | Test phát hiện, không tạo replay giả |
| BP-23 | Operator upstream phát lỗi trước onComplete | Release buffer, không xác thực một body thiếu |
| BP-24 | Upload multipart/streaming lớn | Trả 413 hoặc đi đúng kiến trúc upload riêng |
| BP-25 | Request B sau request A ở luồng khác | Reactor Context không rò principal/tenant |

### Unit test với StepVerifier

Ví dụ kiểm tra việc ghép chunk và giới hạn body. Test dùng `spring-core`, Reactor Test, JUnit Jupiter và `DefaultDataBufferFactory`:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class BoundedBodyCaptureTest {
    private final DefaultDataBufferFactory buffers =
        new DefaultDataBufferFactory();

    @Test
    void mergesChunksWithoutChangingBytes() {
        Flux<DataBuffer> chunks = Flux.just(
            buffers.wrap("abc".getBytes(StandardCharsets.UTF_8)),
            buffers.wrap("123".getBytes(StandardCharsets.UTF_8))
        );

        StepVerifier.create(BoundedBodyCapture.read(chunks, 6))
            .assertNext(bytes -> assertArrayEquals(
                "abc123".getBytes(StandardCharsets.UTF_8), bytes))
            .verifyComplete();
    }

    @Test
    void refusesBodyBeyondLimit() {
        Flux<DataBuffer> chunks = Flux.just(
            buffers.wrap("abc".getBytes(StandardCharsets.UTF_8)),
            buffers.wrap("1234".getBytes(StandardCharsets.UTF_8))
        );

        StepVerifier.create(BoundedBodyCapture.read(chunks, 6))
            .expectError(DataBufferLimitException.class)
            .verify();
    }

    @Test
    void emptyBodyIsAnEmptyByteArray() {
        StepVerifier.create(
                BoundedBodyCapture.read(Flux.empty(), 1024))
            .assertNext(bytes ->
                assertArrayEquals(new byte[0], bytes))
            .verifyComplete();
    }
}
~~~

Đây là **unit test** cho logic capture, chưa chứng minh request đi qua gateway, HMAC, nonce store hoặc controller. Các `DataBuffer` ở đây dùng factory mặc định để kiểm tra dữ liệu; với Netty pooled buffer, cần thêm test/leak detection trong môi trường tích hợp phù hợp.

## 15. Kiểm thử tích hợp bằng WebTestClient và TestPublisher

Một `WebTestClient` test nên chạy qua `SecurityWebFilterChain` thật, với signer HMAC **độc lập** với verifier. Không mock manager trả `authenticated=true` cho mọi request rồi kết luận đã kiểm thử bảo mật.

Ví dụ khung test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HmacWebFluxIntegrationTest {
    @Autowired WebTestClient client;

    @Autowired IndependentHmacTestSigner signer; // Fixture dự án tự tạo.

    @Test
    void bodyIsAvailableToHandlerAfterHmacVerification() {
        String body = "{\"orderId\":\"o-301\",\"amount\":180000}";
        String timestamp = "2026-11-28T04:00:00Z";
        String nonce = "case-webflux-001";

        String signature = signer.sign(
            "POST",
            "/api/hmac/orders?currency=VND",
            "application/json",
            "partner-a",
            "partner-a-k4",
            "tenant-a",
            timestamp, nonce, body);

        client.post()
            .uri("/api/hmac/orders?currency=VND")
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Client-Id", "partner-a")
            .header("X-Key-Id", "partner-a-k4")
            .header("X-Tenant-Id", "tenant-a")
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Signature", signature)
            .bodyValue(body)
            .exchange()
            .expectStatus().is2xxSuccessful();

        // Cần assert thêm service/DB nhận đúng body và tenant.
    }
}
~~~

`IndependentHmacTestSigner` là fixture minh họa, không phải API có sẵn. **Phải cố định `Clock` trong test** hoặc tạo timestamp hợp lệ tại lúc chạy; timestamp ví dụ năm 2026 sẽ không còn nằm trong cửa sổ khi chạy về sau. Cần có dữ liệu test credential, secret, nonce store và một handler thật; không dùng secret production.

### Cancellation và backpressure phải được kiểm thử riêng

Có thể dùng `TestPublisher<DataBuffer>` hoặc một publisher có kiểm soát để phát từng chunk, phát `error` hoặc `cancel` trước khi hoàn tất. Kiểm tra:

- Số byte tối đa luôn được thực thi khi upstream chia data thành chunks khác nhau.
- Cancellation chặn downstream và giải phóng pooled buffer.
- Lỗi từ source không bị chuyển nhầm thành “body rỗng và HMAC đúng”.
- Không có `block()` trong xử lý request trên event loop, không `subscribe()` ngoài chain.
- Nếu nhiều request chậm cùng lúc, concurrency limit giới hạn bộ nhớ giữ bởi các mảng `byte[]`.
- Authentication/authorization phân biệt 401/403; 413 không bị đổi thành 500 hoặc HTML ngoài hợp đồng.

Với test Netty thực, có thể bật công cụ phát hiện leak phù hợp trong môi trường test và quan sát direct memory. Việc unit test `StepVerifier` PASS **không tự chứng minh** không có memory leak khi gặp cancel và pooled buffers.

## 16. Những sai lầm dễ mắc khi triển khai

### Lỗi 1 — Dùng `collectList()` không giới hạn để hỗ trợ HMAC

Dù upstream phát theo demand, toàn bộ chunks vẫn tích lũy. Cách sửa là dùng capture giới hạn byte, timeout và concurrency, hoặc kiến trúc upload streaming có storage tạm.

### Lỗi 2 — `block()` chờ secret hoặc nonce trong WebFilter

Event-loop bị giữ và throughput giảm mạnh; trong một số tình huống Reactor chặn cả thao tác blocking. Dùng API non-blocking; nếu không có, offload có kiểm soát với scheduler thích hợp, không coi đó là lý do bỏ timeout.

### Lỗi 3 — Release `DataBuffer` nhưng vẫn phát lại cùng object

Downstream nhận buffer đã bị trả về pool. Copy dữ liệu vào `byte[]` trước khi release joined buffer rồi tạo DataBuffer mới cho từng subscription.

### Lỗi 4 — Dùng `Flux.cache()` trên pooled body

Cache tham chiếu tới buffer có thể đã release hoặc giữ dữ liệu qua nhiều subscription, dẫn đến lỗi hoặc memory leak. Cache bytes **có giới hạn** ở phạm vi request và phát buffer mới.

### Lỗi 5 — Chỉ giới hạn codec `maxInMemorySize`

Custom filter dùng `DataBufferUtils.join` không giới hạn vẫn tích lũy body. Dùng overload có `maxByteCount` cho bước đọc của filter và kiểm thử thực tế.

### Lỗi 6 — Để handler bắt đầu ghi dữ liệu trước khi signature hoàn thành

Nếu digest chỉ tính xong khi stream kết thúc mà controller đã ghi DB trước đó, request giả mạo có thể tạo side effect. Phải verify trước khi chạy nghiệp vụ, hoặc thiết kế giao thức/chế độ staging và commit riêng.

### Lỗi 7 — Nuốt `DataBufferLimitException` và tiếp tục với body thiếu

HMAC có thể được xác minh trên dữ liệu bị cắt trong khi controller nhận dữ liệu khác. Khi vượt giới hạn, phải fail closed, trả 413 và không thực thi nghiệp vụ.

### Lỗi 8 — Reuse nonce store cục bộ từng JVM

Replay tới gateway khác được chấp nhận. Dùng insert-if-absent nguyên tử trên kho chung và TTL đúng.

### Lỗi 9 — Dùng HMAC thành công như quyền toàn cục

Client A sở hữu secret và ký request tenant B. HMAC vẫn có thể đúng, nhưng authorization phải kiểm tra grant và tài nguyên đích.

### Lỗi 10 — Tin `Content-Length` và forwarded headers không được kiểm soát

Header do client khai có thể sai hoặc gateway thay đổi. Áp giới hạn lên bytes thực tế; canonical target/header phải đến từ trust boundary đã được thiết kế và kiểm thử.

## 17. Bài tập tình huống

Một dịch vụ WebFlux đang xác thực HMAC cho `POST /api/hmac/uploads`. Nhóm triển khai viết:

~~~java
Mono<List<DataBuffer>> body =
    exchange.getRequest().getBody().collectList();

return body.flatMap(buffers -> {
    // Nối tất cả chunks, tính SHA-256 rồi verify HMAC.
    // Sau đó chuyển buffers cũ cho controller dùng lại.
    return verifyAndContinue(buffers);
});
~~~

Hệ thống bắt đầu bị tăng direct memory khi khách hàng gửi nhiều request lớn. Một số request bị cancel, một số khác vào controller nhưng lỗi “buffer released”, và khi nonce store ngừng hoạt động thì hệ thống bỏ qua nonce để giữ throughput.

Hãy phân tích:

1. Vì sao `collectList()` có thể gây tăng bộ nhớ dù Reactor có backpressure?
2. Có thể đặt giới hạn bytes bằng API nào thay cho `collectList()`?
3. Joined `DataBuffer` phải được release trong những trường hợp nào? Khi cancel giữa chừng ai chịu trách nhiệm?
4. Vì sao không được phát lại cùng pooled buffer sau khi release? Có thể dùng `ServerHttpRequestDecorator` thế nào?
5. Body lớn hàng GiB có thể vừa verify trước side effect vừa không buffer toàn bộ bằng cách nào?
6. Khi verifier lấy secret từ SDK blocking, cần thay đổi gì?
7. Khi nonce store lỗi, vì sao không được bỏ kiểm tra chống replay?
8. Client A ký request cho tenant B có được cấp quyền B không?
9. Những ca test nào chứng minh ứng dụng không rò rỉ direct memory khi client cancel hoặc upstream error?

**Gợi ý:** dùng `DataBufferUtils.join(body, maxByteCount)` cho body nhỏ, copy ra bytes và release trong `finally`; đặt timeout và concurrency limit. Với upload lớn, dùng staging/storage tạm có giới hạn hoặc giao thức chunk-signing được đặc tả. Không start side effect trước khi HMAC hợp lệ. Dùng reactive secret/nonce client hoặc offload blocking có kiểm soát; fail closed khi không đủ chứng cứ xác thực. Authorization kiểm tra riêng principal–tenant–action–resource.

## 18. Checklist triển khai production

- Xác định hợp đồng canonical request về method, URI, signed headers, body digest, key ID, timestamp và nonce; client/gateway/server tạo cùng bytes.
- Xác định body HMAC là raw bytes ở điểm nào, đặc biệt khi proxy rewrite, nén/giải nén hoặc streaming upload.
- Không dùng `DataBufferUtils.join` không giới hạn, `collectList` hoặc `onBackpressureBuffer` unbounded trên luồng request không tin cậy.
- Đặt `maxBodyBytes` trong filter, giới hạn ingress/codec phù hợp, read timeout, concurrency admission và rate limit.
- Dùng `DataBufferUtils.join(..., maxByteCount)`, copy body bytes và release joined buffer đúng một lần; kiểm tra error/cancel và pooled-memory leak.
- Khi replay body, tạo `DataBuffer` mới theo subscription; không reuse hoặc release quá sớm cùng pooled buffer.
- Không `block()`, `Thread.sleep()` hoặc `subscribe()` thủ công trong đường xác thực trên event loop.
- HMAC được xác minh **trước nghiệp vụ và trước side effect**; body quá lớn phải từ chối 413 hoặc đi qua kiến trúc upload riêng.
- `ReactiveAuthenticationManager`/verifier dùng đúng key ID, trạng thái key/client/tenant đủ mới và secret được bảo vệ.
- Timestamp và nonce chống replay ở kho chung với thao tác nguyên tử; khi kho lỗi phải fail closed.
- Principal đi qua Reactor Context, không phụ thuộc thread-local; authorization xét target tenant, action và resource.
- Error response phân biệt 401, 403, 413 và 503 theo hợp đồng mà không lộ secret, signature hay raw body nhạy cảm.
- Kiểm thử StepVerifier, WebTestClient, pooled buffer leak detection, cancel/error, body nhiều chunks, proxy/gateway và concurrent requests.
- Key rotation, revocation, stale cache và event đến sai thứ tự được kiểm tra đúng mức bảo đảm; không fallback sang secret khác.
- Dashboard theo dõi rejection do body size, replay, signature mismatch, timeout, memory, event-loop saturation và lỗi phụ trợ.

**Backpressure request body trong WebFlux là vấn đề phối hợp luồng dữ liệu, bộ nhớ và ranh giới bảo mật.** Reactor backpressure giúp điều tiết nhu cầu nhận buffer, nhưng không thay thế giới hạn tổng bytes, cleanup khi cancel và giới hạn concurrency. Với HMAC request authentication, cần đọc đúng raw body bytes theo hợp đồng, verify trước side effect, bảo toàn body cho downstream và tiếp tục áp dụng chống replay, key rotation và authorization độc lập.
