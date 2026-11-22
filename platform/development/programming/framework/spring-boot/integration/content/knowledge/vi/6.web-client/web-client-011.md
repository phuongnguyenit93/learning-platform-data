# Kiểm soát thử lại, token và địa chỉ đích để không rò rỉ thông tin

## 1. Vấn đề trong luồng tích hợp WebClient

Trong **SPRING_BOOT_INTEGRATION**, `WebClient` thường là adapter gọi HTTP từ một dịch vụ Spring Boot đến API đối tác hoặc dịch vụ nội bộ. Phản hồi của API đó có thể quyết định việc ghi cơ sở dữ liệu, cập nhật cache, phát thông điệp qua broker hoặc chuyển một message sang bước tiếp theo của Spring Integration. Vì vậy, việc gọi lại sau lỗi phải được xem xét cùng với **hợp đồng dữ liệu, giao dịch, xử lý trùng lặp và khả năng quan sát** của cả luồng.

Ba thành phần tưởng như độc lập có thể kết hợp thành sự cố bảo mật:

1. **Retry:** Một lỗi tạm thời khiến cùng yêu cầu HTTP được gửi thêm nhiều lần.
2. **Token:** Yêu cầu mang `Authorization: Bearer ...` hoặc một thông tin xác thực khác.
3. **Địa chỉ đích:** URL được ghép từ cấu hình, tham số nghiệp vụ hoặc `Location` trong phản hồi chuyển hướng.

Nếu để URL thay đổi tùy ý, mỗi lần retry có thể gửi lại token và dữ liệu nghiệp vụ đến một máy chủ không được phép. Nếu log toàn bộ request/response, token còn có thể xuất hiện trong log, trace hoặc thông điệp lỗi. Retry không tự tạo ra lỗ hổng, nhưng **làm tăng số lần gửi và khuếch đại hậu quả khi một yêu cầu đã bị định tuyến sai**.

### Mục tiêu sau bài học

- Chỉ retry những lỗi có khả năng hồi phục, với số lần và thời gian chờ hữu hạn; nhận diện thao tác nào an toàn để gửi lại.
- Cấp token phù hợp với đúng API, quyền truy cập (`scope`) và đối tượng nhận (`audience`); tránh phát tán qua URL, redirect và log.
- Xác định, kiểm tra và giới hạn địa chỉ HTTP đích; hiểu vì sao `baseUrl` chưa đủ để khóa máy chủ nhận request.
- Viết kiểm thử chứng minh request không đi sang host lạ, không phát tán token và không retry quá ngân sách.

## 2. Mô hình đe dọa: sự cố bắt đầu từ đâu?

Xét luồng tra cứu đơn hàng tại một API đối tác:

```text
HTTP request vào Spring Boot
    → kiểm tra orderId
    → lấy access token cho API đối tác
    → WebClient GET /v1/orders/{orderId}
    → nhận kết quả
    → cập nhật trạng thái / trả DTO / phát sự kiện
```

Các vị trí dễ xảy ra rò rỉ:

| Điểm phát sinh | Ví dụ không an toàn | Hậu quả |
| --- | --- | --- |
| URL động | `client.get().uri(userSuppliedUrl)` | SSRF: gửi request đến máy chủ lạ, địa chỉ nội bộ hoặc metadata service |
| Token dùng chung | Gắn `Authorization` mặc định trên một WebClient dùng cho nhiều đối tác | Sai API có thể nhận token vốn chỉ dành cho API khác |
| HTTP redirect | Tự động theo `Location` đến host ngoài danh sách cho phép | Dữ liệu hoặc credential có nguy cơ đi qua đích không được kiểm soát |
| Retry rộng | `retry(10)` cho mọi exception, kể cả 401/403 và POST tạo tài nguyên | Tăng tải, lặp thao tác, phát tán thêm dữ liệu nhạy cảm |
| Log HTTP | Bật wiretap ghi header/body hoặc log toàn bộ request | Token, cookie và payload nhạy cảm nằm trong log/tracing |
| Token qua query | `?access_token=...` hoặc truyền token trong đường dẫn | Token xuất hiện ở URL, proxy, access log và báo cáo giám sát |

Một URL nguy hiểm không nhất thiết trông bất thường. Ví dụ, `https://api.partner.example.evil.test` không phải host `api.partner.example`; `https://api.partner.example@evil.test/path` có host thực là `evil.test`. Địa chỉ `http://169.254.169.254/` và các địa chỉ loopback/private cũng là những mục tiêu cần chặn khi đầu vào có thể điều khiển URL.

**Nguyên tắc:** Quyền gọi ra mạng, quyền mang token và quyền gửi lại request phải được giới hạn riêng, rồi kiểm chứng cùng nhau ở ranh giới WebClient.

## 3. Kiểm soát địa chỉ đích trước khi phát request

### 3.1. Tạo WebClient chuyên dụng cho từng API

Nên cấu hình mỗi downstream quan trọng bằng một WebClient riêng, với base URL lấy từ cấu hình đã được kiểm soát. Các method nghiệp vụ chỉ nhận **định danh hoặc dữ liệu**, không nhận một URL hoàn chỉnh từ người dùng.

```java
@Configuration
class PartnerHttpConfig {
    private static final String PARTNER_HOST = "partner-api.example.net";

    @Bean("partnerWebClient")
    WebClient partnerWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .followRedirect(false)
            .responseTimeout(Duration.ofSeconds(2));

        return builder.clone()
            .baseUrl("https://" + PARTNER_HOST)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .filter((request, next) -> {
                URI destination = request.url();

                boolean allowed =
                    "https".equalsIgnoreCase(destination.getScheme())
                    && PARTNER_HOST.equalsIgnoreCase(destination.getHost())
                    && (destination.getPort() == -1 || destination.getPort() == 443)
                    && destination.getRawUserInfo() == null;

                if (!allowed) {
                    return Mono.error(
                        new IllegalArgumentException("Downstream destination rejected")
                    );
                }
                return next.exchange(request);
            })
            .build();
    }
}
```

Các import tiêu biểu: `java.net.URI`, `java.time.Duration`, `reactor.core.publisher.Mono`, `reactor.netty.http.client.HttpClient`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.http.client.reactive.ReactorClientHttpConnector` và `org.springframework.web.reactive.function.client.WebClient`. Đây là cấu hình minh họa cho ứng dụng dùng Spring WebFlux WebClient và Reactor Netty; `example.net` là tên miền giả định cần thay bằng đích thực được phép.

**Giải thích từng lớp bảo vệ:**

- `baseUrl(...)` giúp tạo URI tương đối nhất quán. Nó **không phải rào chắn bảo mật**: truyền một URI tuyệt đối vào `uri(...)` có thể bỏ qua base URL.
- Filter kiểm tra URL cuối cùng trong `ClientRequest` trước khi trao request cho connector. Nó từ chối sai scheme, host, port và user-info. So sánh **host đã được phân tích từ URI**, không dùng `startsWith` hay `contains` trên URL thô.
- `followRedirect(false)` không cho HTTP client tự mở một kết nối mới đến đích trong `Location`. Phản hồi 3xx sẽ được xử lý thành lỗi ở tầng nghiệp vụ.
- `responseTimeout` giới hạn thời gian chờ hoạt động nhận phản hồi của kết nối. Nó **không thay thế** ngân sách thời gian cho toàn bộ chuỗi token → gọi HTTP → retry.

Trong môi trường thực tế, nên đặt allowlist host và port dưới cấu hình triển khai có kiểm soát, xác thực cấu hình ngay khi khởi động và giới hạn đường ra mạng (egress firewall, service mesh hoặc proxy). Một filter Java không thay thế được chính sách mạng: DNS rebinding, DNS thay đổi giữa lúc kiểm tra và lúc kết nối, proxy và redirect là các yếu tố cần được xử lý tại tầng kết nối/hạ tầng nếu hệ thống thực sự cho phép URL do người dùng cung cấp.

### 3.2. Đối xử với tham số nghiệp vụ như dữ liệu

Không nhận `targetUrl` rồi đưa thẳng vào `WebClient.uri(...)`. Với yêu cầu lấy một đơn hàng, chỉ nhận `orderId` và dựng tuyến cố định:

```java
// Ưu tiên endpoint cố định và ràng buộc định dạng định danh.
if (orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
    return Mono.error(new IllegalArgumentException("Invalid orderId"));
}

return client.get()
    .uri(builder -> builder.pathSegment("v1", "orders", orderId).build())
    .retrieve()
    .bodyToMono(PartnerOrder.class);
```

`pathSegment` thể hiện rõ rằng `orderId` là một đoạn đường dẫn; việc kiểm tra định dạng còn ngăn các giá trị bất thường như `..`, dấu `/` hoặc một URL hoàn chỉnh. Đối với giá trị tìm kiếm không thuộc đường dẫn, dùng `queryParam("q", value)` để thư viện mã hóa tham số đúng ngữ cảnh. Không đặt access token, API key hoặc mật khẩu trong path/query.

Nếu nghiệp vụ buộc phải gọi một trong nhiều endpoint, hãy ánh xạ **mã đối tác đã định nghĩa trước → endpoint tin cậy**, rồi chọn WebClient tương ứng; không biến mã đối tác thành chuỗi URL. Nếu bắt buộc hỗ trợ URL bên ngoài, việc xác thực scheme/host/port, DNS/IP, redirect và egress phải có thiết kế và kiểm thử riêng.

## 4. Cấp token đúng đích và đúng thời điểm

### 4.1. Token phải có phạm vi sử dụng

Access token là thông tin xác thực có thể bị sử dụng lại nếu bị lộ. Trước khi gửi token, cần trả lời:

| Câu hỏi | Kiểm soát cần có |
| --- | --- |
| Ai phát hành? | Identity provider hoặc token service tin cậy |
| Cấp cho ai? | `audience` là resource server/API đích, không phải mọi hệ thống |
| Được làm gì? | `scope` / quyền tối thiểu cho thao tác cụ thể |
| Còn hiệu lực không? | Theo dõi hạn token, cache và refresh an toàn trong token provider |
| Gửi qua đâu? | HTTPS đến host đã cho phép, qua header `Authorization` |
| Ai được xem? | Không ghi token trong log, trace, exception, metric tag hoặc URL |

Trong tích hợp server-to-server, một lựa chọn thường dùng là OAuth2 `client_credentials` thông qua cơ chế quản lý authorized client của Spring Security. Tách trách nhiệm lấy/cập nhật token khỏi nghiệp vụ gọi HTTP. Không đưa token từ request của người dùng đang đăng nhập sang API khác chỉ vì token ấy sẵn có trong security context: token có thể mang `audience` hoặc quyền không phù hợp cho downstream.

Đặc biệt thận trọng với các cấu hình tự động chọn authorized client mặc định (`setDefaultOAuth2AuthorizedClient(true)` trong những môi trường Spring Security hỗ trợ cách cấu hình này), hoặc `defaultHeader("Authorization", ...)` trên WebClient dùng chung. Những lựa chọn này có thể gửi credential ngoài ý định khi cùng client được dùng với URL khác. Với API quan trọng, chọn registration/token provider có chủ đích và gắn token trên request đã xác định đích.

### 4.2. Khi nhận 401/403

- **401 Unauthorized:** Không thử lại cùng một token theo vòng lặp. Kiểm tra nguyên nhân, để token provider quản lý hết hạn/refresh; nếu nghiệp vụ cho phép, làm mới rồi thử lại tối đa **một lần có kiểm soát** với cùng host và scope.
- **403 Forbidden:** Thường là không đủ quyền, sai scope hoặc policy từ chối. Không retry tự động.
- **Redirect đến trang login:** Với API mang bearer token, xem đây là phản hồi bất thường; không theo redirect hay gửi lại token sang trang đó.

Không đưa nội dung token hay header `Authorization` vào thông điệp của exception, kể cả khi trả lỗi để phục vụ debug.

## 5. Thiết kế retry có giới hạn và có điều kiện

### 5.1. Retry là gửi lại tác động

Trong Reactor, `retryWhen(...)` **đăng ký lại (resubscribe) nguồn Mono/Flux ở phía trước nó** sau khi nguồn phát lỗi. Với WebClient, điều này thường dẫn đến một request HTTP mới. Nếu chuỗi phía trước còn có bước ghi dữ liệu, phát sự kiện hoặc gọi API khác, những bước ấy cũng có thể chạy lại.

| Trường hợp | Khuyến nghị mặc định | Lý do |
| --- | --- | --- |
| GET thuần đọc, 429 | Retry giới hạn, chú ý `Retry-After` | Có thể là giới hạn tốc độ tạm thời |
| GET thuần đọc, 502/503/504 | Retry với exponential backoff + jitter | Lỗi gateway/service thường có tính tạm thời |
| GET trả 400/404/401/403 | Không retry tự động | Thay đổi thời gian chờ thường không sửa được yêu cầu/quyền |
| POST tạo đơn hàng/thanh toán | Không retry mù | Có thể đã được xử lý trước khi client mất kết nối |
| PUT/PATCH/DELETE | Xét riêng ngữ nghĩa và contract của API | Độ an toàn phụ thuộc idempotency, version/ETag và side effect |
| Timeout/đứt kết nối sau khi đã gửi request | Cần đánh giá riêng | Client không biết server đã thực thi hay chưa |

**Idempotent** nghĩa là thực hiện một thao tác nhiều lần cho cùng kết quả/trạng thái có thể quan sát được theo hợp đồng, không đơn thuần dựa vào tên HTTP method. Với lệnh ghi, cần idempotency key do server hỗ trợ, bảng chống trùng, mã yêu cầu duy nhất, optimistic locking hoặc cơ chế deduplication. Nếu API không cam kết chống trùng, việc retry sau timeout có thể tạo hai giao dịch.

### 5.2. Các thành phần của một chính sách retry

1. **Điều kiện:** Chỉ một số mã trạng thái hoặc exception tạm thời, đã được phân loại rõ.
2. **Giới hạn số lần:** Phân biệt số lần *retry* với tổng số *attempt*. `Retry.backoff(2, ...)` nghĩa là tối đa **hai lần thử lại**, tổng tối đa ba request.
3. **Backoff + jitter:** Khoảng chờ tăng dần và có độ lệch ngẫu nhiên để nhiều instance không đồng loạt bắn lại.
4. **Ngân sách thời gian:** Deadline cho toàn bộ cuộc gọi; giới hạn theo từng attempt không đủ nếu retry kéo dài.
5. **Rate limit và `Retry-After`:** Nếu server trả chỉ dẫn thời gian, xử lý giá trị số giây hoặc HTTP-date hợp lệ, giới hạn bởi deadline; không tạo chuỗi chờ vô hạn.
6. **Khả năng phối hợp:** Circuit breaker, bulkhead hoặc giới hạn đồng thời khi downstream quá tải; tránh nhiều tầng (gateway, SDK, ứng dụng, broker consumer) cùng retry nhân số attempt lên.

### 5.3. Ví dụ kết hợp: khóa đích, gắn token, retry GET

Ví dụ dưới dùng WebClient `partnerWebClient` ở mục 3. Token được lấy từ thành phần riêng; chỉ một GET thuần đọc mới được retry với các phản hồi tạm thời. Trong chương trình thực, cần thêm imports cho `Mono`, `Retry`, `Duration`, `WebClient`, `HttpStatusCode`, `@Service` và `@Qualifier`.

```java
interface PartnerTokenProvider {
    // Token đúng audience/scope, cache và refresh do provider quản lý.
    Mono<String> tokenForOrdersRead();
}

record PartnerOrder(String id, String state) {}

@Service
class PartnerOrderGateway {
    private final WebClient client;
    private final PartnerTokenProvider tokens;

    PartnerOrderGateway(
        @Qualifier("partnerWebClient") WebClient client,
        PartnerTokenProvider tokens
    ) {
        this.client = client;
        this.tokens = tokens;
    }

    Mono<PartnerOrder> getOrder(String orderId) {
        if (orderId == null || !orderId.matches("[A-Za-z0-9_-]{1,64}")) {
            return Mono.error(new IllegalArgumentException("Invalid orderId"));
        }

        Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.5)
            .filter(RetryablePartnerResponse.class::isInstance)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure());

        return tokens.tokenForOrdersRead()
            .flatMap(token -> client.get()
                .uri(uri -> uri.pathSegment("v1", "orders", orderId).build())
                .headers(headers -> headers.setBearerAuth(token))
                .retrieve()
                .onStatus(
                    status -> status.is3xxRedirection(),
                    response -> response.releaseBody()
                        .thenReturn(new UnexpectedRedirect())
                )
                .onStatus(
                    status -> status.value() == 429
                           || status.value() == 502
                           || status.value() == 503
                           || status.value() == 504,
                    response -> response.releaseBody()
                        .thenReturn(new RetryablePartnerResponse())
                )
                .bodyToMono(PartnerOrder.class)
                .retryWhen(retryPolicy)
            )
            .timeout(Duration.ofSeconds(5));
    }

    static final class RetryablePartnerResponse extends RuntimeException {}
    static final class UnexpectedRedirect extends RuntimeException {}
}
```

**Diễn giải:**

- `@Qualifier("partnerWebClient")` chọn WebClient của đúng đối tác. Filter kiểm tra đích vẫn chạy trước khi request được đưa ra mạng; `followRedirect(false)` chặn việc tự động chuyển sang host khác.
- `tokenForOrdersRead()` là hợp đồng trừu tượng của token provider, **không phải một hàm tự có của Spring**. Có thể triển khai bằng Spring Security OAuth2 authorized-client manager phù hợp môi trường (servlet hoặc reactive). Token không được hardcode.
- `headers.setBearerAuth(token)` gắn token cho request cụ thể. Retry nằm **bên trong** `flatMap`, nên các attempt của cùng cuộc gọi dùng token đã lấy cho cuộc gọi đó. Một 401 không nằm trong danh sách retry; nếu cần làm mới token sau 401, xây dựng nhánh xử lý riêng, giới hạn một lần.
- `releaseBody()` giúp giải phóng phần thân của phản hồi 3xx/429/502/503/504 khi chuyển nó thành exception. Không đưa body hoặc token vào exception.
- `retryWhen` chỉ bắt `RetryablePartnerResponse`. Các lỗi khác, kể cả 400/401/403, redirect và timeout không được retry bởi chính policy này.
- `timeout(Duration.ofSeconds(5))` nằm **sau** chuỗi retry để giới hạn tổng thời gian của bước lấy token, gọi HTTP và backoff. Giới hạn 2 giây trong cấu hình connector là thời gian chờ phản hồi trên mỗi request; không có nghĩa cả luồng tối đa 2 giây.

Đây là **chính sách cố ý bảo thủ**: ví dụ chưa retry lỗi kết nối/timeout vì không thể suy ra an toàn của mọi lần mất kết nối. Trong production, có thể mở rộng bộ lọc exception khi đã phân loại được lỗi xảy ra trước khi gửi request và hợp đồng idempotency bảo đảm an toàn. Cần xử lý `Retry-After` cho 429/503 và kết hợp deadline tổng nếu đối tác yêu cầu; đoạn mã minh họa dùng backoff nội bộ cố định.

## 6. Vì sao redirect, URL tuyệt đối và retry thường gây bất ngờ?

### Tình huống A: URL tuyệt đối vượt qua base URL

```java
WebClient client = WebClient.builder()
    .baseUrl("https://partner-api.example.net")
    .build();

// Không nên: có thể khiến request đi tới host do input điều khiển.
client.get().uri("https://attacker.example.org/collect").retrieve();
```

`baseUrl` không có nghĩa mọi request đều bị ép về `partner-api.example.net`. Nếu token được cấu hình ở cấp client, request sai đích sẽ đặc biệt nguy hiểm. Giải pháp là API nghiệp vụ nhận ID thay cho URL, filter kiểm tra destination và chính sách egress.

### Tình huống B: server trả 302 tới host lạ

```text
GET https://partner-api.example.net/v1/orders/42
Authorization: Bearer [redacted]

HTTP/1.1 302 Found
Location: https://untrusted.example.org/receive
```

Không dựa vào giả định thư viện sẽ luôn xóa `Authorization` khi đổi host, bởi hành vi phụ thuộc client, cấu hình và phiên bản. Với ví dụ đang dùng, redirect bị vô hiệu hóa ở connector, còn 3xx được chuyển thành `UnexpectedRedirect` và không retry. Nếu hệ thống thực sự cần follow redirect (chẳng hạn tải tài nguyên từ CDN), phải có allowlist cho *từng đích cuối*, quy tắc bỏ credential khi đổi origin và kiểm thử bằng server kiểm soát được.

### Tình huống C: retry che mất thao tác đã thành công

```text
POST /payments  → server ghi thanh toán thành công
               ← kết nối ngắt trước khi client nhận 201
retry POST      → server tạo thanh toán thứ hai (nếu không deduplicate)
```

Đối với workflow có DB/broker, việc client rollback giao dịch DB tại chỗ **không tự rollback được** HTTP call đã hoàn thành ở downstream. Đặt idempotency key trong hợp đồng, lưu dấu đã xử lý hoặc dùng outbox/inbox và deduplication theo nhu cầu. Retry phía consumer cũng phải tuân thủ cùng khóa và ngưỡng, tránh việc request đã thực hiện lại bị đưa vào hàng đợi vô hạn.

## 7. Log, trace, metric: quan sát mà không phát tán bí mật

Mục tiêu quan sát là biết **API nào**, **đã thử bao nhiêu lần**, **tại sao thất bại**, **mất bao lâu** và **đã vượt ngân sách chưa**. Không cần lưu credential hoặc toàn bộ nội dung request để trả lời những câu hỏi này.

**Có thể ghi:** tên đích logic (`partner_orders_api`), operation (`getOrder`), HTTP method, status, loại lỗi, số attempt, duration, correlation ID không chứa bí mật, kết quả circuit breaker/rate limit.

**Không ghi:** `Authorization`, `Cookie`, `Set-Cookie`, API key, refresh token, token response, URL chứa thông tin xác thực, body nhạy cảm, nguyên chuỗi query có dữ liệu cá nhân, stack trace kèm response dump.

Ví dụ metric có cardinality kiểm soát:

```text
integration.outbound.requests{
  target="partner_orders_api",
  operation="getOrder",
  result="retry_exhausted"
}
```

Tránh dùng order ID, access token, host động hoặc URL đầy đủ làm metric tag. Khi bật Reactor Netty wiretap, request/response logging hoặc HTTP tracing, cần xác minh cấu hình có che header/body nhạy cảm; không mặc định bật body logging ở production. Cấu hình redaction phải áp dụng cả lúc retry, khi exception xảy ra và khi thư viện giám sát tự thu thập header.

Một log hữu ích có dạng: `downstream=partner_orders_api operation=getOrder attempt=2 status=503 duration_ms=210`. Nó đủ phục vụ điều tra vận hành nhưng không cho người xem log quyền gọi API của đối tác.

## 8. Kiểm thử bảo mật và hành vi bằng HTTP server giả lập

Có thể dùng `MockWebServer`, WireMock hoặc mock HTTP server tương đương. Cần kiểm tra request thực sự được nhận ở từng máy chủ, không chỉ kiểm tra kiểu exception. Một bộ kiểm thử tối thiểu:

| Kiểm thử | Dàn dựng | Kết quả cần khẳng định |
| --- | --- | --- |
| Retry hữu hạn | Server trả 503, 503, sau đó 200 | Có đúng ba GET, cuối cùng trả DTO; nếu luôn 503 thì dừng sau ba attempt |
| Không retry lỗi quyền | Server trả 401 hoặc 403 | Chỉ một GET; không lặp lại token cũ |
| Chặn redirect | Server tin cậy trả 302 với `Location` trỏ sang mock server khác | Không phát request tới server thứ hai; token không xuất hiện ở đó |
| Chặn URL tuyệt đối | Cố gọi URI ở một host ngoài allowlist qua WebClient có destination filter | Bị từ chối trước kết nối, mock server lạ nhận 0 request |
| Kiểm tra đầu vào | `orderId` là `../admin`, URL, chuỗi quá dài hoặc ký tự trái quy tắc | Không tạo request; trả lỗi validation |
| Không retry POST mù | Mock server xử lý POST rồi ngắt kết nối | Không tạo lại thao tác, trừ khi contract idempotency đã được thiết kế và kiểm thử |
| Token đúng đích | Hai API mock có token/scope khác nhau | Token của API A không có mặt tại API B |
| Không rò rỉ qua log | Bật cấu hình logging/tracing dùng trong triển khai | Kiểm tra log và trace không chứa chuỗi token giả định |
| Deadline tổng | Mock server cố tình chậm ở nhiều attempt | Call dừng trong ngân sách tổng; không retry vô hạn |
| Phối hợp retry | Giả lập gateway và consumer đều có retry | Tổng attempt không vượt giới hạn đầu-cuối đã chọn |

Khi chạy kiểm thử với mock server, hãy cấu hình host/port được phép **riêng cho test** và vẫn dùng cùng cơ chế kiểm soát đích. Không bỏ filter trong test chỉ để request đi được: làm vậy sẽ không chứng minh được ranh giới bảo mật của production.

Với các lỗi khó mô phỏng như DNS thay đổi, proxy hoặc máy chủ trả chuỗi redirect, nên bổ sung kiểm thử tích hợp ở môi trường mạng cách ly. Kiểm thử cũng cần xác nhận hệ thống không ghi token vào thông điệp lỗi của retry và không phát lại sự kiện broker khi downstream đã xử lý thành công.

## 9. Checklist khi đưa WebClient vào luồng tích hợp

- [ ] URL đích được cấu hình/cho phép rõ ràng; method nghiệp vụ không nhận URL tùy ý.
- [ ] Chỉ gọi HTTPS đến host, port được phép; redirect tự động được tắt hoặc kiểm soát chặt từng hop.
- [ ] Token có audience/scope đúng đối tác, gắn trên request cụ thể; có chính sách làm mới và không log.
- [ ] Không chuyển tiếp access token của người dùng sang downstream khi chưa có thiết kế ủy quyền phù hợp.
- [ ] Policy retry liệt kê rõ status/exception được phép; 401/403, redirect và lỗi validation không nằm trong retry tự động.
- [ ] Có giới hạn attempt, backoff, jitter, tổng deadline và cách ứng xử với `Retry-After`.
- [ ] Mọi thao tác ghi có hợp đồng idempotency/deduplication trước khi cho phép retry khi kết quả không chắc chắn.
- [ ] Log, metric và trace dùng tên downstream logic; có masking và kiểm thử phát hiện token.
- [ ] Kiểm thử có ít nhất một host giả lập không được phép để xác minh không có request/token nào đến đó.

### Câu hỏi tự kiểm tra

1. Tại sao `baseUrl("https://api.example")` không đảm bảo mọi URI mà WebClient nhận đều cùng host?
2. Nếu downstream đã ghi xong giao dịch nhưng client bị timeout, retry POST có thể tạo lỗi gì? Hợp đồng nào giúp tránh?
3. `Retry.backoff(2, ...)` tạo tối đa bao nhiêu HTTP attempt? Điều gì thay đổi nếu đặt `retryWhen` bên ngoài một chuỗi có thêm bước phát sự kiện?
4. Vì sao 401 và 403 cần được tách khỏi nhóm 429/502/503/504?
5. Làm sao chứng minh token không bị chuyển đến host trong header `Location` và không xuất hiện trong log của các attempt?

**Ghi nhớ:** WebClient an toàn trong một hệ thống tích hợp khi mỗi request có **đích tin cậy**, **credential đúng phạm vi** và **quyền retry có điều kiện**. Ba ranh giới này cần được thực thi bằng cấu hình, code, chính sách mạng và kiểm thử, thay vì chỉ trông cậy vào giá trị mặc định của HTTP client.
