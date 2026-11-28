# ServerWebExchange

**ServerWebExchange** là điểm truy cập trung tâm tới **HTTP request, HTTP response và các dữ liệu gắn với một lần trao đổi HTTP** trong Spring WebFlux. Với API bảo vệ bằng **HMAC request authentication**, việc hiểu đúng `ServerWebExchange` quyết định liệu verifier có ký lại đúng method, URI, signed headers và raw body bytes **mà client thực sự gửi** hay không, và liệu request có tiếp tục tới handler theo đúng mô hình **non-blocking/reactive**.

Bài thuộc chương **Spring WebFlux integration** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request gồm phương thức, URI, header hoặc body theo hợp đồng ký; người học thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

> **Nguyên tắc cốt lõi:** `ServerWebExchange` cung cấp **request/response đang được xử lý**, chứ không tự chứng minh một HTTP header hay tenant ID đáng tin. HMAC verifier phải dựng canonical request từ **trusted representation của HTTP request**, tra đúng secret theo key ID, so toàn bộ MAC, kiểm timestamp/nonce rồi mới tạo authenticated identity. Khi đọc `Flux<DataBuffer>` của request body, không được chặn event-loop, không tự `subscribe()`, không để consumer phía sau nhận body rỗng hoặc bytes khác với bytes đã ký.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trình bày vai trò của `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse` và `WebFilterChain`.
2. Phân biệt WebFlux reactive HTTP stack với Servlet `HttpServletRequest`/`OncePerRequestFilter`.
3. Đọc method, URI/raw path/query, headers, cookies và HTTP request body đúng từ exchange.
4. Giải thích cách `getAttributes()`, `getPrincipal()`, `getSession()` và `mutate()` hoạt động trong request pipeline.
5. Xác định **trusted signing boundary** khi HMAC nằm sau reverse proxy/gateway.
6. Thiết kế request-body buffering/decorating trong WebFlux với giới hạn kích thước, `DataBufferUtils` và body replay.
7. Dùng `Mono.defer`, `flatMap`, `Flux.defer` và `ServerHttpRequestDecorator` mà không phá reactive backpressure/lifecycle.
8. Chọn `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ServerAuthenticationConverter` và `ReactiveAuthenticationManager` phù hợp.
9. Ràng buộc key ID, signed headers, timestamp, nonce, audience và body digest vào canonical request.
10. Kiểm thử các trường hợp body bị đọc hai lần, header trùng, key revoke, replay store outage, tenant authorization và gateway rewrite.

## 2. ServerWebExchange là gì?

Trong Spring WebFlux, một HTTP request đi qua pipeline asynchronous/reactive:

~~~mermaid
flowchart TD
    C[HMAC HTTP client] --> G[Reverse proxy or gateway]
    G --> R[Reactive server adapter]
    R --> E[ServerWebExchange]
    E --> F[WebFilter chain]
    F --> S[Spring Security SecurityWebFilterChain]
    S --> A[HMAC authentication]
    A --> Z[Authorization]
    Z --> H[WebFlux HandlerMapping and handler]
    H --> B[Business service]
    B --> P[ServerHttpResponse]
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `ServerWebExchange` | Đóng gói request/response và metadata của HTTP exchange hiện tại |
| `ServerHttpRequest` | Method, URI, path, query, headers, cookies, body `Flux<DataBuffer>` |
| `ServerHttpResponse` | Status, headers, cookies, response buffers, commit/write API |
| `WebFilter` | Middleware reactive nhận exchange và chain, trả `Mono<Void>` |
| `WebFilterChain` | Gọi filter/handler kế tiếp qua `filter(exchange)` |
| `SecurityWebFilterChain` | Spring Security reactive filters cho request match |
| `AuthenticationWebFilter` | Authentication adapter reactive theo matcher và converter |
| `ServerAuthenticationConverter` | Từ exchange tạo authentication request chưa được xác minh |
| `ReactiveAuthenticationManager` | Xác minh credentials và tạo authenticated result |
| `ReactiveSecurityContextHolder` | Bối cảnh security theo Reactor Context, không phải ThreadLocal mặc định |
| `DataBuffer` | Đơn vị bytes trong body stream; có ownership/release semantics |

**Lưu ý:** `ServerWebExchange` bản thân không phải authentication mechanism. Nó chỉ cho các lớp truy cập representations của HTTP request/response. Một caller có thể gửi `X-Key-Id` hoặc `X-Tenant-Id` giả; chúng vẫn xuất hiện trong `exchange.getRequest().getHeaders()` dù chưa đáng tin.

### 2.1. Servlet và WebFlux không dùng chung filter API

| Spring MVC/Servlet | Spring WebFlux/reactive |
| --- | --- |
| `HttpServletRequest` | `ServerHttpRequest` |
| `HttpServletResponse` | `ServerHttpResponse` |
| `FilterChain#doFilter` | `WebFilterChain#filter` |
| `OncePerRequestFilter` | `WebFilter` / reactive security filters |
| `InputStream` hoặc `Reader` | `Flux<DataBuffer>` |
| `SecurityContextHolder` thường gắn thread | `ReactiveSecurityContextHolder` dùng Reactor Context |
| Blocking API dễ xuất hiện | Event loop cần non-blocking end-to-end |

Không dùng `OncePerRequestFilter` trong một pure WebFlux runtime để xác thực HMAC. Các ví dụ Servlet khác phải được chuyển sang mô hình reactive/ServerWebExchange thay vì sao chép nguyên phương thức `doFilterInternal`.

## 3. Các khả năng chính của ServerWebExchange

Một `ServerWebExchange` thường cho truy cập:

~~~java
import java.net.URI;
import java.security.Principal;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class ExchangeBasicsV1 {
    public Mono<Void> inspect(ServerWebExchange exchange) {
        var request = exchange.getRequest();
        var response = exchange.getResponse();

        String requestId = request.getId();
        URI uri = request.getURI();
        String method = request.getMethod().name();
        String rawPath = uri.getRawPath();
        String rawQuery = uri.getRawQuery();
        String signature = request.getHeaders()
                .getFirst("X-Signature");

        // Thông tin trên đều chỉ là dữ liệu HTTP chưa xác thực.
        // Không log signature, body hoặc secret trong production.
        exchange.getAttributes().put(
                "hmac.demo.requestId", requestId);

        return exchange.getPrincipal()
                .cast(Principal.class)
                .doOnNext(principal -> {
                    // Principal chỉ đáng tin sau authenticated filter
                    // và security context integration phù hợp.
                })
                .then();
    }
}
~~~

Đây là đoạn minh họa truy cập các API. `getPrincipal()` trả `Mono<Principal>`, có thể không phát giá trị khi request chưa xác thực; không tự giả định có principal chỉ vì một header ID tồn tại.

### 3.1. getRequest() — dữ liệu HTTP cần ký

`exchange.getRequest()` cung cấp:

- `getMethod()`: HTTP method (`GET`, `POST`...).
- `getURI()`: URI theo representation mà server adapter thấy.
- `getPath()`: request path được WebFlux biểu diễn qua `RequestPath`; cần cẩn trọng khi dùng decoded/path segments.
- `getHeaders()`: HTTP fields, có thể có nhiều values cùng tên.
- `getQueryParams()`: parsed multi-value parameters, có thể đã decode/normalize.
- `getCookies()`: parsed cookies, thường không dùng làm nguồn HMAC principal.
- `getBody()`: `Flux<DataBuffer>`, không phải một `byte[]` sẵn có.
- `getId()`: request identifier hữu ích cho tracing, **không** dùng làm signed nonce của client.

### 3.2. getResponse() — trạng thái và kết thúc response

`exchange.getResponse()` cho đặt status/headers và trả body reactive. Trong một authentication failure, có thể:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public Mono<Void> unauthorized(ServerWebExchange exchange) {
    var response = exchange.getResponse();
    if (!response.isCommitted()) {
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
    }
    return response.setComplete();
}
~~~

Nếu response đã commit, không thể giả định còn đổi được status/headers. Lỗi reactive trong `Mono` phải được xử lý bằng operator/exception handling đúng chỗ, không gọi `response.setComplete().subscribe()` trong filter rồi tiếp tục chain.

### 3.3. getAttributes() — metadata nội bộ của exchange

~~~java
exchange.getAttributes().put("hmac.v1.signedBoundary", "edge");
Object value = exchange.getAttribute("hmac.v1.signedBoundary");
~~~

Attributes dùng chia sẻ **server-side request metadata** giữa filters/handler. Chúng không tự là authenticated truth: module khác có thể ghi sai, hoặc developer vô tình copy dữ liệu từ client-supplied headers vào attributes rồi xem là trusted. Đặt tên có namespace, giới hạn ai được ghi và chỉ lưu verified data khi có provenance rõ.

Attributes cũng **không thay** Reactor security context và không dùng làm cơ chế lưu secret dài hạn.

### 3.4. getPrincipal() và authentication context

Sau khi Spring Security reactive xác thực, `exchange.getPrincipal()` có thể cung cấp principal tương ứng tùy integration. Trong reactive business flow, dùng `ReactiveSecurityContextHolder.getContext()` hoặc Spring Security method/controller integration, không dựa vào `SecurityContextHolder.getContext()` của một worker thread bất kỳ.

### 3.5. getSession(), formData và multipartData

`getSession()` trả `Mono<WebSession>`; HMAC per-request API thường hướng tới **stateless auth**, không nên tự tạo session từ một successful HMAC để bypass request-signature verification về sau.

`getFormData()` và `getMultipartData()` có thể **đọc/parse request body**, tùy codec và content type. Nếu HMAC contract ký **raw body bytes**, đừng gọi chúng trước khi quyết định cách capture và verify raw stream. Body parsed object không bảo đảm byte-for-byte tương ứng với signer input.

## 4. Một WebFilter cơ bản: nhận exchange và trả Mono<Void>

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ExchangeObservationFilterV1
        implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        // Không block và không tự subscribe.
        return Mono.defer(() -> {
            exchange.getAttributes().put(
                    "hmac.v1.observe.method",
                    exchange.getRequest().getMethod().name());

            return chain.filter(exchange);
        });
    }
}
~~~

Một `WebFilter` trả `Mono<Void>` mô tả công việc bất đồng bộ. Chỉ khi framework subscribe, pipeline mới thực sự được thực thi. Không:

~~~java
// SAI: subscribe ngoài framework, tạo flow độc lập không được chờ.
verifier.verify(exchange).subscribe();
return chain.filter(exchange);
~~~

Sai lầm này có thể cho handler chạy trước khi authentication hoàn tất, lỗi verifier không chặn business, mất context và làm nonce race.

### 4.1. Chaining đúng

Một filter cần chặn request khi verification thất bại và chỉ gọi `chain.filter(exchange)` **sau** khi có kết quả hợp lệ:

~~~java
return verifier.verify(exchange)
        .flatMap(result -> {
            if (!result.accepted()) {
                return reject(exchange);
            }
            return chain.filter(exchange);
        });
~~~

Nếu `verifier.verify` trả `Mono.empty()`, đoạn trên **không gọi chain**; đó có thể là policy fail-closed hoặc bug làm response treo. Phải định nghĩa riêng cách xử lý empty/error, không mặc nhiên tiếp tục request. `chain.filter` chỉ được gọi một lần theo policy.

## 5. Raw URI, parsed path và hợp đồng canonical request

Một HTTP request có thể chứa:

~~~http
POST /v1/tenants/tenant-A/orders?sort=a%2Fb&sort=a%2fb HTTP/1.1
Host: orders.example.test
X-Key-Id: client-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <43-char-base64url-hmac-sha256>
Content-Type: application/json

{"orderId":"O42"}
~~~

Các nguồn khác nhau:

~~~java
var request = exchange.getRequest();

String rawPath = request.getURI().getRawPath();
String rawQuery = request.getURI().getRawQuery();

var decodedPathRepresentation = request.getPath();
var queryParamMap = request.getQueryParams();
~~~

`rawQuery` có thể khác một representation được dựng lại từ `getQueryParams()` vì decoding, duplicate names, order hoặc percent-hex casing. Nếu protocol định nghĩa **ký raw request-target query**, verifier không được sort parsed query tùy ý hoặc dùng `toString()` của multi-value map.

### 5.1. Raw không có nghĩa bytes gốc trên Internet

`getURI().getRawPath()` là raw/encoded path **theo URI ở WebFlux server adapter**, nhưng gateway có thể đã rewrite, normalize, percent-decode hoặc strip prefix trước khi backend nhìn thấy. Một field `X-Original-URI` từ Internet không đáng tin.

Hãy xác định signing boundary:
- Verify tại gateway trước rewrite, rồi truyền authenticated assertion/context có integrity tới backend.
- Hoặc ký một representation công khai, versioned và được backend tái dựng từ **trusted gateway metadata**.
- Hoặc giữ nguyên signed semantics end-to-end nếu topology thật hỗ trợ.

### 5.2. Sign what you execute

Nếu verifier ký `/v1/tenants/tenant-A/orders` nhưng router/handler thực thi trên tenant B vì parser/proxy mismatch, có thể xảy ra cross-tenant bypass. Tenant trong signed path, header/body (nếu có) phải được so và ràng buộc với **trusted target resource** thực tế.

Không làm “compatibility fallback” bằng cách thử các path/query canonical forms tới khi MAC khớp. Cần một contract phiên bản, rejection rules và independent test fixtures.

### 5.3. HTTP/1.1, HTTP/2 và Host/:authority

Host/authority có thể thay đổi qua gateway hoặc HTTP/2 conversion. Nếu host được ký, hợp đồng cần quy định chính xác trusted authority, proxy mapping và port normalization. Không cho caller tự khai `X-Forwarded-Host` rồi coi đó là nguồn signature authority trừ khi gateway strip/overwrite và bảo vệ channel.

## 6. Header parsing: multi-value và HTTP field ambiguity

Dùng:

~~~java
var headers = exchange.getRequest().getHeaders();
String keyId = headers.getFirst("X-Key-Id");
~~~

**không đủ** cho một protocol bảo mật nếu header có hai occurrences:

~~~http
X-Key-Id: client-a-k3
x-key-id: client-b-k1
~~~

HTTP field names là **case-insensitive**. `getFirst` che mất việc có nhiều values. Nếu một proxy đã merge/drop duplicate, backend không thể khôi phục raw wire evidence; cần reject tại trusted ingress.

### 6.1. Parser strict tại WebFlux boundary

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.BadCredentialsException;

public final class StrictSignedHeaderV1 {
    private StrictSignedHeaderV1() {}

    public static String single(HttpHeaders headers, String name) {
        var values = headers.get(name);
        if (values == null || values.size() != 1) {
            throw new BadCredentialsException(
                    "Invalid signed request metadata");
        }

        String value = values.get(0);
        if (value == null || value.isEmpty()
                || value.length() > 256
                || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0) {
            throw new BadCredentialsException(
                    "Invalid signed request metadata");
        }
        return value;
    }
}
~~~

Helper này chỉ là **một lớp** của strict parsing. Cần validate grammar riêng cho key ID, timestamp, nonce và tag, cùng rules cho combined comma-separated field values. Tầng ingress phải reject duplicate/framing ambiguity mà WebFlux adapter không còn thấy được.

### 6.2. Key ID là selector, không phải principal

`X-Key-Id` do client khai là **untrusted input**. Server phải tra **exact key ID** trong trusted registry rồi lấy secret/algorithm/audience/status/principal. Chỉ sau khi full HMAC tag khớp, timestamp/nonce đạt policy mới tạo authenticated principal. Không tạo SecurityContext bằng cách parse `client-a-k3` thành tenant/role.

### 6.3. Mandatory signed headers

Một contract HMAC-HTTP-V1 nên ký `key-id`, `timestamp`, `nonce`, audience và relevant `content-type`/body digest; đừng cho caller gửi danh sách signed headers thiếu trường bắt buộc rồi verifier chấp nhận chỉ vì một số field khác khớp. Nếu có signed header list, validate allowlist/mandatory set và canonical order theo version.

## 7. Request body trong WebFlux là Flux<DataBuffer>

Khác Servlet `InputStream`, WebFlux biểu diễn body bằng một **`Flux<DataBuffer>`**. Nó có thể phát các buffers theo thời gian và chịu cơ chế **backpressure**. Những hệ quả quan trọng:

- Body không mặc nhiên có sẵn toàn bộ ở thời điểm `WebFilter#filter` được gọi.
- Một publisher có thể được subscribe **một lần** theo HTTP transport; đừng giả định có thể đọc lại `getBody()` từ network.
- `DataBuffer` có thể backed bởi **pooled reference-counted memory** (ví dụ Netty), cần release đúng ownership khi giữ buffer ngoài flow tiêu chuẩn.
- `DataBufferUtils.join` có thể gom body có giới hạn nhưng **đang đánh đổi streaming lấy buffering**.
- `collectList()`/`reduce`/`block()`/`subscribe()` tùy tiện trong filter có thể tạo memory leak, block event-loop hoặc vượt authentication ordering.
- Một request body bị đọc bởi authentication middleware phải **được tái cấp chính xác** cho downstream nếu controller còn cần đọc.

### 7.1. Sai: đọc body trong một subscription riêng

~~~java
// SAI: bỏ kết quả, tạo subscription độc lập với request pipeline.
exchange.getRequest().getBody()
        .doOnNext(buffer -> {
            // update digest...
        })
        .subscribe();

return chain.filter(exchange);
~~~

Vì `subscribe()` tự kích hoạt một flow riêng, verifier có thể còn đang đọc body khi controller chạy; lỗi không được truyền về chain và request stream có thể bị tranh chấp hoặc tiêu thụ. Dùng **composition**: dữ liệu phải đi qua một `Mono/Flux` được return, và chỉ gọi chain khi các bước authentication hoàn tất.

### 7.2. Sai: block Netty event loop

~~~java
// SAI trong reactive request processing:
byte[] body = bodyMono.block();
return chain.filter(exchange);
~~~

`block()` trên reactive event-loop gây stall, có thể ném exception và làm throughput/latency suy giảm. Nếu truy vấn key registry, nonce store hoặc KMS là blocking, không gọi JDBC/synchronous Redis SDK ngay trong Netty event loop. Ưu tiên clients non-blocking; nếu không thể, offload blocking work có kiểm soát sang bounded worker scheduler và giám sát capacity.

### 7.3. Sai: join body không có maximum bytes

~~~java
// Không dùng mặc định cho untrusted request không giới hạn:
return DataBufferUtils.join(exchange.getRequest().getBody())
        .flatMap(joined -> { /* ... */ });
~~~

Có thể tạo memory pressure nghiêm trọng nếu attacker gửi body lớn. Cần max request body ở gateway và ứng dụng. Ví dụ educational dùng **64 KiB** cho signed JSON. Với streaming uploads, chọn signing contract khác, không buffer hàng GB trong filter.

### 7.4. DataBuffer ownership

Nếu `DataBufferUtils.join` cấp một joined buffer cho code, cần đọc và **release** sau khi copy bytes nếu không chuyển ownership cho downstream. Không giữ một pooled DataBuffer qua async operations mà không retain/release đúng; không dùng lại một DataBuffer đã đọc xong với read index bị thay đổi.

Với `Flux.defer` tạo một **DataBuffer mới cho mỗi subscription downstream** từ bytes đã copy, từng consumer đọc một wrapper mới. Không tự release buffer downstream trong authentication layer sau khi đã giao cho HTTP framework; lifecycle của buffer mới do pipeline consumer quản lý.

## 8. ServerHttpRequestDecorator và exchange.mutate()

Một điểm mở rộng quan trọng là:

~~~java
var decoratedRequest = new ServerHttpRequestDecorator(exchange.getRequest()) {
    @Override
    public Flux<DataBuffer> getBody() {
        return Flux.defer(() -> {
            DataBuffer buffer = exchange.getResponse()
                    .bufferFactory().wrap(cachedBytes.clone());
            return Flux.just(buffer);
        });
    }
};

ServerWebExchange decoratedExchange = exchange.mutate()
        .request(decoratedRequest)
        .build();

return chain.filter(decoratedExchange);
~~~

Ở đây:

1. `ServerHttpRequestDecorator` ủy quyền phần lớn operations cho request gốc, chỉ override body.
2. `exchange.mutate().request(decoratedRequest).build()` tạo exchange view có request được thay theo contract; không thay đổi bytes đang truyền trên Internet.
3. `Flux.defer` tạo buffers mới khi một subscriber downstream thực sự đọc body.
4. `cachedBytes` phải đến từ **bounded raw-body capture**, không đến từ header digest caller khai.
5. Clone bytes cho mỗi subscription để các consumers không vô tình sửa chung backing array. Điều này tốn memory, chấp nhận cho payload nhỏ đã giới hạn.

Không cho controller đọc request gốc sau khi authentication đọc hết body: nó có thể thấy empty stream. Cũng không dùng exchange decorator để **thay signed path/headers theo ý muốn** khiến verifier và router xử lý hai representations khác nhau.

### 8.1. Mutate dùng để thay request/response khi thực sự cần

`ServerWebExchange.mutate()` có thể hỗ trợ thay request, response hoặc principal theo API. Nhưng **đừng dùng mutate().principal(...) như một đường tắt authentication tự đặt** dựa trên `X-Client-Id`. Security principal phải đến từ Spring Security reactive authentication mechanism, với context propagation và authorization đúng.

### 8.2. Attributes không phải chỗ lưu raw shared secret

Có thể lưu một fingerprint nội bộ hoặc correlation ID trong exchange attributes cho metrics. Nhưng lưu raw HMAC secret, raw sensitive body hoặc full replayable request trong attribute kéo dài thời gian sống của dữ liệu và tăng nguy cơ bị log. Nếu có caching trong RAM, giới hạn size/lifetime, không giữ trên singleton services và tránh leak giữa exchanges.

## 9. Ví dụ Java 17: bounded body replay WebFilter

Đoạn sau minh họa **cách capture body rồi pass cùng bytes cho AuthenticationWebFilter và controller**. Nó là một body-boundary adapter, **không** tự quyết định HMAC đúng/sai và **không** tự tạo principal.

Ví dụ dành cho Spring WebFlux/Spring Security reactive (Spring 6-style APIs). Các import `jakarta.servlet`/`HttpServletRequest` hoàn toàn không xuất hiện.

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class BoundedSignedBodyReplayWebFilter
        implements WebFilter {

    private static final int MAX_BODY_BYTES = 64 * 1024;

    private final ServerWebExchangeMatcher signedApiMatcher =
            new PathPatternParserServerWebExchangeMatcher(
                    "/signed-api/**");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return signedApiMatcher.matches(exchange)
                .flatMap(match -> {
                    if (!match.isMatch()) {
                        return chain.filter(exchange);
                    }
                    return captureAndReplay(exchange, chain);
                });
    }

    private Mono<Void> captureAndReplay(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() ->
                DataBufferUtils.join(
                        exchange.getRequest().getBody(),
                        MAX_BODY_BYTES)
                    .switchIfEmpty(Mono.fromSupplier(() ->
                            exchange.getResponse()
                                    .bufferFactory()
                                    .wrap(new byte[0])))
                    .flatMap(joined -> {
                        final byte[] bytes;
                        try {
                            bytes = new byte[
                                    joined.readableByteCount()];
                            joined.read(bytes);
                        } finally {
                            // Joined buffer was consumed by this filter.
                            DataBufferUtils.release(joined);
                        }

                        var decoratedRequest =
                                new ServerHttpRequestDecorator(
                                        exchange.getRequest()) {
                            @Override
                            public Flux<DataBuffer> getBody() {
                                return Flux.defer(() ->
                                        Flux.just(
                                            exchange.getResponse()
                                                .bufferFactory()
                                                .wrap(bytes.clone())));
                            }
                        };

                        var decoratedExchange = exchange.mutate()
                                .request(decoratedRequest)
                                .build();

                        return chain.filter(decoratedExchange);
                    })
                    .onErrorMap(
                        DataBufferLimitException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "Signed request body too large")));
    }
}
~~~

### 9.1. Tại sao dùng Mono.defer?

`Mono.defer` bảo đảm thao tác đọc body/subscribe được gắn với subscription của **request processing flow**, không thực hiện một eager side effect ngoài pipeline. `DataBufferUtils.join` tiêu thụ body once, copy bytes vào array, release joined buffer rồi tạo decorator truyền xuống chain.

### 9.2. Chuyện gì xảy ra với body rỗng?

Với stream hoàn toàn empty, `join` có thể hoàn tất không phát `DataBuffer`. `switchIfEmpty` cung cấp buffer rỗng để downstream vẫn có một representation ổn định. Chữ ký của body rỗng là SHA-256 của **zero bytes**, không tự biến nó thành dấu ngoặc nhọn JSON, chuỗi null hoặc newline.

### 9.3. Tại sao MAX_BODY_BYTES là 64 KiB?

Đây chỉ là **giới hạn demo** phù hợp signed JSON nhỏ. Production chọn ngưỡng theo endpoint, có giới hạn ở gateway, WebFlux body codecs và ứng dụng, với metrics và memory budgeting. Đọc toàn payload để xác thực là một chi phí **trước authentication** nên vẫn bị DoS nếu không giới hạn concurrency/rate.

### 9.4. Error/cancel/release

`DataBufferUtils.join` có cơ chế quản lý các buffers đã gom khi upstream error/cancel; code release joined buffer khi đã nhận giá trị và copy xong. Các operators lỗi khác, custom decorators/Netty pipelines, multipart/streaming cần review tương ứng. Không gọi `release` hai lần, không giữ reference `joined` sau release, và test cancellation/size limit bằng integration.

### 9.5. Một giới hạn quan trọng của body replay

Đây là một **bounded in-memory buffering example**, không phải bộ middleware tổng quát sẵn sàng production. Nó không hỗ trợ uploads lớn/streaming, không chuẩn hóa `Content-Encoding`, không tự chứng minh handling của multiple subscriptions đồng thời, form-data/multipart decoding hoặc client disconnect. Production cần đánh giá body lifetime, backpressure, memory pressure và chain order trên runtime thực tế.

### 9.6. Đặt trước authentication khi cần

Nếu Spring Security `AuthenticationWebFilter` cần đọc body để tính signature, `BoundedSignedBodyReplayWebFilter` phải chạy **trước security authentication** nhưng **chỉ trên đúng signed API routes**. Cấu hình thứ tự `WebFilter` cần kiểm qua integration tests; không giả định một `@Order` bất kỳ luôn đúng trong mọi cấu hình của `WebFilterChainProxy`.

Nếu middleware khác tiêu thụ body trước adapter, capture sẽ thấy bytes rỗng hoặc sai; phải xác định owner của body và trust boundary. Tùy deployment, bạn có thể tích hợp capture ngay trong specialized authentication `WebFilter` thay vì dùng một filter tách trước nó.

## 10. Spring Security reactive integration và vị trí exchange

Với WebFlux, API authentication chuẩn là **`AuthenticationWebFilter`**, `ServerAuthenticationConverter` và `ReactiveAuthenticationManager`. Một `SecurityWebFilterChain` được cấu hình bằng `ServerHttpSecurity` và sắp xếp qua `SecurityWebFiltersOrder`.

~~~mermaid
flowchart TD
    A[ServerWebExchange] --> B[Body replay adapter if required]
    B --> C[Spring Security WebFilterChainProxy]
    C --> D[AuthenticationWebFilter]
    D --> E[ServerAuthenticationConverter]
    E --> F[Unauthenticated Authentication]
    F --> G[ReactiveAuthenticationManager]
    G --> H[HMAC canonicalizer and credential verifier]
    H --> I[Timestamp plus atomic nonce policy]
    I --> J[Authenticated Authentication]
    J --> K[Reactive Security Context]
    K --> L[AuthorizationWebFilter]
    L --> M[Handler and business policy]
~~~

### 10.1. Một converter không tự tạo authenticated principal

`ServerAuthenticationConverter.convert(exchange)` trích metadata/body và tạo **unauthenticated Authentication**. Chỉ sau `ReactiveAuthenticationManager.authenticate(...)` trả kết quả hợp lệ mới có principal đáng tin.

Khi converter trả `Mono.empty()`, `AuthenticationWebFilter` có thể coi như **không có authentication attempt** và đi tiếp tùy cấu hình. Do đó đối với endpoint **HMAC-required**, matcher và authorization rules phải bảo đảm request thiếu HMAC **không được xử lý như anonymous được phép**. Có thể yêu cầu converter ném `BadCredentialsException` khi missing fields trên HMAC-only route.

### 10.2. SecurityWebFilterChain không giống Servlet SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain signedApiSecurityChain(
        ServerHttpSecurity http,
        AuthenticationWebFilter hmacAuthenticationWebFilter) {

    return http
            .securityMatcher(new PathPatternParserServerWebExchangeMatcher(
                    "/signed-api/**"))
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            // CSRF chỉ vô hiệu ở stateless API không dùng
            // browser cookie/session credentials theo threat model.
            .csrf(csrf -> csrf.disable())
            .addFilterAt(
                    hmacAuthenticationWebFilter,
                    SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
}
~~~

Ví dụ trên cần bean `PathPatternParserServerWebExchangeMatcher`/imports, `AuthenticationWebFilter` được cấu hình converter, manager, matcher và handlers; chain khác xử lý các route còn lại. Nếu một catch-all security chain ưu tiên cao hơn match trước, signed route có thể bị xử lý sai.

### 10.3. AuthenticationWebFilter có lifecycle riêng

Một filter framework quản lý success/failure handlers, authentication context và cách gọi chain. Tự viết `WebFilter` lớn để dựng `ReactiveSecurityContextHolder` mà không hiểu lifecycle có thể dẫn đến:

- Principal không xuất hiện ở authorization.
- Một publisher bị subscribe hai lần.
- Lỗi authentication bị nuốt thành `Mono.empty()`.
- Context bị ghi đè hoặc rò giữa concurrent requests.
- Nonce bị claim lại khi filter chạy nhiều lần.

Ưu tiên framework filter + converter/manager khi đủ đáp ứng body/canonicalization requirements; chỉ custom `WebFilter` khi HTTP signing boundary đặc thù bắt buộc.

## 11. Reactive context, attributes và principal provenance

### 11.1. Không dùng global mutable principal

~~~java
// SAI: request A/B có thể chạy đồng thời.
static String currentClientId;
static String currentTenantId;
~~~

Trong reactive stack, nhiều requests chia sẻ ít threads. ThreadLocal-based principal không phù hợp khi Reactor chuyển scheduler; dùng Spring Security reactive context hoặc explicit typed request-scoped data với provenance rõ.

### 11.2. ReactiveSecurityContextHolder trong handler

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .filter(auth -> auth != null && auth.isAuthenticated())
            .map(auth -> auth.getName());
}
~~~

Authentication phải đến từ trusted provider/verifier. Không tự đặt context từ `X-Key-Id` hoặc `X-Role`. Nếu không có Authentication, publisher ở trên có thể empty; handler cần policy khi không authenticated.

### 11.3. Attributes không thay SecurityContext

`exchange.getAttributes()` cho lưu local metadata của một HTTP exchange, ví dụ canonical version/trace ID được ghi bởi server filter. Nhưng `AUTHENTICATED_CLIENT` chỉ được đặt từ trusted verifier result, không copy client header. Spring Security `Authentication` và `ReactiveSecurityContextHolder` vẫn là điểm tích hợp cho authorization/method security.

## 12. HMAC-HTTP-V1: canonical request từ ServerWebExchange

Để các đoạn Java sau có một hợp đồng xác định, ta dùng **protocol minh họa HMAC-HTTP-V1** (không phải một RFC authentication scheme):

~~~http
POST /signed-api/orders?dryRun=false HTTP/1.1
Host: orders.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <43-character-base64url-hmac-sha256>

{"orderId":"O42"}
~~~

Canonical bytes:

~~~text
HMAC-HTTP-V1
POST
/signed-api/orders
dryRun=false
audience:orders-api
content-type:application/json
key-id:partner-a-k3
timestamp:1800000030
nonce:0123456789abcdef0123456789abcdef
body-sha256:<lowercase-hex-of-SHA256-raw-body>
~~~

Quy định:

- Ghép 10 dòng bằng LF, encode UTF-8 và **không có LF cuối**.
- Method là `POST`; path đúng literal `/signed-api/orders`; query đúng literal `dryRun=false` (demo chỉ hỗ trợ một route/shape).
- Audience cố định `orders-api`, phải được đối chiếu credential policy và actual routed service.
- Content-Type có đúng một value `application/json` (hợp đồng demo).
- Key ID, timestamp và nonce được strict parse và **đều nằm trong signed bytes**.
- Body digest do server tính từ **raw body bytes đã capture**, không tin body hash header caller gửi.
- Expected tag HMAC-SHA256 32 bytes; presented tag Base64URL không padding 43 ký tự.
- Signature header là output tag, **không nằm trong HMAC input**.
- Unsupported encodings/headers, duplicate query parameters, path aliases bị reject; production cần canonicalization version phong phú hơn nếu muốn hỗ trợ chúng.

### 12.1. Vì sao canonicalization cần biết ServerWebExchange?

`ServerWebExchange` cung cấp method/URI/header/body theo đúng giai đoạn request được nhận. Signer và verifier phải thống nhất:
- URI trước/sau gateway rewrite?
- Query raw hay query params đã parse?
- Header name/value normalization?
- Request body được hash trước hay sau decompression?
- Phần nào được phép unsigned?

Nếu backend HMAC verifier nhìn một `ServerWebExchange` đã được mutate trước đó, các fields được ký phải là representation **có nguồn đáng tin** và phù hợp với business handler thực thi. Không cho một external header `X-Canonical-Request` quyết định canonical bytes.

### 12.2. Java 17 canonicalizer

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;
import org.springframework.http.HttpMethod;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;

public final class ExchangeCanonicalizerV1 {
    private static final Pattern KEY =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private ExchangeCanonicalizerV1() {}

    public static byte[] bytes(
            ServerWebExchange exchange,
            String keyId, long timestamp, String nonce,
            byte[] rawBody) throws NoSuchAlgorithmException {

        var request = exchange.getRequest();

        if (request.getMethod() != HttpMethod.POST
                || !"/signed-api/orders".equals(
                        request.getURI().getRawPath())
                || !"dryRun=false".equals(
                        request.getURI().getRawQuery())
                || keyId == null || !KEY.matcher(keyId).matches()
                || nonce == null || !NONCE.matcher(nonce).matches()
                || timestamp < 0L
                || rawBody == null || rawBody.length > 65536) {
            throw new BadCredentialsException(
                    "Outside HMAC-HTTP-V1 contract");
        }

        String contentType = StrictSignedHeaderV1.single(
                request.getHeaders(), "Content-Type");
        if (!"application/json".equals(contentType)) {
            throw new BadCredentialsException(
                    "Invalid signed Content-Type");
        }

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        String bodyHex = HexFormat.of().formatHex(digest);

        String canonical = String.join("\n",
                "HMAC-HTTP-V1",
                "POST",
                "/signed-api/orders",
                "dryRun=false",
                "audience:orders-api",
                "content-type:application/json",
                "key-id:" + keyId,
                "timestamp:" + timestamp,
                "nonce:" + nonce,
                "body-sha256:" + bodyHex);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Code này giới hạn HTTP shape để tránh tuyên bố “ký đúng mọi URI”. Không dùng `getQueryParams().toString()` thay raw query hoặc ký JSON đã reserialize. Với production, cần independent canonical byte fixtures cho multi-value query, percent-encoding, trailing slash, Unicode và HTTP/2 gateway semantics.

## 13. Reactive AuthenticationConverter đọc body đã được replay

`ServerAuthenticationConverter` làm nhiệm vụ **parse một HTTP request thành yêu cầu authentication chưa xác minh**, không tự tạo principal đã authenticated.

### 13.1. Token đầu vào chưa đáng tin

~~~java
import java.util.Collections;
import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class PresentedHmacAuthenticationV1
        extends AbstractAuthenticationToken {

    private final String keyId;
    private final long timestampSeconds;
    private final String nonceHex;
    private final byte[] canonical;
    private final byte[] presentedTag;

    public PresentedHmacAuthenticationV1(
            String keyId, long timestampSeconds, String nonceHex,
            byte[] canonical, byte[] presentedTag) {
        super(Collections.emptyList());
        this.keyId = keyId;
        this.timestampSeconds = timestampSeconds;
        this.nonceHex = nonceHex;
        this.canonical = canonical.clone();
        this.presentedTag = presentedTag.clone();
        setAuthenticated(false);
    }

    public String keyId() { return keyId; }
    public long timestampSeconds() { return timestampSeconds; }
    public String nonceHex() { return nonceHex; }
    public byte[] canonicalBytes() { return canonical.clone(); }

    @Override
    public Object getPrincipal() {
        // UNTRUSTED selector; not an authenticated identity.
        return keyId;
    }

    @Override
    public Object getCredentials() {
        return presentedTag.clone();
    }
}
~~~

**Cảnh báo:** `getPrincipal()` trên token chưa authenticated chỉ là input selector. Không đưa nó vào application SecurityContext hoặc dùng key ID để cấp role. Token chứa presented tag, cần tránh log/toString và xóa sensitive data theo lifecycle tương ứng khi triển khai thực tế.

### 13.2. Strict metadata/parser

~~~java
import java.util.Base64;
import java.util.regex.Pattern;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.http.HttpHeaders;

public final class HmacMetadataParserV1 {
    private static final Pattern TIMESTAMP =
            Pattern.compile("(?:0|[1-9][0-9]{0,18})");
    private static final Pattern TAG =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private HmacMetadataParserV1() {}

    public static long timestamp(HttpHeaders headers) {
        String raw = StrictSignedHeaderV1.single(
                headers, "X-Timestamp");

        if (!TIMESTAMP.matcher(raw).matches()) {
            throw new BadCredentialsException("Invalid timestamp");
        }

        try {
            return Long.parseLong(raw);
        } catch (NumberFormatException overflow) {
            throw new BadCredentialsException("Invalid timestamp");
        }
    }

    public static byte[] fullTag(HttpHeaders headers) {
        String encoded = StrictSignedHeaderV1.single(
                headers, "X-Signature");
        if (!TAG.matcher(encoded).matches()) {
            throw new BadCredentialsException("Invalid signature");
        }

        final byte[] tag;
        try {
            tag = Base64.getUrlDecoder().decode(encoded);
        } catch (IllegalArgumentException invalid) {
            throw new BadCredentialsException("Invalid signature");
        }

        if (tag.length != 32 ||
                !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(tag).equals(encoded)) {
            throw new BadCredentialsException("Invalid signature");
        }
        return tag;
    }
}
~~~

Strict parse còn cần validate key ID/nonce grammar, duplicate fields theo `StrictSignedHeaderV1`; converter bên dưới chuyển lỗi về `AuthenticationException`. Thời gian là **Unix epoch seconds**, không tự đoán milliseconds, dấu cộng, chuỗi số có leading zeros hoặc values overflow.

### 13.3. Reactive converter

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class HmacExchangeConverterV1
        implements ServerAuthenticationConverter {

    private static final int MAX_BYTES = 64 * 1024;

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        return Mono.defer(() -> {
            var headers = exchange.getRequest().getHeaders();

            // Required HMAC route: missing headers means BAD request,
            // not Mono.empty() anonymous fallback.
            String keyId = StrictSignedHeaderV1.single(
                    headers, "X-Key-Id");
            String nonce = StrictSignedHeaderV1.single(
                    headers, "X-Nonce");
            long timestamp = HmacMetadataParserV1
                    .timestamp(headers);
            byte[] tag = HmacMetadataParserV1.fullTag(headers);

            return DataBufferUtils.join(
                        exchange.getRequest().getBody(), MAX_BYTES)
                    .switchIfEmpty(Mono.fromSupplier(() ->
                            exchange.getResponse()
                                    .bufferFactory()
                                    .wrap(new byte[0])))
                    .map(joined -> {
                        final byte[] bytes;
                        try {
                            bytes = new byte[
                                    joined.readableByteCount()];
                            joined.read(bytes);
                        } finally {
                            DataBufferUtils.release(joined);
                        }

                        try {
                            byte[] canonical =
                                ExchangeCanonicalizerV1.bytes(
                                    exchange, keyId, timestamp,
                                    nonce, bytes);

                            return (Authentication)
                                new PresentedHmacAuthenticationV1(
                                    keyId, timestamp, nonce,
                                    canonical, tag);

                        } catch (java.security.NoSuchAlgorithmException e) {
                            throw new AuthenticationServiceException(
                                    "SHA-256 unavailable", e);
                        }
                    })
                    .onErrorMap(DataBufferLimitException.class,
                        ex -> new BadCredentialsException(
                                "Signed request too large", ex));
        });
    }
}
~~~

**Quan trọng:** Ví dụ converter này **giả định body-replay adapter ở mục 9 chạy trước**. Nó subscribe vào decorated `getBody()` để tính canonical bytes; sau đó controller subscribe lần nữa và đọc cùng bytes từ decorator. Nếu không có wrapper, converter sẽ tiêu thụ request body và controller có thể nhận body rỗng.

Đừng dùng converter trên streaming/multipart endpoints mà chưa thiết kế bounded payload, replay và signing contract. Để tối ưu, có thể thiết kế body capture một lần và truyền immutable digest nội bộ tới converter, nhưng phải giữ ownership/provenance, chống attribute spoofing và kiểm đúng body mà handler xử lý.

### 13.4. Khi nào converter trả Mono.empty?

Nếu một `AuthenticationWebFilter` được dùng cho optional multi-scheme routes, `Mono.empty()` có thể biểu thị “converter không nhận diện credentials này” và cho filter khác xử lý. Nhưng đối với **HMAC-only endpoint**, missing/malformed signed fields phải là failure hoặc bị authorization gate chặn chắc chắn; không chọn empty chỉ để “để chạy tiếp cho tiện”.

## 14. ReactiveAuthenticationManager và HMAC verifier

Sau converter, `ReactiveAuthenticationManager` cần:

1. Nhận đúng loại unauthenticated token.
2. Exact lookup key ID từ registry **reactive/non-blocking**.
3. Kiểm key status (ACTIVE/RETIRING window, không REVOKED), audience và algorithm.
4. Tính HMAC expected trên canonical bytes và **strict 32-byte tag**.
5. Kiểm signed timestamp theo **server clock**.
6. Claim nonce bằng shared atomic reactive replay store.
7. Trả `Authentication` với trusted principal/authorities; không lấy role/tenant từ caller headers.

### 14.1. Interfaces cô lập storage

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

public interface ReactiveCredentialRegistryV1 {
    // Empty = verified absent ID, error = lookup unavailable.
    Mono<HmacCredentialV1> findExact(String keyId);
}

public interface ReactiveNonceStoreV1 {
    enum Claim { NEW, REPLAY, UNKNOWN }

    // One atomic create-if-absent on a shared authority.
    Mono<Claim> claimOnce(String nonceNamespace, Duration ttl);
}
~~~

Credential record:

~~~java
import java.time.Instant;
import java.util.Set;
import java.util.Objects;

public record HmacCredentialV1(
        String keyId,
        String principalId,
        String tenantId,
        String audience,
        String algorithm,
        String status,
        Instant notBefore,
        Instant notAfter,
        byte[] secret,
        Set<String> authorities) {

    public HmacCredentialV1 {
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(algorithm);
        Objects.requireNonNull(status);
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(secret);
        authorities = Set.copyOf(authorities);
        secret = secret.clone();
    }

    @Override
    public byte[] secret() {
        return secret.clone();
    }
}
~~~

Trong production, thay `String status` bằng enum/state machine/rotation policy rõ, có `verifyUntil` cho RETIRING; dùng secret manager/KMS phiên bản hóa, không log `record.toString()` vì record chứa secret bytes metadata. Bài demo manager dưới đây chỉ accept ACTIVE để giữ policy ngắn và fail closed.

### 14.2. Trusted principal

~~~java
public record VerifiedHmacPrincipalV1(
        String principalId,
        String tenantId,
        String credentialKeyId,
        String audience) {}
~~~

Principal phải được tạo **sau** HMAC và replay admission. `tenantId` từ trusted registry không mặc nhiên cho phép mọi resource có path tenant khác; authorization phải kiểm grants, scopes, object ownership.

## 15. Java 17: ReactiveAuthenticationManager kiểm HMAC và replay

Manager dưới đây minh họa **một luồng HMAC admission hoàn chỉnh ở mức service**, sau khi converter đã dựng canonical bytes. Nó không xử lý authorization tenant/resource; việc đó thuộc security authorization/handler. Các file Java public ở các mục nên được tách thành source files khi dùng trong project.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import reactor.core.publisher.Mono;

public final class ReactiveHmacAuthenticationManagerV1
        implements ReactiveAuthenticationManager {

    private static final long MAX_PAST_AGE_SECONDS = 300;
    private static final long MAX_FUTURE_SKEW_SECONDS = 30;
    private static final Duration REPLAY_TTL =
            Duration.ofSeconds(360);

    private final ReactiveCredentialRegistryV1 registry;
    private final ReactiveNonceStoreV1 nonceStore;
    private final Clock clock;

    public ReactiveHmacAuthenticationManagerV1(
            ReactiveCredentialRegistryV1 registry,
            ReactiveNonceStoreV1 nonceStore,
            Clock clock) {

        this.registry = registry;
        this.nonceStore = nonceStore;
        this.clock = clock;
    }

    @Override
    public Mono<Authentication> authenticate(
            Authentication authentication) {

        if (!(authentication instanceof
                PresentedHmacAuthenticationV1 candidate)) {
            // Manager này không xử lý các token loại khác.
            return Mono.empty();
        }

        return Mono.defer(() -> registry
                .findExact(candidate.keyId())
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException(
                                "Invalid HMAC credentials")))
                .flatMap(record -> authenticateWithRecord(
                        candidate, record)));
    }

    private Mono<Authentication> authenticateWithRecord(
            PresentedHmacAuthenticationV1 candidate,
            HmacCredentialV1 record) {

        Instant now = clock.instant();

        // Demo only: ACTIVE. Production RETIRING/rotation
        // needs explicit server-side verifyUntil policy.
        if (!record.keyId().equals(candidate.keyId())
                || !"ACTIVE".equals(record.status())
                || !"orders-api".equals(record.audience())
                || !"HmacSHA256".equals(record.algorithm())
                || now.isBefore(record.notBefore())
                || !now.isBefore(record.notAfter())) {

            return Mono.error(new BadCredentialsException(
                    "Invalid HMAC credentials"));
        }

        byte[] expected;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                    record.secret(), "HmacSHA256"));
            expected = mac.doFinal(candidate.canonicalBytes());
        } catch (GeneralSecurityException e) {
            return Mono.error(new AuthenticationServiceException(
                    "HMAC verifier unavailable", e));
        }

        if (!MessageDigest.isEqual(
                expected, (byte[]) candidate.getCredentials())) {
            return Mono.error(new BadCredentialsException(
                    "Invalid HMAC credentials"));
        }

        long nowSeconds = now.getEpochSecond();
        final long oldest;
        final long newest;
        try {
            oldest = Math.subtractExact(
                    nowSeconds, MAX_PAST_AGE_SECONDS);
            newest = Math.addExact(
                    nowSeconds, MAX_FUTURE_SKEW_SECONDS);
        } catch (ArithmeticException overflow) {
            return Mono.error(new BadCredentialsException(
                    "Invalid signed timestamp"));
        }

        if (candidate.timestampSeconds() < oldest
                || candidate.timestampSeconds() > newest) {
            return Mono.error(new BadCredentialsException(
                    "Invalid signed timestamp"));
        }

        String replayKey = "hmac-replay:v1:orders-api:"
                + candidate.keyId()
                + ":" + candidate.nonceHex();

        return nonceStore.claimOnce(replayKey, REPLAY_TTL)
                .switchIfEmpty(Mono.error(
                        new AuthenticationServiceException(
                                "Replay authority returned empty")))
                .flatMap(claim -> {
                    if (claim == ReactiveNonceStoreV1.Claim.REPLAY) {
                        return Mono.error(
                                new BadCredentialsException(
                                        "Request replay"));
                    }
                    if (claim != ReactiveNonceStoreV1.Claim.NEW) {
                        return Mono.error(
                                new AuthenticationServiceException(
                                        "Replay authority uncertain"));
                    }

                    var principal = new VerifiedHmacPrincipalV1(
                            record.principalId(),
                            record.tenantId(),
                            record.keyId(),
                            record.audience());

                    List<SimpleGrantedAuthority> authorities =
                            record.authorities().stream()
                                .map(SimpleGrantedAuthority::new)
                                .toList();

                    return Mono.just((Authentication)
                            UsernamePasswordAuthenticationToken
                                .authenticated(
                                    principal, null, authorities));
                });
    }
}
~~~

### 15.1. Đâu là phần reactive?

`registry.findExact` và `nonceStore.claimOnce` đều trả `Mono`; manager ghép chúng bằng `flatMap`, không gọi `block()` hoặc `subscribe()`. Spring Security subscribe/lấy kết quả thông qua authentication filter.

HMAC SHA-256 trên một signed body **đã giới hạn 64 KiB** là thao tác CPU synchronous nhỏ trong callback; không có I/O blocking ở đây. Nếu phải giải mã payload lớn/hardware crypto gọi đồng bộ, cần đánh giá scheduling/CPU và backpressure, không chạy blocking I/O trên event-loop.

### 15.2. Unknown key khác registry outage

`Mono.empty()` từ `registry.findExact` trong ví dụ có nghĩa **authoritative exact lookup xác nhận không có key** nên biến thành `BadCredentialsException`.

**Registry timeout không được biến thành Mono.empty().** Adapter phải báo lỗi dependency hoặc authentication service unavailable; manager không được thử default secret, key ID của client khác hoặc cached REVOKED record như ACTIVE để giữ availability.

### 15.3. Key ID phải ràng buộc trong canonical bytes

`candidate.keyId()` được converter lấy từ signed field và `ExchangeCanonicalizerV1.bytes` đưa key ID đó vào HMAC input. Nếu attacker đổi key ID sau signing, verifier chọn secret của ID mới và canonical bytes cũng thay đổi → MAC phải mismatch.

Tách riêng credentials theo client/trust boundary. Nếu A/B dùng cùng secret bytes, hai key IDs khác nhau **không tạo cryptographic isolation thực sự**.

### 15.4. Full-tag comparison, không so chuỗi/prefix

Tag từ converter phải được decode strict 32-byte HMAC-SHA256 output. `MessageDigest.isEqual` phù hợp hơn `String.equals` hoặc early-exit custom loop khi so expected/presented MAC. Nhưng nó **không** chứng minh toàn key lookup, HTTP parsing hay registry cache là constant-time; tránh oracle qua error messages/timing theo threat model.

### 15.5. Status/revocation

Manager demo chỉ nhận `ACTIVE` và valid interval. Production cần key status state machine, planned rotation `RETIRING` + `verifyUntil`, emergency `REVOKED` và consistency guarantee trên tất cả verifier nodes.

Một request dùng stolen secret có thể mang timestamp/nonce mới và MAC hoàn toàn đúng; sau revoke phải **reject vì credential status**, không chấp nhận dựa trên signed timestamp trước revokedAt.

### 15.6. Reactive nonce store không được local per-pod

Một replay namespace minh họa:

~~~text
hmac-replay:v1:orders-api:partner-a-k3:0123456789abcdef0123456789abcdef
~~~

Key dựa trên trusted audience, exact signed key ID và signed nonce. Client A/B được scoped riêng; cùng key ID/nonce gửi vào hai pods phải được claim bởi **cùng authority**, không hai in-memory hash maps.

Khi replay store trả `UNKNOWN`, `Mono.empty()` hoặc error, **không** xử lý business. Acknowledged atomic operation của một Redis primary không mặc nhiên durable qua mọi asynchronous replica failover. Nếu yêu cầu mạnh, chọn consistency/durability phù hợp và test failover.

### 15.7. Freshness và TTL

Cho `A=300s` max past age, `F=30s` future skew, `M=30s` safety margin. TTL 360s tính từ lúc nonce được claim là một bound bảo thủ:

\[
TTL_{\mathrm{nonce}} \ge A + F + M
\]

Nếu TTL quá ngắn, một nonce đã hết hạn trong store có thể được replay khi signed timestamp vẫn nằm trong acceptance window. Client clock skew phải được sửa ở client/clock sync, không tự nới future window vô hạn.

## 16. Redis reactive adapter minh họa atomic nonce claim

Khi dùng Spring Data Redis Reactive, một adapter có thể sử dụng **atomic set-if-absent với TTL**:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public final class RedisReactiveNonceStoreV1
        implements ReactiveNonceStoreV1 {

    private final ReactiveStringRedisTemplate redis;

    public RedisReactiveNonceStoreV1(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public Mono<Claim> claimOnce(
            String key, Duration ttl) {

        return redis.opsForValue()
                .setIfAbsent(key, "seen", ttl)
                .map(first -> first ? Claim.NEW : Claim.REPLAY)
                .switchIfEmpty(Mono.just(Claim.UNKNOWN));
    }
}
~~~

`setIfAbsent(key, value, ttl)` được triển khai tương đương một lệnh atomic conditional SET kèm expiry trên Redis phù hợp. Không dùng hai operations `hasKey` rồi `set` vì concurrent requests có thể cùng thấy missing.

**Không dùng onErrorReturn(Claim.NEW).** Lỗi Redis phải fail closed; có thể map sang typed infrastructure error để auth failure handler xử lý và metrics phân biệt outage. Nếu Redis cluster/replication/failover có semantics yếu hơn yêu cầu, thiết kế authority/replay durability khác.

### 16.1. Body/replay cả hai đều có “một lần” nhưng khác ý nghĩa

- Body publisher của một network request là một resource flow có thể không re-subscribe; body-replay decorator giúp **downstream đọc lại bytes** trong cùng exchange.
- Nonce replay store ngăn **một signed request** được admit nhiều lần vào business API, kể cả gửi qua nhiều nodes.

Không nhầm “body được replay tới controller” với “được phép replay HTTP request lên server”.

## 17. HMAC authentication và authorization trong WebFlux

Một successful authentication token có principal:

~~~text
principal = partner-a-service
credential = partner-a-k3
tenant = tenant-A
audience = orders-api
authorities = [SCOPE_orders:create]
~~~

Khi client ký request body chứa `"tenantId":"tenant-B"`, HMAC có thể **valid** nhưng authorization phải kiểm tenant/resource ownership:

~~~text
HMAC verification: PASS for partner-a-k3
Replay/freshness: PASS
Authenticated principal: tenant-A
Requested business resource: tenant-B
Authorization: DENY (unless explicit trusted delegation)
~~~

Có thể dùng `authorizeExchange`, custom reactive `ReactiveAuthorizationManager`, method security hoặc domain-level tenant policy để enforce action/resource. **Không tạo role/tenant từ `X-Role`/`X-Tenant-Id` do caller tự khai** dù header được ký: HMAC chỉ chứng minh caller đã khai giá trị đó, không chứng minh server đã cấp quyền.

### 17.1. Tenant revoked nhưng MAC đúng

Nếu tenant A REVOKED trong trusted policy store, request từ credential ACTIVE A3 có thể vẫn MAC hợp lệ; normal operations trên A phải bị từ chối. Với queued/long-running jobs, có thể cần revalidate tenant epoch/state trước commit.

### 17.2. Exchange attributes và authorization

Nếu middleware đặt `exchange.getAttributes().put("tenant", "...")` trước authentication, downstream tuyệt đối không nên xem đó là trusted tenant. Chỉ trusted verified principal + policy grant quyết định authority. Một reactive request-scoped attribute hữu ích cho correlation/trace không đồng nghĩa authority token.

## 18. Unit test reactive verifier bằng StepVerifier và JUnit 5

Các ví dụ sử dụng **Java 17, JUnit Jupiter, reactor-test và Spring WebFlux mock classes**. Chúng chứng minh kết quả của `ReactiveAuthenticationManager` và deterministic clock, **chưa chứng minh** body replay/HTTP gateway/Redis production. Khi triển khai thật, đặt mỗi public class/record/interface trong source file tương ứng và bổ sung đúng dependencies.

### 18.1. Fixture: signed request ở một mốc thời gian cố định

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

public final class ReactiveHmacAuthenticationManagerV1Test {
    private static final long EPOCH = 1_800_000_030L;

    private static final Instant NOW =
            Instant.ofEpochSecond(EPOCH);

    private static final byte[] TEST_SECRET =
            "independent-test-secret-for-client-A"
                .getBytes(StandardCharsets.UTF_8);

    private final Clock clock =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private ReactiveCredentialRegistryV1 registry;
    private ReactiveNonceStoreV1 nonceStore;
    private ReactiveHmacAuthenticationManagerV1 manager;

    private final java.util.Set<String> claimed =
            java.util.concurrent.ConcurrentHashMap.newKeySet();

    private static HmacCredentialV1 credential(String status) {
        return new HmacCredentialV1(
                "client-a-k3",
                "client-A-service",
                "tenant-A",
                "orders-api",
                "HmacSHA256",
                status,
                NOW.minusSeconds(600),
                NOW.plusSeconds(600),
                TEST_SECRET,
                Set.of("SCOPE_orders:create"));
    }

    @BeforeEach
    void setup() {
        HmacCredentialV1 key = credential("ACTIVE");
        registry = id -> "client-a-k3".equals(id)
                ? Mono.just(key)
                : Mono.empty();

        nonceStore = (name, ttl) -> Mono.just(
                claimed.add(name)
                    ? ReactiveNonceStoreV1.Claim.NEW
                    : ReactiveNonceStoreV1.Claim.REPLAY);

        claimed.clear();
        manager = new ReactiveHmacAuthenticationManagerV1(
                registry, nonceStore, clock);
    }

    private static PresentedHmacAuthenticationV1 candidate(
            String keyId, String nonce, byte[] signerSecret)
            throws Exception {

        byte[] body = "{\"orderId\":\"O42\"}"
                .getBytes(StandardCharsets.UTF_8);

        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                    .post("/signed-api/orders?dryRun=false")
                    .header("Content-Type", "application/json")
                    .build());

        byte[] canonical = ExchangeCanonicalizerV1.bytes(
                exchange, keyId, EPOCH, nonce, body);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(signerSecret, "HmacSHA256"));
        byte[] tag = mac.doFinal(canonical);

        return new PresentedHmacAuthenticationV1(
                keyId, EPOCH, nonce, canonical, tag);
    }

    @Test
    void matchingKeyMacAndFreshNonceAuthenticate()
            throws Exception {

        var submitted = candidate(
                "client-a-k3",
                "0123456789abcdef0123456789abcdef",
                TEST_SECRET);

        StepVerifier.create(manager.authenticate(submitted))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertEquals("client-A-service",
                        ((VerifiedHmacPrincipalV1) auth
                            .getPrincipal()).principalId());
                    assertEquals("tenant-A",
                        ((VerifiedHmacPrincipalV1) auth
                            .getPrincipal()).tenantId());
                })
                .verifyComplete();

        assertEquals(1, claimed.size());
    }

    @Test
    void wrongSecretDoesNotClaimNonce() throws Exception {
        byte[] wrongSecret =
                "another-independent-test-secret!"
                .getBytes(StandardCharsets.UTF_8);

        var submitted = candidate(
                "client-a-k3",
                "0123456789abcdef0123456789abcdef",
                wrongSecret);

        StepVerifier.create(manager.authenticate(submitted))
                .expectError(BadCredentialsException.class)
                .verify();

        assertTrue(claimed.isEmpty());
    }

    @Test
    void sameSignedRequestCannotBeAdmittedTwice()
            throws Exception {

        var submitted = candidate(
                "client-a-k3",
                "0123456789abcdef0123456789abcdef",
                TEST_SECRET);

        StepVerifier.create(manager.authenticate(submitted))
                .expectNextCount(1)
                .verifyComplete();

        StepVerifier.create(manager.authenticate(submitted))
                .expectError(BadCredentialsException.class)
                .verify();

        assertEquals(1, claimed.size());
    }

    @Test
    void validMacUnderRevokedKeyMustFail()
            throws Exception {

        registry = id -> Mono.just(credential("REVOKED"));
        manager = new ReactiveHmacAuthenticationManagerV1(
                registry, nonceStore, clock);

        var submitted = candidate(
                "client-a-k3",
                "0123456789abcdef0123456789abcdef",
                TEST_SECRET);

        StepVerifier.create(manager.authenticate(submitted))
                .expectError(BadCredentialsException.class)
                .verify();

        assertTrue(claimed.isEmpty());
    }

    @Test
    void unknownKeyMustNotFallBackToSecret()
            throws Exception {

        var submitted = candidate(
                "client-a-k99",
                "0123456789abcdef0123456789abcdef",
                TEST_SECRET);

        StepVerifier.create(manager.authenticate(submitted))
                .expectError(BadCredentialsException.class)
                .verify();

        assertTrue(claimed.isEmpty());
    }

    @Test
    void replayStoreOutageMustNotAuthenticate()
            throws Exception {

        nonceStore = (name, ttl) ->
                Mono.just(ReactiveNonceStoreV1.Claim.UNKNOWN);
        manager = new ReactiveHmacAuthenticationManagerV1(
                registry, nonceStore, clock);

        var submitted = candidate(
                "client-a-k3",
                "0123456789abcdef0123456789abcdef",
                TEST_SECRET);

        StepVerifier.create(manager.authenticate(submitted))
                .expectError()
                .verify();
    }
}
~~~

### 18.2. Một giới hạn cần nói rõ

`candidate` trong test trên được dựng trực tiếp bằng canonical bytes và test secret; vì thế nó **không** chứng minh `ServerAuthenticationConverter` thật đã đọc body đúng từ `ServerWebExchange`. Hai bên dùng cùng canonicalizer sai cũng có thể khiến happy-path tests thành công. Cần **golden canonical byte fixtures độc lập** và `WebTestClient` tests qua HTTP route.

### 18.3. Fake nonce store không thay Redis production

`ConcurrentHashMap.newKeySet()` là atomic **trong một JVM**, không có TTL, replication/failover hay cluster consistency. Mục đích của fake là xác nhận logic “claim nonce chỉ sau correct HMAC”, không chứng minh toàn hệ thống chống replay khi có hai pods.

### 18.4. Không dùng Thread.sleep để kiểm race

Với reactive/async concurrency tests, dùng `StepVerifier`, `VirtualTimeScheduler`, `CountDownLatch`/barriers (chỉ trong test coordination, không block event-loop production), hoặc một test double có thể điều khiển publisher completion. Cần kiểm cancellation, timeout và double-subscription trong body publisher.

## 19. WebTestClient: test ServerWebExchange và body-replay flow

`WebTestClient` giúp gửi HTTP requests qua WebFlux filter/handler stack. Có thể bind vào application context hoặc server đang chạy; chọn mode phù hợp requirement.

### 19.1. Những ca quan trọng

| Request | Kỳ vọng |
| --- | --- |
| POST `/signed-api/orders?dryRun=false` không key ID/signature | Authentication reject, không handler side effect |
| POST key ID sai grammar | Reject trước registry lookup |
| POST duplicate `X-Key-Id` nhìn thấy ở adapter | Reject |
| POST malformed Base64URL tag | Reject |
| POST correct tag và body B | Authenticated, handler đọc **đúng B** |
| POST body whitespace thay đổi giữ tag | MAC mismatch |
| POST same tag/nonce lần hai | Replay reject |
| POST timestamp too old/future | Freshness reject |
| POST key REVOKED với tag đúng | Key policy reject |
| POST key A nhưng MAC dùng secret B | Bad MAC; no fallback |
| POST đúng MAC, unauthorized tenant | Authorization deny |
| POST body 64 KiB | Theo signed-body size contract |
| POST body 64 KiB+1 | Reject (ví dụ HTTP 413 từ body adapter) |
| POST query duplicate, percent-encoded alias | Strict contract reject |
| POST proxy rewritten path | HMAC matches only agreed signing boundary |
| Redis/registry timeout | Fail closed; không trả authenticated principal |

### 19.2. WebTestClient integration skeleton

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
public class SignedApiWebTestClientIT {

    @Autowired
    WebTestClient client;

    @Test
    void missingHmacNeverReachesBusinessHandler() {
        client.post()
                .uri("/signed-api/orders?dryRun=false")
                .header("Content-Type", "application/json")
                .bodyValue("{\"orderId\":\"O42\"}")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

**Đây là skeleton**, cần một WebFlux Spring Boot test application với đúng `SecurityWebFilterChain`, entry point và handler. Code không tự chứng minh raw body preservation hoặc multi-node replay; các tests khác phải gửi tag thật tính theo independent canonical fixture.

### 19.3. Đo body đúng bytes, không chỉ JSON tương đương

Một handler test có thể echo hoặc hash request body:

~~~java
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class RawBodyEchoControllerV1 {
    @PostMapping(
        path = "/signed-api/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Integer> bodyLength(
            org.springframework.http.server.reactive.ServerHttpRequest req) {

        return DataBufferUtils.join(req.getBody())
            .map(buffer -> {
                try {
                    return buffer.readableByteCount();
                } finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .defaultIfEmpty(0);
    }
}
~~~

Controller này chỉ minh họa kiểm body bytes trong test, không phải một business endpoint. Với size-limit tests, dùng đúng bounded replay adapter và assert handler không chạy nếu body vượt giới hạn.

Để chứng minh **byte-for-byte**, handler nên trả SHA-256 của bytes thực nhận hoặc so một independent known digest, không chỉ length (hai bodies khác nhau có thể cùng độ dài). Nếu echo raw bytes qua response, cân nhắc tránh leak payload nhạy cảm và chỉ làm trong test environment.

### 19.4. HTTP ingress thực vẫn khác in-process WebTestClient

`WebTestClient.bindToApplicationContext` không đảm bảo tái tạo raw TCP framing, HTTP/2 pseudo-headers, gateway percent decoding hoặc duplicate header merging. Phải có end-to-end tests qua proxy/gateway thật cho các trust-boundary bugs.

## 20. Reactor StepVerifier: cancellation, empty body và body subscription

Body publisher có thể bị cancel khi client ngắt kết nối hoặc downstream timeout. Các bất biến:

1. Không leak `DataBuffer` khi upstream cancel hoặc error.
2. Không có side effect từ một subscription tách ngoài chain.
3. Empty body được xử lý như zero bytes, không biến thành null.
4. Body không vượt bounded limit.
5. Khi một consumer downstream đọc body, bytes phải đúng với những gì verifier dùng để ký.
6. Khi authentication fail, business handler không được gọi.
7. Nếu filter chain không được subscribe, không đọc body/không claim nonce.

### 20.1. Một fake WebFilterChain ghi lại raw-body digest

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

AtomicReference<String> downstreamBodyDigest =
        new AtomicReference<>();

WebFilterChain chain = decoratedExchange ->
        DataBufferUtils.join(decoratedExchange.getRequest().getBody())
            .flatMap(buffer -> {
                byte[] bytes = new byte[buffer.readableByteCount()];
                try {
                    buffer.read(bytes);
                } finally {
                    DataBufferUtils.release(buffer);
                }

                try {
                    byte[] sha = MessageDigest
                            .getInstance("SHA-256")
                            .digest(bytes);
                    downstreamBodyDigest.set(
                            HexFormat.of().formatHex(sha));
                    return Mono.<Void>empty();
                } catch (java.security.NoSuchAlgorithmException ex) {
                    return Mono.error(ex);
                }
            })
            .then();
~~~

Dùng chain fake này với `BoundedSignedBodyReplayWebFilter`, một `MockServerWebExchange` chứa body B và `StepVerifier`:

~~~java
StepVerifier.create(filter.filter(exchange, chain))
        .verifyComplete();

assertEquals(expectedSha256Hex, downstreamBodyDigest.get());
~~~

Đây là **pattern minh họa**, yêu cầu thêm các imports/fixtures/vars `filter`, `exchange` và `expectedSha256Hex` khi tạo test source. `DataBufferUtils.join` trong fake có thể dùng max limit nếu test body lớn. Test cũng cần kiểm error/cancel and leak-detection trên pooled buffers/Netty runtime.

### 20.2. Double subscription là một dấu hiệu đáng ngờ

Nếu một code path vô tình subscribe một response/auth pipeline hai lần, có thể xảy ra:
- Body gốc không phát lại được cho subscription thứ hai.
- Nonce lần thứ hai nhận `REPLAY`.
- Business side effect được chạy hai lần nếu thiếu idempotency.

Thiết kế để một lần HTTP admission chỉ có **một framework-managed subscription**; việc replay body cho downstream nhiều readers là một kỹ thuật buffering cục bộ, không cho phép nhân đôi business request.

## 21. Error handling trên ServerWebExchange: không fail open

Một HTTP exchange có response commit lifecycle. Nếu verifier phát hiện lỗi, phải trả publisher biểu thị **denial/failure** và **không gọi handler**.

### 21.1. Một WebFilter minh họa fail closed

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class ExampleGateWebFilter implements WebFilter {
    private final ExchangeAdmissionService admission;

    public ExampleGateWebFilter(ExchangeAdmissionService admission) {
        this.admission = admission;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        return admission.accept(exchange)
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException(
                                "Admission result missing")))
                .flatMap(accepted -> {
                    if (!accepted) {
                        return Mono.error(
                                new BadCredentialsException(
                                        "Invalid signed request"));
                    }
                    return chain.filter(exchange);
                });
    }

    public interface ExchangeAdmissionService {
        Mono<Boolean> accept(ServerWebExchange exchange);
    }
}
~~~

**Chú ý:** Đoạn này **chưa tự trả HTTP 401**; khi tích hợp thật cần authentication failure handler/entry point hoặc WebExceptionHandler phù hợp. Nếu tự catch exception bằng `onErrorResume`, phải đặt operator quanh **admission step**, không nuốt luôn lỗi từ `chain.filter` rồi biến mọi business error thành “invalid HMAC”.

### 21.2. 401, 403, 413, 5xx và phạm vi

| Trường hợp | Phân loại | Response minh họa |
| --- | --- | --- |
| Missing key ID/signature ở HMAC-required route | Authentication | 401 |
| Unknown/revoked credential | Credential policy | Generic 401 |
| HMAC mismatch | Authentication | Generic 401 |
| Stale timestamp hoặc nonce replay | Admission | Generic 401 |
| Body vượt limit | Resource protection | 413 |
| HMAC đúng nhưng principal thiếu scope | Authorization | 403 |
| Tenant REVOKED | Tenant authorization | 403 hoặc policy status |
| Registry/KMS/Redis outage | Dependency failure, fail closed | 5xx hoặc generic unavailable |
| Controller lỗi | Business failure | Không gán nhầm thành bad MAC |

Codes chỉ minh họa; cần API contract cụ thể, tránh key enumeration và bảo đảm **không side effect khi auth fail**.

### 21.3. Response đã commit

Một filter gọi `response.setStatusCode(...)` sau khi downstream đã ghi body có thể không có hiệu lực. Authentication phải chạy **trước handler/response commit**. Không để verifier chạy nền rồi cố sửa response sau khi business đã bắt đầu.

`response.beforeCommit(...)` phục vụ response lifecycle hook, **không phải chỗ xác minh HMAC** vì quá muộn để ngăn side effects.

## 22. Logging, tracing và metrics từ exchange

`ServerWebExchange` cung cấp correlation metadata:

~~~java
String requestId = exchange.getRequest().getId();
String logPrefix = exchange.getLogPrefix();
String path = exchange.getRequest().getURI().getRawPath();
~~~

`getLogPrefix()` hữu ích khi liên hệ logs. Nhưng không đưa shared secret, expected HMAC, raw Authorization hay full signed request còn replayable vào logs. Raw path cũng có thể chứa identifiers nhạy cảm.

### 22.1. Metrics hữu ích

| Metric | Mục đích |
| --- | --- |
| `hmac_parse_reject_total` | Missing/duplicate/malformed signed headers |
| `hmac_body_size_reject_total` | Body vượt maximum |
| `hmac_mac_mismatch_total` | Chữ ký sai |
| `hmac_key_policy_reject_total` | Key expired/revoked/wrong audience |
| `hmac_registry_error_total` | Registry/KMS unavailable |
| `hmac_nonce_claim_new_total` | Authenticated nonce mới |
| `hmac_nonce_replay_total` | Replay attempts |
| `hmac_nonce_store_unknown_total` | Replay authority outage |
| `hmac_canonical_reject_total` | URI/query/header/body outside contract |
| `hmac_authz_denied_total` | MAC đúng nhưng thiếu quyền |
| `hmac_verify_duration_seconds` | Latency (không là timing proof) |
| `hmac_buffered_body_bytes` | Chi phí buffer |
| `hmac_gateway_semantics_mismatch_total` | Proxy rewrite mismatch |

### 22.2. High-cardinality và thông tin nhạy cảm

`X-Key-Id` chưa authenticated có thể do attacker tạo vô hạn. Không tạo metrics label riêng cho mỗi unknown ID; aggregate theo reason và dùng trusted principal khi phù hợp. Đừng lưu raw signed body trong `exchange.getAttributes()` rồi log toàn bộ map; attributes có thể bị truy cập bởi nhiều components trong request.

### 22.3. Security audit

Audit có thể ghi correlation ID, policy/key revision, principal sau authentication, route và outcome đã redacted. Khi key bị revoke, đo effective reject time **trên mọi verifier nodes**, không chỉ lúc registry đổi status.

## 23. Multi-client, multi-tenant, proxy và key lifecycle

Một HMAC WebFlux API có thể phục vụ:

~~~text
Client A -> key A3 -> secret KA3 -> principal A -> tenant A
Client B -> key B1 -> secret KB1 -> principal B -> tenant B
Gateway G -> WebFlux nodes W1, W2, W3
~~~

Với **exact key lookup**, A3 không thể được xác thực bằng secret B1. Key B1 hợp lệ cũng không cấp quyền trên tenant A nếu thiếu trusted delegation.

### 23.1. Trạng thái credential

| Key state | Tag mathematically correct | Expected admission |
| --- | --- | --- |
| PROVISIONED | Có thể | Deny trước activation |
| ACTIVE, trong validity interval | Có | May authenticate |
| ACTIVE, expired | Có thể | Deny |
| RETIRING, trong approved overlap | Có | May verify theo policy |
| RETIRING, hết verifyUntil | Có thể | Deny |
| DISABLED | Có thể | Deny |
| REVOKED | Có thể | Deny |

Không dùng client-signed timestamp trước revokedAt để bypass REVOKED; bên có stolen secret có thể ký lùi timestamp trong freshness window.

### 23.2. Gateway retry và nonce

Gateway có thể retry một signed request tới W2 sau khi W1 đã claim nonce N. Nếu shared store ghi `NEW` ở lần đầu, retry phải là `REPLAY` theo contract. Business cần idempotency key/operation status độc lập với nonce. Không tắt anti-replay để gateway retries “luôn thành công”.

### 23.3. Một principal có quyền trên nhiều tenants

Principal P có thể được cấp grants vào tenant A và B. HMAC xác thực P, nhưng quyền với A/B phụ thuộc trusted grants, resource ownership và tenant state. Tenant A REVOKED vẫn phải deny A dù HMAC của P đúng và nonce mới. Không lấy tenant từ `X-Tenant-Id` thành quyền chỉ vì header được signed.

### 23.4. Multi-region failover

Nonce store per-instance hoặc Redis primary async failover có thể tạo replay gap. Credential registry stale ACTIVE có thể chấp nhận key vừa revoked. Cache revision fencing, authoritative status/leases và fail-closed policy cần được thiết kế theo security guarantee, rồi test partition/failover/rollback.

### 23.5. WebFlux không biến blocking dependency thành non-blocking

Nếu verifier dùng đồng bộ JDBC/Redis/KMS bên trong `flatMap`, nó vẫn block event loop. Ưu tiên reactive clients/drivers. Với dependency buộc phải blocking, offload **chỉ stage blocking hẹp** sang `Schedulers.boundedElastic()` có capacity/timeouts rõ; kiểm load và backpressure.

Không “chữa” mọi blocking bằng cách đổi scheduler toàn HTTP request một cách mù quáng.

## 24. Ma trận lỗi đặc thù ServerWebExchange

| Tình huống | Lỗi thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| Converter đọc raw body | Handler nhận empty | Decorator replay exact bytes |
| Body publisher subscribed twice | Network stream không repeatable | Compose once, kiểm subscription count |
| Join body không giới hạn | Memory exhaustion | Bounded join + 413 |
| Joined pooled buffer không release | Netty direct-memory leak | Test release/ownership |
| Decorator trả consumed DataBuffer | Downstream nhận empty/malformed | New buffer per subscription |
| `getQueryParams()` thay raw query | Canonicalization mismatch | Versioned raw-query contract |
| Duplicate `X-Key-Id` | Key identity confusion | Reject trusted ingress |
| Gateway rewrites path | Client/backend sign URI khác nhau | Signing boundary rõ |
| HTTP/2 authority khác Host | Wrong signed authority | Gateway tests |
| `X-Forwarded-Host` từ Internet | Spoofed canonical host | Strip/overwrite trusted proxy |
| Blocking Redis/JDBC in WebFilter | Event-loop stalls | Reactive I/O or bounded offload |
| Mono.empty from registry | Missing key treated as optional | Convert absent ID to reject |
| Mono.empty from nonce claim | Uncertain admission | Fail closed |
| onErrorResume calls chain | Fail-open outage | Không tiếp tục request |
| Revoked key | Tag đúng vẫn accept | Enforce key policy |
| Wrong secret selected | Cross-client impersonation | Exact key ID mapping |
| Nonce local per pod | Cross-pod replay | Shared atomic authority |
| Key A/B same nonce text | False-positive collision | Key-scoped namespace |
| ThreadLocal auth in reactive | Missing/leaked identity | Reactor SecurityContext |
| Exchange attribute as principal | Untrusted tenant/role | Trusted authenticated result only |
| Optional converter on HMAC-required route | Anonymous bypass | Required chain policy |
| Security chain wrong order | HMAC not invoked | WebTestClient integration |
| Body replay after parsing middleware | Signed bytes changed | Test filter order |
| Async/error path double verifies | Nonce replay on error | One security admission |
| Tenant revoked after queue admission | Later side effects | Revalidate tenant policy |
| Handler executes other URI than signed | Authorization bypass | Sign what you execute |
| Logs contain body/signature | Replay/privacy exposure | Redacted telemetry |

### 24.1. Các thuộc tính kiểm thử bắt buộc

Tối thiểu, một signed request hợp lệ phải qua: strict HTTP parsing → exact credential lookup → HMAC full-tag → timestamp freshness → atomic nonce claim → trusted principal → authorization → business. Các đường lỗi phải **không chạy handler** trừ những lỗi authorization chỉ được xử lý ở lớp deny. Với streaming/large bodies, phải định nghĩa một signing flow khác thay vì nâng max buffer vô hạn.

### 24.2. Sơ đồ xét lỗi

~~~mermaid
flowchart TD
    A[Receive exchange] --> B{Signed route?}
    B -- No --> Z[Other security chain]
    B -- Yes --> C{Headers and body valid?}
    C -- No --> E[Reject]
    C -- Yes --> D{Exact key allowed?}
    D -- No or unavailable --> E
    D -- Yes --> F{HMAC matches full tag?}
    F -- No --> E
    F -- Yes --> G{Timestamp fresh?}
    G -- No --> E
    G -- Yes --> H{Nonce atomically NEW?}
    H -- No or unknown --> E
    H -- Yes --> I[Trusted authenticated context]
    I --> J{Authorized tenant/action/resource?}
    J -- No --> K[Deny authorization]
    J -- Yes --> L[Business execution]
~~~

Luồng này diễn tả logic. Một production WebFlux implementation có thể tổ chức body capture và policy checks theo thứ tự khác để giảm resource exhaustion, nhưng phải giữ đúng invariants và không tạo side effects trước authentication/authorization.

## 25. Checklist triển khai ServerWebExchange cho HMAC

### 25.1. HTTP exchange và canonical boundary

- [ ] HMAC mechanism chạy trên **Spring WebFlux reactive stack**, không nhầm Servlet Filter.
- [ ] `SecurityWebFilterChain` chọn đúng signed routes trước catch-all chain.
- [ ] Method, URI/raw path/raw query, signed headers và body bytes được định nghĩa trong một contract versioned.
- [ ] `exchange.getRequest().getURI().getRawPath()` không bị coi là raw wire bytes trước mọi gateway rewrites.
- [ ] Canonical path/query match cùng resource semantics mà handler thực thi.
- [ ] Proxy `X-Forwarded-*` chỉ được tin nếu trusted gateway strip/overwrite và bảo vệ internal channel.
- [ ] HTTP header names case-insensitive; duplicate signature/key ID fields bị reject tại trusted ingress.
- [ ] Key ID, timestamp, nonce, audience, relevant headers/body digest được ký.
- [ ] Không nhận client-provided canonical string/body hash làm authority.
- [ ] Không parse/re-serialize JSON thay raw body signing nếu contract ký bytes.
- [ ] Không thử nhiều canonicalization variants hoặc secrets khi MAC mismatch.

### 25.2. Reactive body/response lifecycle

- [ ] Không gọi `block()` hoặc tự `subscribe()` trong WebFilter/authentication flow.
- [ ] Body publisher được capture có kiểm soát trước khi handler dùng.
- [ ] `DataBufferUtils.join` có giới hạn bytes cho signed JSON.
- [ ] Joined `DataBuffer` được release theo ownership sau copy.
- [ ] Body rỗng tương ứng zero bytes, không thay bằng JSON null hoặc string khác.
- [ ] `ServerHttpRequestDecorator` cung cấp **cùng raw bytes** cho converter và controller.
- [ ] Mỗi subscription downstream nhận buffer đọc được với lifecycle đúng.
- [ ] Request body memory/buffer retention không vượt capacity budget.
- [ ] Cancellation, timeout, client disconnect và pooled memory được test.
- [ ] Streaming/multipart/large upload có signing contract riêng, không buffer vô hạn.
- [ ] Response lỗi xác thực được quyết định trước handler/response commit.
- [ ] Không catch downstream business exceptions thành authentication failure.

### 25.3. Spring Security reactive authentication

- [ ] Dùng `AuthenticationWebFilter` + `ServerAuthenticationConverter` + `ReactiveAuthenticationManager` khi phù hợp.
- [ ] Converter tạo **unauthenticated token**, không tạo role/principal đã authenticated.
- [ ] HMAC-required route không được bypass bằng `Mono.empty()` từ converter.
- [ ] Exact credential lookup và trusted principal creation nằm trong manager/verifier.
- [ ] `ReactiveSecurityContextHolder` được dùng đúng Reactor Context, không global mutable identity.
- [ ] Authentication failure dừng chain, public error không leak key/secret/expected tag.
- [ ] Authentication thành công **không** bỏ qua tenant/resource authorization.
- [ ] WebFilter order/body-capture order được xác minh bằng integration tests.
- [ ] WebFlux không phụ thuộc `jakarta.servlet`/`OncePerRequestFilter`.
- [ ] CSRF/session policy phù hợp API threat model; không disable chỉ theo thói quen.

### 25.4. HMAC, replay và credential lifecycle

- [ ] HMAC SHA-256 expected tag được tính từ đúng signed canonical bytes.
- [ ] Presented tag strict Base64URL unpadded, full 32 bytes, canonical encoding.
- [ ] So full MAC bằng primitive phù hợp, không dùng prefix/early-exit custom loop.
- [ ] HMAC key ID là selector, không phải trusted principal.
- [ ] Credential ACTIVE/RETIRING/REVOKED/wrong audience/expiry được enforce.
- [ ] Mỗi client/key ID chọn đúng secret version; không fallback sang key khác.
- [ ] Timestamp freshness dựa vào server clock, future/past skew có policy.
- [ ] Nonce claim chỉ sau MAC đúng, tránh unauthenticated poisoning.
- [ ] Replay namespace xác định version/audience/key ID/nonce rõ ràng.
- [ ] Shared atomic replay authority có TTL đủ dài cho freshness window.
- [ ] Redis/KMS/registry outage hoặc unknown replay claim không fail open.
- [ ] Multi-node/failover/replication consistency có guarantees và tests thật.
- [ ] Compromised secret được revoke/rotate; timestamp+nonce không chặn bên có secret ký request mới.
- [ ] Business idempotency không bị nhầm với nonce replay protection.

### 25.5. Test và vận hành

- [ ] Có independent RFC 4231 HMAC primitive fixtures.
- [ ] Có golden canonical byte fixtures cho protocol V1, không chỉ signer/verifier dùng chung một hàm.
- [ ] Có `StepVerifier` tests cho manager happy/failure/replay.
- [ ] Có `WebTestClient` tests cho exchange, body replay và security chain.
- [ ] Có tests body empty/max/max+1, cancel/error và DataBuffer release.
- [ ] Có ingress tests HTTP/1.1–HTTP/2 và raw duplicated headers.
- [ ] Có proxy rewrite/host/authority/URI encoded tests.
- [ ] Có cross-client secret và cross-tenant denial tests.
- [ ] Có registry outage, nonce store outage, key rotation/revocation tests.
- [ ] Có performance/load test chứng minh không block event-loop.
- [ ] Logs redacted, metrics bounded cardinality, request correlation ID đáng tin.
- [ ] Có incident runbook và xác nhận revoke có hiệu lực trên toàn cluster.

## 26. Bài tập thực hành

### Bài tập 1 — Nhận diện dữ liệu của ServerWebExchange

Tạo một `WebFilter` quan sát method, `getURI().getRawPath()`, `getURI().getRawQuery()`, `getHeaders()` và `getRequest().getId()`. Gắn namespaced correlation ID vào `exchange.getAttributes()` nhưng không log signature/secret/body. Nêu vì sao dữ liệu request này vẫn chưa là authenticated identity.

### Bài tập 2 — Raw query vs parsed query

Gửi hai URIs có query `a=%2F&b=1` và `a=%2f&b=1`. So sánh raw query với `getQueryParams()`. Xác định contract sẽ ký raw encoding hay một canonical query representation; viết golden fixtures và reject ambiguity.

### Bài tập 3 — Duplicate headers

Gửi `X-Key-Id: A3` và `x-key-id: B1`. Test adapter/WebFlux khi cả hai values còn hiện diện phải reject. Sau đó test qua ingress thật vì gateway có thể merge/drop duplicate trước khi backend nhìn thấy.

### Bài tập 4 — Body bị tiêu thụ

Viết filter cố ý đọc `exchange.getRequest().getBody()` rồi gọi chain với exchange gốc. Quan sát handler nhận empty hoặc lỗi. Thay bằng `ServerHttpRequestDecorator` và kiểm handler nhận đúng byte-for-byte payload B.

### Bài tập 5 — Body size và release

Dùng `BoundedSignedBodyReplayWebFilter` với body 0, 1, 65.536, 65.537 bytes. Assert response/trạng thái xử lý theo contract và không có pooled-buffer leak. Bổ sung cancellation test sau khi đã phát một phần chunks.

### Bài tập 6 — Không tự subscribe

Tạo một `WebFilter` gọi `verifier.verify(exchange).subscribe()` rồi lập tức `chain.filter(exchange)`. Dùng controlled publisher để chứng minh handler có thể chạy trước auth. Refactor thành `flatMap`/`Mono.defer` để handler chỉ chạy sau verified result.

### Bài tập 7 — Converter và AuthenticationWebFilter

Cài `HmacExchangeConverterV1`, dùng bounded body replay adapter trước security chain, thêm `AuthenticationWebFilter` có matcher HMAC-only. Đảm bảo missing signed fields **fail**, không chuyển thành anonymous allowed.

### Bài tập 8 — Exact credential lookup

Tạo keys A3/KA3 và B1/KB1. Dùng HMAC KA3 với key ID B1, assert reject; unknown key ID với tag đúng dưới KA3 vẫn reject. Không cho manager thử nhiều secrets để tìm một tag match.

### Bài tập 9 — Replay ở nhiều pods

Dùng hai WebFlux instances cùng shared Redis replay authority. Gửi 100 copies signed request có nonce N đồng thời. Kiểm at most one successful nonce claim trong configured guarantee; test primary failover/replication uncertainties.

### Bài tập 10 — Key bị revoke nhưng MAC đúng

Tạo credential REVOKED cùng secret mà attacker có thể biết; ký fresh timestamp/nonce. Xác định manager từ chối do key policy, không dựa vào HMAC mismatch. Sau đó rotate sang key ID/secret mới độc lập.

### Bài tập 11 — Tenant authorization

Key A3 ACTIVE ký request có payload nhắm resource tenant B. HMAC và replay có thể pass nhưng authorization phải deny trừ khi có trusted delegated grant. Nêu vì sao `X-Tenant-Id` có HMAC integrity cũng không tự cấp quyền.

### Bài tập 12 — Event-loop blocking

Tạo fake registry blocking delay trong `flatMap`. Dùng load test/BlockHound nếu phù hợp và thread metrics để thấy tác động. Thay bằng reactive registry hoặc isolate blocking stage qua bounded scheduler. So sánh timeout và throughput.

### Bài tập 13 — Reactive error semantics

Cho credential registry trả `Mono.empty()` (unknown key), `Mono.error(...)` (outage) và nonce store trả `UNKNOWN`. Verify mọi trường hợp fail closed, nhưng internal reason codes vẫn phân biệt. Không dùng `onErrorResume(... -> chain.filter(exchange))`.

### Bài tập 14 — Gateway URI rewrite

Client ký public path `/public/signed-api/orders` nhưng backend thấy `/signed-api/orders`. Chọn signing boundary đúng và test end-to-end; không thử nhiều canonical paths cho tới khi MAC match.

### Bài tập 15 — WebFlux SecurityContext

Sau successful HMAC auth, đọc `ReactiveSecurityContextHolder.getContext()` trong handler. Sau một request B invalid, kiểm không có identity của A còn sót lại; test concurrent requests qua Reactor schedulers.

### Bài tập 16 — Những gì WebTestClient chưa chứng minh

Một `WebTestClient.bindToApplicationContext` test pass với JSON body hợp lệ. Nêu ít nhất năm rủi ro vẫn cần ingress/real-server tests: HTTP framing, HTTP/2 authority, proxy rewrite, pooled DataBuffer lifecycle, distributed replay, request cancellation.

## 27. Câu hỏi tự kiểm tra

1. **ServerWebExchange là gì?** HTTP request/response và metadata của một exchange trong Spring WebFlux.
2. **Nó có tự tạo authenticated principal không?** Không; Spring Security/verifier phải xác thực theo protocol.
3. **Lấy HTTP method từ đâu?** `exchange.getRequest().getMethod()`.
4. **Lấy raw path/query từ đâu?** `getRequest().getURI().getRawPath()/getRawQuery()` theo server-visible URI.
5. **Raw path trong exchange có luôn là bytes gốc từ Internet không?** Không; gateway có thể đã rewrite.
6. **Vì sao không dùng getQueryParams().toString() mặc định để ký?** Parsing/decoding/order có thể khác raw signing contract.
7. **getHeaders().getFirst() có bảo đảm chỉ một header không?** Không, cần check multiplicity/ingress ambiguity.
8. **getPrincipal() có giá trị trước authentication không?** Có thể empty; đừng coi caller header là principal.
9. **getAttributes() có thay ReactiveSecurityContextHolder không?** Không; attributes là local metadata, không tự là trusted security identity.
10. **getSession() có nên lưu HMAC auth cho mọi request không?** Thông thường HMAC per-request là stateless; cần policy rõ nếu dùng session.
11. **Request body của WebFlux là gì?** `Flux<DataBuffer>`.
12. **Vì sao không gọi block() trong WebFilter?** Có thể chặn event-loop và phá reactive throughput/lifecycle.
13. **Vì sao không gọi subscribe() rồi tiếp tục chain?** Xác minh chạy song song, lỗi không chặn handler và body stream có thể bị tranh chấp.
14. **DataBuffer có cần release không?** Có khi component nhận ownership một pooled buffer; ví dụ joined buffer được release sau copy.
15. **DataBufferUtils.join có rủi ro gì?** Buffering memory lớn, cần max size và cancellation/error handling.
16. **ServerHttpRequestDecorator dùng để làm gì?** Thay/bao request view, ví dụ replay body cho downstream.
17. **exchange.mutate() có tự xác thực request không?** Không, chỉ tạo/điều chỉnh exchange view.
18. **Flux.defer có ích gì trong body replay?** Tạo publisher/buffer cho mỗi subscription của downstream.
19. **Nếu body bị filter đọc hết mà không decorate thì sao?** Controller có thể nhận empty/unreadable body.
20. **Body hash client tự gửi có đáng tin không?** Không nếu server không tính lại raw bytes và bind trong HMAC.
21. **AuthenticationWebFilter khác Servlet OncePerRequestFilter như thế nào?** Là reactive Spring Security mechanism, không dùng Servlet API.
22. **ServerAuthenticationConverter trả gì?** Yêu cầu authentication chưa trusted, thường dưới dạng `Mono<Authentication>`.
23. **ReactiveAuthenticationManager làm gì?** Xác minh credential và tạo trusted Authentication hoặc báo failure.
24. **Mono.empty của converter luôn là lỗi?** Không trong optional scheme; nhưng HMAC-required route phải không bypass.
25. **Mono.empty từ registry có được coi như ACTIVE không?** Không, đó là unknown key hoặc error adapter cần xử lý.
26. **Replay store trong một pod có đủ không?** Không cho multi-pod HTTP admission.
27. **HMAC đúng có tự cấp quyền trên tenant B không?** Không, phải kiểm authorization.
28. **Key bị REVOKED nhưng tag đúng có được nhận không?** Không.
29. **Timestamp và nonce có chặn bên đã có stolen secret tạo request mới không?** Không, cần revocation/rotation.
30. **MessageDigest.isEqual chứng minh toàn verifier constant-time không?** Không; chỉ là primitive so MAC bytes.
31. **WebTestClient in-process thay được gateway raw HTTP tests không?** Không.
32. **Một body decorator có tự tạo exactly-once business effects không?** Không; business idempotency tách biệt.
33. **Khi Redis nonce claim UNKNOWN thì sao?** Fail closed, không chạy business.
34. **Vì sao cần test async cancellation và pooled DataBuffers?** Để tránh leak/double subscription/mất body khi request bị hủy.
35. **Bài học quan trọng nhất?** Ký và xác minh đúng semantics của request đang thực thi, giữ reactive body/context/lifecycle và fail closed ở mọi bảo vệ.

## 28. Tài liệu tham khảo và hướng đọc thêm

- **Spring Framework Reference — WebFlux / WebHandler API / WebFilter / ServerWebExchange.** HTTP reactive exchange và middleware.
- **Spring Framework API — ServerHttpRequestDecorator, ServerWebExchange.Builder và DataBufferUtils.** Request decoration, mutable view, buffer ownership và data flow.
- **Spring Framework Reference — WebFlux HTTP codecs, request body, streaming và backpressure.** Hạn chế của full-body buffering.
- **Spring Security Reference — WebFlux Security / AuthenticationWebFilter / SecurityWebFilterChain.** Reactive authentication filters và request matching.
- **Spring Security API — ServerAuthenticationConverter, ReactiveAuthenticationManager, ReactiveSecurityContextHolder.** Các điểm mở rộng chính.
- **Reactor Reference Guide — Mono, Flux, Context, Backpressure và StepVerifier.** Reactive composition và testing.
- **Spring Test — WebTestClient.** HTTP handler/filter integration tests.
- **Spring Data Redis Reactive API — ReactiveStringRedisTemplate và setIfAbsent với TTL.** Replay key admission primitive và giới hạn failover.
- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng shared-secret MAC.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Independent known-answer tests.
- **RFC 9110, RFC 9112, RFC 9113 — HTTP semantics, HTTP/1.1 và HTTP/2.** Header/URI/message framing, proxy conversion.
- **RFC 3986 — URI Generic Syntax.** Percent encoding, path/query representation trong canonicalization.
- **OWASP API Security và Secrets Management guidance.** Xác thực, tenant authorization, key rotation và log hygiene.
- **Java SE 17 — javax.crypto.Mac, SecretKeySpec, MessageDigest.isEqual, Clock, HexFormat.** Crypto/time APIs dùng trong ví dụ.

## 29. Tổng kết

**ServerWebExchange là trung tâm của HTTP reactive request processing**, không phải cơ chế xác thực. Nó cung cấp method, URI, headers, body publisher, response, exchange attributes và request-scoped metadata để Spring WebFlux/Spring Security dựng các cơ chế như HMAC request authentication.

Đối với HMAC, những quyết định quan trọng nhất là: **đặt signing boundary đúng với gateway/router**, strict parse key ID/timestamp/nonce/tag, ký đúng canonical bytes của method/URI/headers/raw body, **đọc body theo reactive lifecycle**, nếu cần thì replay chính xác bytes cho downstream bằng decorator, và tuyệt đối không block event-loop hoặc tạo subscription ngoài chain. `AuthenticationWebFilter` và `ReactiveAuthenticationManager` nên quản lý authentication, còn key policy, replay authority, tenant authorization và business idempotency giữ ranh giới rõ ràng.

Một request chỉ được đi tới business khi tag HMAC khớp secret đúng key ID, credential còn hợp lệ, timestamp fresh, nonce được claim một lần và principal được authorize cho action/resource. Những nguyên tắc này phải được xác minh bằng **StepVerifier, WebTestClient và tests qua gateway/multi-node thực**, kể cả khi body rỗng, request bị cancel, key bị revoke, Redis outage hoặc URI bị proxy rewrite.





