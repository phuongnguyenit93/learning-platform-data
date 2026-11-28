# HMAC với WebFlux: xác thực HTTP request trong luồng reactive

## 1. Bài toán và kết quả cần đạt

**Spring WebFlux integration** là phần tích hợp cơ chế xác thực HMAC vào một ứng dụng HTTP chạy theo mô hình reactive. Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, hệ thống xác minh chữ ký được tạo từ **shared secret** và **canonical request** theo hợp đồng giữa client và server; đồng thời chống replay bằng timestamp/nonce, hỗ trợ key rotation, kiểm tra tác động của proxy/gateway và phân biệt xác thực với phân quyền.

Ví dụ: đối tác gọi `POST /api/signed/payments` để tạo giao dịch. Chỉ request có chữ ký HMAC hợp lệ, nằm trong cửa sổ thời gian được cho phép, sử dụng nonce chưa từng được chấp nhận và gắn với client có quyền phù hợp mới được đến handler nghiệp vụ.

Sau bài này, người học có thể:

1. Chỉ ra điểm khác biệt khi triển khai HMAC giữa Spring MVC/Servlet và Spring WebFlux.
2. Lựa chọn đúng `WebFilter`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder` và các handler của Spring Security reactive.
3. Đọc và xác minh body được ký một cách **có giới hạn dung lượng**, không làm mất body của handler phía sau hoặc làm rò `DataBuffer`.
4. Thiết kế verifier bất đồng bộ cho key lookup và nonce store, bảo đảm **atomic replay protection** và cơ chế từ chối khi không thể xác minh an toàn.
5. Kiểm thử chữ ký, phân quyền, concurrency, key rotation và proxy/gateway bằng `WebTestClient`.

> Phạm vi: các đoạn code minh họa cách nối HMAC vào WebFlux/Spring Security 6 trên Java 17+. Công thức canonical, tập header được ký, encoding chữ ký, skew, TTL nonce và chính sách key **phải được chuẩn hóa trong hợp đồng API cụ thể**. “HMAC” tự thân không định nghĩa một giao thức HTTP thống nhất cho mọi ứng dụng.

## 2. HMAC và WebFlux gặp nhau ở đâu?

Trong Servlet, filter nhận `HttpServletRequest`, thường xử lý trên một thread và có thể có các điểm đọc đồng bộ. Trong WebFlux, request được mô tả qua `ServerWebExchange`; body là `Flux<DataBuffer>` và một hoạt động bất đồng bộ trả về `Mono` hoặc `Flux`. Không thể mang nguyên mẫu code Servlet sang rồi gọi `block()` để đọc body hoặc truy vấn Redis trong event-loop.

| Chủ đề | Servlet / Spring MVC | Spring WebFlux |
|---|---|---|
| Bộ lọc web | `Filter`, `OncePerRequestFilter` | `WebFilter`; hoặc `AuthenticationWebFilter` khi dùng Spring Security |
| Đối tượng request | `HttpServletRequest` | `ServerHttpRequest` trong `ServerWebExchange` |
| Đọc body | `ServletInputStream` | `Flux<DataBuffer>` được tiêu thụ qua publisher |
| Ngữ cảnh bảo mật | `SecurityContextHolder` thường dựa trên thread | `ReactiveSecurityContextHolder` qua **Reactor Context** |
| Kho key/nonce | Có thể có API đồng bộ | Nên dùng client reactive, ví dụ reactive Redis |
| Kết thúc response | Ghi response trong filter | Trả một `Mono<Void>` đại diện cho việc ghi response hoàn tất |

Luồng xác thực điển hình:

~~~mermaid
flowchart TD
    A[HTTP request vào WebFlux] --> B{Có thuộc route bắt buộc HMAC?}
    B -- Không --> C[Security chain / route khác]
    B -- Có --> D[Giới hạn và thu body thành byte array]
    D -- Vượt giới hạn --> E[413, dừng luồng]
    D -- Hợp lệ --> F[Đọc key ID, timestamp, nonce, signature]
    F --> G[Tra key và xác minh canonical HMAC]
    G -- Sai / thiếu / hết hạn --> H[401, dừng luồng]
    G -- Hợp lệ --> I[Claim nonce nguyên tử trong kho replay]
    I -- Nonce trùng --> H
    I -- Kho nonce lỗi --> J[503, dừng luồng]
    I -- Claim thành công --> K[Authentication vào Reactor Context]
    K --> L{Có quyền truy cập?}
    L -- Không --> M[403 Forbidden]
    L -- Có --> N[Handler nghiệp vụ nhận lại body]
~~~

**HMAC xác thực** bên gửi có quyền dùng secret tương ứng với key ID; **authorization** kiểm tra principal được xác thực có được dùng tài nguyên/hành động cụ thể hay không. Chữ ký đúng chưa bảo đảm có quyền `payments:write`.

## 3. Quy ước một hợp đồng chữ ký mẫu

Giả sử API thỏa thuận:

~~~http
POST /api/signed/payments?source=partner HTTP/1.1
Content-Type: application/json
X-Key-Id: client-a-2026-11
X-Timestamp: 2026-11-28T03:15:00Z
X-Nonce: 1bfae351-8dc8-4724-8fd3-f931062c20f7
X-Signature: <base64-cua-32-byte-hmac>

{"amount":125000,"currency":"VND"}
~~~

Một canonical string **chỉ để minh họa** có thể gồm các dòng theo thứ tự cố định:

~~~text
HMAC-V1
POST
/api/signed/payments
source=partner
client-a-2026-11
2026-11-28T03:15:00Z
1bfae351-8dc8-4724-8fd3-f931062c20f7
<sha256-hex-cua-body-goc>
~~~

Với hợp đồng này, cả client và server tính:

~~~text
bodyHash = hex(SHA-256(originalBodyBytes))
canonical = joinWithNewline(
    "HMAC-V1", uppercaseMethod, rawPath, rawQueryOrEmpty,
    keyId, timestamp, nonce, bodyHash
)
signature = Base64(HMAC-SHA256(secretBytes, UTF8(canonical)))
~~~

Phần ký được **ràng buộc với key ID, method, path/query, timestamp, nonce và body**. Ví dụ chưa ký `Content-Type`; nếu header này ảnh hưởng đến cách diễn giải request, phải bổ sung vào hợp đồng ký với quy tắc chuẩn hóa cụ thể. Tương tự, không tự ý đổi `rawQuery` thành một map rồi sắp xếp lại nếu client ký nguyên văn raw query. Nếu muốn chuẩn hóa/sắp xếp query, phải định nghĩa rõ percent-encoding, khóa trùng, dấu cách, chữ hoa/chữ thường và thứ tự từ cả hai phía.

Với API đi qua gateway, `rawPath` và `rawQuery` ở điểm kiểm tra có thể khác dữ liệu client thực sự ký. Đường dẫn công khai, prefix bị rewrite, header `Host` và forwarded headers phải được xử lý theo chính sách **trust boundary** rõ ràng; không lấy trực tiếp `X-Forwarded-*` không đáng tin cậy từ Internet để thay phần ký.

### Ràng buộc bảo mật tối thiểu

- Secret riêng theo client/key ID, lưu trong hệ thống quản lý bí mật; chỉ nhận thuật toán và version đã được cho phép, không tin tham số thuật toán do request tự chọn.
- Timestamp theo một format thống nhất (ví dụ ISO-8601 UTC), sai format hoặc lệch ngoài cửa sổ thì từ chối. Cửa sổ ±5 phút chỉ là **ví dụ cấu hình**, không phải mặc định của HMAC.
- Nonce phải duy nhất trong phạm vi đã quy định (thường là client/key) trong suốt khoảng request có thể được xác nhận; thao tác claim nonce cần atomic.
- Signature được decode đúng encoding, giới hạn độ dài và so sánh bằng hàm giảm rò rỉ thông tin thời gian, chẳng hạn `MessageDigest.isEqual` cho hai mảng byte.
- Giao tiếp vẫn phải dùng **HTTPS/TLS**: HMAC không thay thế mã hóa kênh truyền.

## 4. Thiết kế tích hợp với Spring Security reactive

Spring Security cho WebFlux hoạt động với `SecurityWebFilterChain`, trong đó các filter vận hành theo thứ tự `SecurityWebFiltersOrder`. Có hai hướng triển khai:

**Hướng dùng thành phần có sẵn của Spring Security:** cấu hình `AuthenticationWebFilter`, `ServerAuthenticationConverter` và `ReactiveAuthenticationManager`. Converter chuyển request thành token chưa xác thực; manager kiểm tra HMAC; success/failure handlers xử lý kết quả. Đây là hướng phù hợp nếu quá trình chuyển đổi request không làm mất body và việc cung cấp lại body cho handler phía sau đã được thiết kế.

**Hướng filter tùy biến có kiểm soát:** viết `WebFilter` chỉ phục vụ route HMAC, thu body có hạn mức, gọi verifier reactive, khôi phục body bằng `ServerHttpRequestDecorator`, gắn `Authentication` vào Reactor Context và trả response lỗi nếu không hợp lệ. Ví dụ đầy đủ phía dưới dùng hướng này để làm rõ giới hạn của body streaming và thứ tự xử lý.

Khi chọn một hướng, cần xác định rõ trách nhiệm của từng thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| `WebFilter` / `AuthenticationWebFilter` | Kích hoạt kiểm tra trên route yêu cầu HMAC, nối các bước reactive, dừng request không hợp lệ |
| `ReactiveHmacVerifier` | Xây canonical, xác minh key/signature/timestamp/nonce, trả principal đáng tin cậy |
| `ServerAuthenticationEntryPoint` | Phản hồi khi chưa xác thực được, thường 401 |
| `ServerAccessDeniedHandler` | Phản hồi khi đã xác thực nhưng thiếu authority, thường 403 |
| `SecurityWebFilterChain` | Chọn route, sắp thứ tự filter, cấu hình authorization |
| `ReactiveSecurityContextHolder` | Mang authentication theo Reactor Context trong luồng thực thi |

**Không dùng `SecurityContextHolder.getContext()` dựa trên `ThreadLocal` làm nguồn xác thực ở code reactive.** Một request có thể đổi thread khi pipeline chạy, còn Reactor Context đi cùng subscription và được Spring Security đọc ở các bước sau.

## 5. Vấn đề khó nhất: body là Flux<DataBuffer>

Các điểm dễ sai khi tính chữ ký HMAC cho request có body:

1. **Body không phải mảng byte có sẵn.** `exchange.getRequest().getBody()` trả `Flux<DataBuffer>` và có thể chỉ cho tiêu thụ một lần từ kết nối mạng. Nếu filter đọc xong rồi chuyển tiếp nguyên request, controller có thể không còn body để đọc.
2. **Không được thu body vô hạn.** `DataBufferUtils.join(...)` cần giới hạn kích thước để một request lớn không chiếm hết heap/pooled memory. Trường hợp vượt giới hạn nên kết thúc bằng 413 hoặc mã lỗi theo hợp đồng.
3. **Quản lý buffer:** khi đọc từ `DataBuffer` đã gộp, phải giải phóng bằng `DataBufferUtils.release(...)` theo vòng đời dữ liệu. Khi join lỗi/hủy, Spring xử lý các buffer đã tích lũy theo hợp đồng của phương thức.
4. **Replay body cho downstream:** dùng `ServerHttpRequestDecorator` trả một publisher mới cho dữ liệu body đã chụp; tạo `DataBuffer` mới ở mỗi subscription, tránh chia sẻ một buffer có read position đã thay đổi.
5. **Ký đúng byte gốc:** hash trên body bytes, không parse JSON rồi serialize lại (khác thứ tự field, khoảng trắng, escaping hoặc encoding sẽ đổi chữ ký).

Một số hệ thống yêu cầu ký body nhiều GB: thu toàn bộ vào bộ nhớ **không phù hợp**. Khi ấy phải có chiến lược streaming/spooling có giới hạn, xác thực trước khi thực hiện side effect, hoặc hợp đồng ký digest riêng được gửi sẵn với cơ chế ràng buộc đáng tin cậy. Không “tạm bỏ qua” việc ký body vì payload lớn.

## 6. Ví dụ WebFilter HMAC end-to-end

Ví dụ sau dùng Java 17+, Spring WebFlux, Spring Security 6 và Reactor. Bộ verifier được tách riêng để có thể dùng kho key/nonce reactive (mục 7). Những lỗi `AuthenticationException` phải được tạo thành tín hiệu `Mono.error(...)` hoặc được ném khi publisher đang được đăng ký.

### 6.1. Hợp đồng verifier

~~~java
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

public interface ReactiveHmacVerifier {
    // Thành công: Authentication đã authenticated với quyền từ dữ liệu server.
    // Chữ ký/header/timestamp/nonce không hợp lệ: AuthenticationException.
    // Kho key/nonce không khả dụng: AuthenticationServiceException.
    Mono<Authentication> verify(ServerHttpRequest request, byte[] rawBody);
}
~~~

Một utility tạo phản hồi lỗi tối giản, không chứa chi tiết secret/key:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class HmacProblemResponses {
    private HmacProblemResponses() {}

    public static Mono<Void> write(ServerWebExchange exchange, HttpStatus status) {
        var response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.empty();
        }

        String title = switch (status) {
            case UNAUTHORIZED -> "Unauthorized";
            case FORBIDDEN -> "Forbidden";
            case SERVICE_UNAVAILABLE -> "Service Unavailable";
            case PAYLOAD_TOO_LARGE -> "Payload Too Large";
            default -> throw new IllegalArgumentException("Unexpected status");
        };

        byte[] content = ("{\"type\":\"about:blank\",\"title\":\""
                + title + "\",\"status\":" + status.value() + "}")
                .getBytes(StandardCharsets.UTF_8);

        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().setContentLength(content.length);
        if (status == HttpStatus.UNAUTHORIZED) {
            // HMAC là tên scheme được thỏa thuận cho API ví dụ.
            response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, "HMAC realm=\"signed-api\"");
        }
        return response.writeWith(Mono.just(response.bufferFactory().wrap(content)));
    }
}
~~~

Theo HTTP, phản hồi **401** cần có `WWW-Authenticate` với challenge cho tài nguyên. Scheme HMAC ở đây là **quy ước của API ví dụ**, không phải một scheme xác thực chuẩn chung được định nghĩa bởi Spring Security. Phản hồi **403** dành cho principal đã xác thực nhưng không được phép. Không trả chữ ký kỳ vọng, canonical string thực tế hoặc trạng thái key/nonce trong body lỗi.

### 6.2. Thu body, xác thực và cho phép downstream đọc lại

~~~java
import java.util.Arrays;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class HmacWebFilter implements WebFilter {
    private static final int MAX_BODY_BYTES = 1024 * 1024; // Ví dụ: 1 MiB.

    private final ReactiveHmacVerifier verifier;
    private final ServerAuthenticationEntryPoint entryPoint;

    public HmacWebFilter(
            ReactiveHmacVerifier verifier,
            ServerAuthenticationEntryPoint entryPoint) {
        this.verifier = verifier;
        this.entryPoint = entryPoint;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        // join với giới hạn; Mono.empty nếu request không có body.
        Mono<byte[]> captured = DataBufferUtils.join(
                        exchange.getRequest().getBody(), MAX_BODY_BYTES)
                .map(HmacWebFilter::readAndRelease)
                .defaultIfEmpty(new byte[0])
                .onErrorResume(DataBufferLimitException.class, ex ->
                        HmacProblemResponses.write(
                                exchange, HttpStatus.PAYLOAD_TOO_LARGE)
                                .then(Mono.empty()));

        return captured.flatMap(bytes -> verifyAndContinue(exchange, chain, bytes));
    }

    private static byte[] readAndRelease(DataBuffer buffer) {
        try {
            byte[] body = new byte[buffer.readableByteCount()];
            buffer.read(body);
            return body;
        } finally {
            DataBufferUtils.release(buffer);
        }
    }

    private Mono<Void> verifyAndContinue(
            ServerWebExchange exchange, WebFilterChain chain, byte[] bytes) {

        // Mỗi subscriber được cấp DataBuffer mới, còn nội dung luôn là bytes gốc.
        ServerHttpRequest replayableRequest =
                new ServerHttpRequestDecorator(exchange.getRequest()) {
                    @Override
                    public Flux<DataBuffer> getBody() {
                        return Flux.defer(() -> Flux.just(
                                exchange.getResponse().bufferFactory().wrap(
                                        Arrays.copyOf(bytes, bytes.length))));
                    }
                };

        ServerWebExchange replayableExchange = exchange.mutate()
                .request(replayableRequest)
                .build();

        // Catch lỗi CHỈ thuộc giai đoạn xác thực.
        Mono<Authentication> authenticated = Mono.defer(
                        () -> verifier.verify(exchange.getRequest(), bytes))
                .filter(Authentication::isAuthenticated)
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid HMAC request")))
                .onErrorResume(AuthenticationServiceException.class, ex ->
                        HmacProblemResponses.write(
                                exchange, HttpStatus.SERVICE_UNAVAILABLE)
                                .then(Mono.empty()))
                .onErrorResume(AuthenticationException.class, ex ->
                        entryPoint.commence(exchange, ex).then(Mono.empty()));

        // Chỉ request đã xác thực mới được chạy chain tiếp theo.
        // contextWrite gắn principal vào Reactor Context của downstream.
        return authenticated.flatMap(authentication ->
                chain.filter(replayableExchange)
                        .contextWrite(ReactiveSecurityContextHolder
                                .withAuthentication(authentication)));
    }
}
~~~

Giải thích từng điểm thiết kế:

- `DataBufferUtils.join(body, MAX_BODY_BYTES)` thu body nhưng giới hạn tổng số byte; body rỗng được biến thành `byte[0]` để các request không có payload vẫn được xác thực. Khi vượt giới hạn, pipeline gửi 413 và **không gọi tiếp filter chain**.
- `readAndRelease` copy dữ liệu rồi giải phóng buffer đã join. Không giữ `DataBuffer` sau khi release, không truy cập lại vùng nhớ được cấp cho nó.
- `ServerHttpRequestDecorator` phát lại body với một buffer mới mỗi lần được subscribe; controller tiếp tục đọc được payload ban đầu. Hạn mức 1 MiB ở đây chỉ là ví dụ; hệ thống phải chọn theo năng lực và hợp đồng endpoint.
- `Mono.defer(...)` bảo đảm lỗi đồng bộ phát sinh khi gọi verifier cũng trở thành lỗi reactive. Nhánh `AuthenticationServiceException` ở trước nhánh `AuthenticationException` vì đây là subclass cần trả 503 thay vì 401.
- `switchIfEmpty(...)` không cho verifier trả `Mono.empty()` rồi kết thúc request mà không có phản hồi. Thành công phải trả `Authentication` thực sự đã xác thực, được verifier xây dựng từ thông tin có thể tin cậy.
- Hai `onErrorResume` gắn với **publisher xác thực** và nằm **trước** `chain.filter(...)`; chúng không biến lỗi từ controller/filter phân quyền ở phía sau thành 401.
- Không có `block()`, `subscribe()` thủ công hoặc `ThreadLocal`. Framework quản lý subscription và Reactor Context.

Ví dụ thiên về API nhỏ/vừa với body có giới hạn. Nếu cùng route chứa request streaming lâu dài, file upload lớn hoặc multipart phức tạp, cần thiết kế đường xác thực riêng để tránh làm mất ý nghĩa streaming và tránh giữ toàn bộ payload trong heap. Cơ chế forward body cũng phải được kiểm chứng với các filter/web handler khác đang có trong ứng dụng.

## 7. Viết verifier bất đồng bộ: key, chữ ký và replay

Filter ở trên cố ý **không** tự thực hiện cryptography; verifier cần xử lý hợp đồng ký. Mẫu logic:

~~~text
verify(request, rawBody):
    requiredSingleHeaders = keyId, timestamp, nonce, signature
    validate header count, syntax, size, accepted algorithm/version
    validate timestamp with bounded clock skew
    canonical = canonicalV1(method, rawPath, rawQuery,
                            keyId, timestamp, nonce,
                            SHA256(rawBody))

    return keyRepository.findActiveKey(keyId)  // reactive, không block
        .switchIfEmpty(BadCredentials)
        .flatMap(key -> {
            expected = HmacSHA256(key.secret, UTF8(canonical))
            supplied = decodeStrictBase64(signature)
            if !constantTimeEqual(expected, supplied):
                return Mono.error(BadCredentials)

            return nonceStore.claimOnce(key.clientId, key.id, nonce, ttl)
                .flatMap(claimed -> {
                    if !claimed:
                        return Mono.error(BadCredentials)  // replay
                    return Mono.just(
                        authenticatedPrincipal(key.clientId, key.authorities))
                })
        })
~~~

Đây là **pseudocode** để diễn tả các bước; các thao tác lấy key, claim nonce và phân loại lỗi cần hiện thực cụ thể. Nếu code dùng `Mac` trong Java, phải tạo hoặc khởi tạo riêng đối tượng `Mac` cho mỗi thao tác (nó là mutable, không chia sẻ đồng thời mà không đồng bộ hóa). Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256 {
    private HmacSha256() {}

    public static boolean matches(
            byte[] secret, String canonical, byte[] suppliedSignature) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(expected, suppliedSignature);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC algorithm unavailable", e);
        }
    }
}
~~~

Với lỗi encoding/độ dài signature, hãy trả lỗi xác thực trước khi gọi `matches`. Không đưa raw signature hay shared secret vào log. Nếu kho key không phản hồi, coi đó là lỗi **không thể xác minh an toàn**, ánh xạ thành `AuthenticationServiceException` để filter trả 503; không mặc định thông qua.

### Atomic claim nonce với Reactive Redis

Chống replay **không thể** thực hiện an toàn chỉ bằng đoạn mã kiểu “tìm nonce → nếu chưa có thì insert”. Hai request cùng nonce có thể cùng nhìn thấy “chưa có” và đều được xử lý. Với Redis, có thể dùng thao tác tương đương:

~~~text
SET hmac:nonce:<client-or-key-scope>:<hashed-nonce> 1 NX PX <ttl-ms>
~~~

Lệnh này chỉ tạo key nếu chưa tồn tại và đặt thời gian sống **trong cùng một thao tác**. API reactive ví dụ:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public final class RedisNonceStore {
    private final ReactiveStringRedisTemplate redis;

    public RedisNonceStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> claimOnce(
            String scopedNonceKey, Duration ttl) {
        // setIfAbsent(key, value, timeout) tương ứng SET NX + expiry.
        return redis.opsForValue()
                .setIfAbsent(scopedNonceKey, "1", ttl);
    }
}
~~~

Ở code production, `scopedNonceKey` phải được tạo **tại server** từ định danh client/key đáng tin cậy và giá trị nonce đã kiểm soát định dạng; nên băm nonce trước khi ghép khóa để tránh giá trị bất thường hoặc lộ dữ liệu qua log/monitoring. Redis TTL phải bao phủ **toàn bộ khoảng thời gian mà một request đã chấp nhận có thể được gửi lại và vẫn hợp lệ**, kể cả độ lệch đồng hồ, biên thời gian và thời gian xử lý. Nếu dùng cửa sổ chấp nhận đối xứng ±5 phút, TTL chỉ 5 phút tính từ lần đầu nhận có thể chưa đủ; cần tính theo chính sách cụ thể và có biên an toàn.

Đặt claim nonce **sau khi signature đã được xác minh** để tránh request giả dùng nonce tùy ý gây cạn kho hoặc chặn request hợp lệ. Việc claim và xác minh quyền là hai bước khác nhau: nonce được ghi nhận theo chính sách sau khi xác thực chữ ký, kể cả khi principal cuối cùng thiếu authority (403).

Nếu Redis hoặc kho nonce lỗi, đừng mặc định `false` hoặc `true` trong `onErrorReturn(...)`. Cần phát tín hiệu lỗi hạ tầng, quy đổi thành `AuthenticationServiceException`, dừng request và trả 503. Client không được khuyến khích tái sử dụng một nonce đã gửi: retry nên sinh timestamp/nonce/chữ ký mới và dùng **idempotency key** riêng cho thao tác tạo giao dịch để tránh tạo thanh toán hai lần.

### Quản lý key rotation

Mỗi key ID cần metadata từ phía server: client/tenant, trạng thái, thời điểm hiệu lực, quyền hạn và vòng đời revoke. Khi chuyển key, server có thể chấp nhận nhiều key **còn hiệu lực** trong khoảng chuyển tiếp theo chính sách đã ký kết. Không thử tuần tự tất cả secret đến khi chữ ký khớp và không dùng key bị thu hồi chỉ vì key khác chưa đồng bộ. Một shared secret bị lộ cần có quy trình revoke và vô hiệu hóa ngay ở lớp key lookup.

**Lưu ý reactor:** Redis reactive không làm các thao tác cryptography nhỏ trở thành network I/O; tính HMAC SHA-256 trên body đã giới hạn thường có thể thực hiện nhanh trong pipeline. Nếu phải dùng API blocking (database driver cũ, secret manager blocking, thao tác đọc file), phải đổi sang API không blocking hoặc cô lập trên scheduler phù hợp; không gọi blocking I/O trên event-loop của Netty.

## 8. Gắn WebFilter vào SecurityWebFilterChain

Ví dụ cấu hình route `/api/signed/**` yêu cầu HMAC và kiểm tra authority cho endpoint thanh toán:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SignedApiSecurityConfiguration {
    @Bean
    @Order(1)
    SecurityWebFilterChain signedApiChain(
            ServerHttpSecurity http,
            ReactiveHmacVerifier verifier) {

        ServerAuthenticationEntryPoint entryPoint =
                (exchange, failure) -> HmacProblemResponses.write(
                        exchange, HttpStatus.UNAUTHORIZED);
        ServerAccessDeniedHandler deniedHandler =
                (exchange, denied) -> HmacProblemResponses.write(
                        exchange, HttpStatus.FORBIDDEN);

        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/signed/**"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(deniedHandler))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.POST, "/api/signed/payments")
                        .hasAuthority("payments:write")
                        .anyExchange().authenticated())
                .addFilterAt(new HmacWebFilter(verifier, entryPoint),
                        SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

`securityMatcher` áp dụng filter chain này cho các route signed. Các route còn lại cần một hoặc nhiều `SecurityWebFilterChain` khác được cấu hình theo yêu cầu bảo vệ ứng dụng. Nếu có nhiều chain, hãy kiểm tra thứ tự `@Order`, matcher chồng lấn và chính sách mặc định.

Ở ví dụ này, việc tắt CSRF và repository session chỉ phù hợp với API máy-gọi-máy (stateless), **không dựa vào cookie của trình duyệt** để xác thực. Không tự động áp dụng quy tắc này cho ứng dụng WebFlux có browser session hoặc endpoint khác. Nếu dùng CORS, cần quyết định rõ cách xử lý preflight `OPTIONS`; một preflight hợp lệ không thể mang chữ ký HMAC của request POST thực tế theo cách thông thường.

Không gắn `HmacWebFilter` thành một bean `WebFilter` toàn cục **đồng thời** thêm chính instance đó vào security chain, tránh chạy filter hai lần. Dùng bean qua security chain, hoặc cấu hình scope rõ ràng để không chặn nhầm route ngoài `/api/signed/**`.

### Đường đi lỗi 401, 403, 503

| Tình huống | Nơi xử lý | HTTP status |
|---|---|---|
| Thiếu header bắt buộc, sai canonical HMAC, key không hợp lệ | HMAC verifier và entry point | **401** |
| Timestamp hết hạn hoặc nonce được dùng lại | HMAC verifier và entry point | **401** |
| HMAC hợp lệ nhưng principal thiếu `payments:write` | Authorization trong Spring Security và denied handler | **403** |
| Kho key hoặc nonce không sẵn sàng, không thể xác minh | HMAC verifier/filter | **503** |
| Body vượt kích thước cho phép | Filter thu body hoặc lớp HTTP/gateway | **413** |

Trong WebFlux, `ExceptionTranslationWebFilter` xử lý các exception phù hợp trong các thành phần chạy phía sau nó. Với filter HMAC ở vị trí authentication, đừng giả định mọi exception do chính filter phát ra sẽ được thành phần nằm phía sau tự bắt; ví dụ đã chủ động chuyển lỗi xác thực thành response bằng entry point. Thao tác ghi response là một publisher được **trả về** để framework subscribe, không gọi `subscribe()` thủ công.

## 9. Kiểm thử bằng WebTestClient

`WebTestClient` cho phép kiểm tra response WebFlux và luồng security. Một test dùng mock verifier để cô lập hành vi của HMAC filter:

~~~java
// Ví dụ trích từ test có @MockBean/@MockitoBean hoặc mock injection phù hợp.
when(verifier.verify(any(), any(byte[].class)))
        .thenReturn(Mono.error(new BadCredentialsException("Bad MAC")));

webTestClient.post()
        .uri("/api/signed/payments")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"amount\":125000}")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE, "HMAC realm=\"signed-api\"");

verifyNoInteractions(paymentService);
~~~

Muốn chứng minh body được khôi phục, hãy mock verifier trả authentication đã xác thực, cho handler đọc `@RequestBody` và kiểm tra payload thực tế nhận đủ các byte/field như ban đầu. Có thể dùng một endpoint thử nghiệm trả về hash của body để đối chiếu với hash do client ký.

Các test cần thiết:

| Trường hợp | Kỳ vọng |
|---|---|
| Request không có body nhưng có chữ ký hợp lệ của body rỗng | Verifier vẫn chạy; không bỏ qua do `Mono.empty()` |
| Thiếu bất kỳ header ký bắt buộc | 401, handler không được gọi |
| Thay một byte body hoặc raw query sau khi ký | 401, không có side effect |
| Timestamp quá cũ hoặc quá xa tương lai | 401 |
| Hai request dùng cùng key ID + nonce hợp lệ và gửi đồng thời | Atomic nonce store chỉ cho tối đa một request qua |
| Key còn hiệu lực trong thời gian rotation | Chấp nhận theo chính sách |
| Key đã revoke hoặc hết hiệu lực | 401 |
| Redis nonce/key lookup gián đoạn | 503, request không đi đến nghiệp vụ |
| Chữ ký đúng, thiếu quyền tạo thanh toán | 403 từ authorization |
| Đổi byte body, không đổi chữ ký | 401, kể cả JSON vẫn parse thành object giống nhau |
| Body vượt 1 MiB (giới hạn ví dụ) | 413, không tăng memory vô hạn |
| Body hợp lệ được đọc ở handler sau filter | Dữ liệu không bị mất, không bị đọc rỗng |
| Proxy thay prefix/path/host/header được ký | Kết quả theo canonical contract client/server; không có fallback bỏ qua chữ ký |
| Gửi request vào route không thuộc `/api/signed/**` | Không bị HMAC filter của chain này xử lý |

Ở test tích hợp, đừng chỉ mock verifier: cần test vector canonical dùng chung client/server, mock clock cố định, Redis thực hoặc test container để chứng minh atomic claim, và đường request qua proxy/gateway gần production. Kiểm thử cancel/error trong lúc đọc body giúp phát hiện rò pooled buffer, thao tác ghi response hai lần và các lỗi flow-control.

## 10. Quan sát hệ thống và các lỗi phổ biến

**Tránh blocking event-loop.** Không dùng `block()`, `Thread.sleep()`, JDBC/Redis blocking trực tiếp trên event-loop. Nếu một dependency chưa có API reactive, cần giải pháp chuyển đổi có kiểm soát và đánh giá tải. HMAC signing thuần CPU nhỏ khác với truy vấn kho khóa/nonce qua mạng.

**Không đọc body hai lần từ network stream.** Một lần đọc để ký và một lần đọc ở controller có thể thất bại nếu không dùng request decorator/caching. Đừng nghĩ `ServerHttpRequest.getBody()` luôn là nguồn có thể subscribe tùy ý.

**Không ghi đè body đã ký.** Một filter decompress, parse/serialize JSON, đổi encoding hoặc sửa nội dung có thể làm mismatch. Chỉ hash cùng byte sequence được hai phía thống nhất, rồi chuyển tiếp dữ liệu đúng hợp đồng. Với `Content-Encoding` như gzip, phải định nghĩa rõ chữ ký áp dụng trước hay sau decode.

**Không bỏ qua key/nonce store khi lỗi.** 503 giúp client và vận hành phân biệt lỗi hạ tầng với lỗi ký request. Tự cho qua sẽ làm mất bảo đảm chống replay/xác thực.

**Không gộp authorization vào chữ ký.** HMAC xác nhận principal có khả năng dùng secret; các quyết định như `payments:write`, ownership hoặc tenant isolation phải được tính từ dữ liệu tin cậy của server.

**Không ghi bí mật vào log.** Log có thể chứa correlation ID, route dạng template, key ID đã làm mờ, nhóm lỗi và độ trễ xác minh. Tránh log raw body, canonical string, shared secret, full signature và nonce nguyên văn. Theo dõi riêng số lần 401, 403, 413, 503, replay, clock skew và độ trễ Redis.

**Không coi WebFlux đồng nghĩa mọi thao tác đều streaming.** Cách gộp body ở mục 6 phù hợp khi giới hạn rõ ràng; với upload lớn hoặc luồng vô hạn cần kiến trúc chữ ký khác, được mô tả trong hợp đồng và kiểm tra tài nguyên.

## 11. Checklist tự đánh giá

- [ ] Có hợp đồng canonical request phiên bản hóa: method, raw path/query, danh sách header ký, hash byte body, timestamp, nonce, encoding và HMAC algorithm.
- [ ] Route cần ký được giới hạn bằng security matcher; request thiếu hẳn HMAC trên route đó vẫn bị từ chối.
- [ ] Đọc `Flux<DataBuffer>` một lần có giới hạn; release đúng buffer; request decorator cho handler nhận lại body.
- [ ] Verifier/key lookup/nonce store vận hành reactive và không gọi `block()` trên event-loop.
- [ ] Tính HMAC bằng secret đúng key và so sánh chữ ký theo byte; input sai bị từ chối.
- [ ] Nonce claim nguyên tử, TTL bao phủ replay window; store lỗi thì fail closed.
- [ ] Authentication được đưa vào `ReactiveSecurityContextHolder`; authority dựa trên server; phân quyền được kiểm tra độc lập.
- [ ] 401, 403, 413 và 503 phản ánh đúng nguyên nhân; không trả dữ liệu nhạy cảm cho client.
- [ ] Tích hợp key rotation và proxy/gateway có test vector nhất quán.
- [ ] Dùng `WebTestClient` kiểm chứng không có side effect khi từ chối, body còn nguyên và các request đồng thời không vượt qua nonce guard.

**Kết luận:** Tích hợp HMAC với WebFlux cần cùng lúc bảo toàn quy tắc cryptography của canonical request và tuân thủ vòng đời reactive của `Flux<DataBuffer>`, `Mono` và Reactor Context. Khi body được xử lý an toàn, verifier không blocking, replay protection nguyên tử và filter dừng đúng đường lỗi, request chỉ đến nghiệp vụ sau khi đã được xác thực; phân quyền vẫn là bước độc lập.
