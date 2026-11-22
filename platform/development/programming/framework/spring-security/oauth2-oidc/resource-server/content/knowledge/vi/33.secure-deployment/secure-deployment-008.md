# Giới hạn kích thước token, header và chi phí xử lý đầu vào

Một **OAuth 2.0 Resource Server** nhận access token từ request của client rồi xác minh token trước khi cấp Authentication. Token có thể là JWT hoặc opaque string; trong cả hai trường hợp, kích thước đầu vào và số lượng header ảnh hưởng đến khả năng phục vụ của API. Một access token quá lớn có thể vượt giới hạn reverse proxy hoặc HTTP connector, làm request bị từ chối trước khi tới Spring Security. Nếu request được chấp nhận, token lớn và claims phức tạp còn làm tăng chi phí đọc header, parse, decode, xác minh chữ ký, gọi introspection và tạo authorities.

Vì vậy, giới hạn đầu vào phải được đặt ở nhiều lớp:

- **Gateway/reverse proxy/load balancer:** giới hạn kích thước request header trước khi chuyển tiếp vào ứng dụng.
- **HTTP server connector:** áp dụng giới hạn độc lập tại Tomcat, Jetty, Undertow hoặc Reactor Netty.
- **Bearer token resolver:** giới hạn riêng giá trị Authorization header và độ dài token trước khi gọi decoder/introspector.
- **Token/claim policy:** giữ access token gọn, giới hạn số lượng scope/group/claim và chi phí tạo authorities.
- **Kiểm thử vận hành:** chứng minh request trong giới hạn hoạt động, request vượt giới hạn bị từ chối và không có đường đi bỏ qua xác minh.

Không có một con số tối đa phù hợp với mọi hệ thống. Kích thước phải được chọn từ token thực tế do issuer phát hành, giới hạn của từng hạ tầng và ngân sách xử lý của Resource Server. Điều quan trọng là giới hạn phải hữu hạn, nhất quán giữa các hop và được kiểm thử.

## 1. Những kích thước cần phân biệt

Trong một request HTTP, có nhiều loại giới hạn khác nhau:

| Đầu vào | Ví dụ | Lớp thường kiểm soát |
|---|---|---|
| Một header field | Authorization: Bearer ... | Proxy và HTTP connector |
| Tổng request headers | Authorization, Cookie, tracing, custom headers | Proxy, load balancer, connector |
| Bearer token | Phần token sau tiền tố Bearer | Bearer token resolver |
| Request line / request target | Method, path, query string | HTTP server/proxy |
| Request body | JSON payload, form body | Body-size limit riêng |
| Claims trong JWT | groups, scope, permissions, nested JSON | Issuer policy, decoder/validator, converter |
| Introspection response | Attributes và authorities AS trả về | HTTP client/response handling và introspector |

Các giới hạn này không thay thế nhau. Giới hạn body không giới hạn Authorization header. Giới hạn tổng header của connector cũng không nhất thiết đặt được một mức riêng cho token. Giới hạn token trong resolver chỉ chạy sau khi HTTP server đã đọc và chấp nhận request headers.

### 1.1. Header size và token size không giống nhau

Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9...
Accept: application/json
X-Request-Id: 7f21a
~~~

Authorization header chứa cả scheme Bearer, dấu cách và token. Header field còn có tên Authorization, dấu phân cách và framing của giao thức. Token limit nên áp dụng cho chuỗi credential sau khi resolver tách Bearer scheme; header limit của HTTP server bao phủ header field hoặc toàn bộ request headers theo cách connector định nghĩa.

JWT compact serialization thường là ASCII Base64URL. Với token hợp lệ theo Bearer grammar, số ký tự token gần tương ứng số byte token. Nhưng header tổng có thể có Cookie, tracing và các header khác, vì vậy không nên đặt tổng header limit bằng token limit.

### 1.2. Giới hạn header có thể chặn request trước Spring Security

Luồng xử lý:

~~~text
Client
  |
  v
Gateway / Reverse proxy
  |  request-header limits
  v
HTTP server connector
  |  request-header limits
  v
Servlet container / Reactive server
  |
  v
Spring Security filters
  |
  v
Bearer token resolver
  |  token-specific limit
  v
JwtDecoder / OpaqueTokenIntrospector
  |
  v
Authorization + Controller
~~~

Nếu gateway hoặc connector từ chối header quá lớn, request không tới Bearer token resolver. Vì vậy, không thể chỉ dùng MockMvc để chứng minh connector trả lỗi khi header vượt ngưỡng. Cần test bằng HTTP server thật hoặc test riêng ở lớp proxy/gateway.

## 2. Vì sao token và header lớn gây tốn tài nguyên?

### 2.1. Chi phí nhận và lưu header

HTTP server phải nhận bytes từ socket, giải mã header theo giao thức, kiểm tra cấu trúc và lưu các giá trị để ứng dụng truy cập. Header quá lớn có thể:

- Tăng memory sử dụng trên mỗi request.
- Giữ connection và buffer lâu hơn.
- Tăng chi phí copy/parse chuỗi.
- Làm nhiều request đồng thời tiêu thụ nhiều memory hơn.
- Tạo điều kiện cho request flooding hoặc resource exhaustion.

HTTP/2 có HPACK compression nhưng không làm mất giới hạn kích thước logic của header sau giải nén. Server và proxy vẫn cần giới hạn decoded header list/field size để tránh một header nhỏ trên wire trở thành dữ liệu lớn trong bộ nhớ.

### 2.2. Chi phí xử lý JWT

Khi nhận JWT, Resource Server thường thực hiện:

1. Tách compact serialization thành các phần.
2. Decode Base64URL header và payload.
3. Parse JOSE header và claims JSON.
4. Tìm signing key theo kid trong key set tin cậy.
5. Xác minh chữ ký theo thuật toán được cho phép.
6. Kiểm tra issuer, audience, thời gian và token profile.
7. Ánh xạ scope/roles/groups thành authorities.
8. Tạo Authentication và đưa request vào authorization.

Parsing và tạo authorities tăng theo lượng dữ liệu/claim cần xử lý. Signature verification có chi phí mật mã riêng; nếu key chưa có trong cache, việc tải JWKS còn tạo network latency. Không nên cho phép token kích thước không giới hạn chỉ vì decoder có thể xử lý được một token thông thường.

### 2.3. Chi phí xử lý opaque token

Opaque token không nhất thiết ngắn hơn JWT. Resource Server vẫn phải đọc chuỗi token và thường gọi introspection endpoint. Token dài làm request header lớn hơn; introspection response lớn với nhiều attributes/groups còn làm tăng chi phí truyền dữ liệu, parse JSON và tạo authorities.

### 2.4. Claims phình to

Các nguyên nhân thường gặp:

- Đưa toàn bộ danh sách group của một tổ chức vào access token.
- Lặp lại profile, địa chỉ, thông tin liên hệ hoặc metadata không cần cho API.
- Nhúng permission cho hàng nghìn tài nguyên.
- Lồng nhiều object JSON hoặc claim trùng ý nghĩa.
- Phát hành nhiều scope nhỏ thay vì một mô hình quyền phù hợp.
- Gửi cả dữ liệu mà Resource Server có thể tra cứu theo subject/resource.

Access token nên mang thông tin tối thiểu cần thiết để Resource Server xác thực và quyết định quyền. Dữ liệu hồ sơ lớn hoặc quyền biến động mạnh có thể được tra cứu từ service nội bộ theo policy; không cần nhồi tất cả vào mỗi request.

## 3. Chọn giới hạn phù hợp

Không có giới hạn token/header toàn cầu được OAuth 2.0 hoặc JWT quy định. Các giới hạn phụ thuộc hạ tầng và issuer. Hãy đo token thực tế, cộng headroom có kiểm soát, rồi đặt cap.

Một ví dụ minh họa:

| Giới hạn | Giá trị minh họa |
|---|---:|
| Tổng request headers | 16 KiB |
| Authorization header value | 8 KiB |
| Bearer token sau scheme | 6 KiB |
| Số lượng group/permission claim được ánh xạ | 100 |
| Độ dài scope string | 2 KiB |

Các con số trên **không phải khuyến nghị mặc định**. Một hệ thống có cookie hoặc tracing headers lớn cần phân bổ header budget khác. Một issuer có token profile nhỏ có thể đặt cap thấp hơn; hệ thống có claim group lớn cần thay đổi token design thay vì tăng limit vô hạn.

### 3.1. Đo token thực tế

Nên thu thập kích thước theo percentile từ môi trường test/staging hoặc telemetry đã loại bỏ credential:

- Kích thước token nhỏ nhất, trung vị, p95, p99 và maximum quan sát được.
- Kích thước Authorization header.
- Tổng kích thước request headers.
- Số lượng scope/roles/groups.
- Số lượng và kích thước custom claims.
- Số request có token vượt ngưỡng dự kiến.

Chỉ ghi **kích thước**, không ghi token. Không đưa raw access token vào logs, tracing spans, metrics labels hoặc error reports.

### 3.2. Chừa ngân sách cho header khác

Ví dụ nếu tổng header limit là 16 KiB, không nên để Authorization chiếm toàn bộ 16 KiB. Cookie, traceparent, correlation ID, Accept, Content-Type, proxy metadata và header ứng dụng cũng cần chỗ. Một header lớn có thể hợp lệ riêng lẻ nhưng tổng header list vẫn vượt giới hạn.

### 3.3. Giới hạn đồng bộ giữa các lớp

Một cấu hình nhất quán có thể là:

~~~text
Gateway total-header cap        = 16 KiB
HTTP connector total-header cap = 16 KiB
Application Authorization cap  = 8 KiB
Application Bearer-token cap    = 6 KiB
~~~

Đây chỉ là sơ đồ minh họa. Nếu gateway cho phép lớn hơn connector, request có thể bị từ chối ở backend với một status khác. Nếu backend cho phép lớn hơn gateway, đường truy cập trực tiếp vào backend có thể có giới hạn yếu hơn. Chỉ expose backend qua proxy tin cậy và đặt giới hạn tại backend như một lớp bảo vệ độc lập.

## 4. Giới hạn request headers ở Spring Boot

Ở các phiên bản Spring Boot mới, cấu hình chung thường dùng property:

~~~yaml
server:
  max-http-request-header-size: 16KB
~~~

Property này đặt giới hạn request-header size cho embedded server theo hỗ trợ của Spring Boot/connector. Phiên bản cũ có thể dùng tên property khác, chẳng hạn `server.max-http-header-size`; hãy kiểm tra metadata và reference documentation của đúng Spring Boot version trước khi áp dụng.

### 4.1. Giới hạn connector không phải giới hạn token riêng

Giá trị `server.max-http-request-header-size` kiểm soát request headers ở tầng server. Nó không thay thế giới hạn riêng cho Bearer token và không kiểm số lượng authorities sau khi JWT được xác minh.

Connector có thể từ chối request trước khi Spring MVC/WebFlux nhận được. Tùy server và version, response có thể là HTTP 400 hoặc 431. Đừng viết test giả định mọi connector đều trả đúng cùng một status nếu tài liệu implementation không cam kết.

### 4.2. Tomcat, Jetty, Undertow và Reactor Netty

Spring Boot hỗ trợ nhiều embedded server. Property chung có thể được ánh xạ sang cấu hình tương ứng của server, nhưng:

- Cách tính kích thước header (một field hay toàn bộ request) có thể khác.
- Một số connector có thêm giới hạn riêng.
- Phiên bản container có thể thay đổi default và behavior khi vượt ngưỡng.
- Proxy phía trước có thể từ chối request trước khi connector xử lý.

Khi cần điều chỉnh sâu, dùng WebServerFactoryCustomizer hoặc server-specific customizer theo đúng connector/version. Không sao chép thuộc tính Tomcat sang Netty/Jetty nếu chưa xác nhận nó được hỗ trợ.

### 4.3. Giới hạn ở reverse proxy và ingress

Đặt limit ở edge giúp từ chối request lớn trước khi tiêu thụ tài nguyên của ứng dụng. Kiểm tra đồng thời:

- Public load balancer.
- API gateway.
- Ingress controller/service mesh.
- Reverse proxy nội bộ.
- Embedded HTTP server.

Một request đi qua nhiều hop có thể bị giới hạn ở mỗi nơi. Cần ghi nhận lớp nào từ chối để chẩn đoán. Không mở rộng limit trên tất cả tầng chỉ để xử lý một token phình to; trước tiên xác định token chứa claim nào làm tăng kích thước.
## 5. Giới hạn riêng Bearer token trong Servlet

Connector limit bảo vệ parser HTTP. Để đặt cap nhỏ hơn cho Authorization header/token, có thể bọc BearerTokenResolver mặc định và kiểm tra trước khi trả token cho authentication filter.

### 5.1. Resolver có giới hạn

~~~java
import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

final class LimitedBearerTokenResolver implements BearerTokenResolver {

    private final BearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    private final int maxHeaderValueChars;
    private final int maxTokenChars;

    LimitedBearerTokenResolver(
            int maxHeaderValueChars,
            int maxTokenChars) {
        this.maxHeaderValueChars = maxHeaderValueChars;
        this.maxTokenChars = maxTokenChars;
    }

    @Override
    public String resolve(HttpServletRequest request) {
        Enumeration<String> values =
            request.getHeaders(HttpHeaders.AUTHORIZATION);

        if (values != null && values.hasMoreElements()) {
            String headerValue = values.nextElement();

            if (values.hasMoreElements()) {
                throw invalidRequest("Multiple Authorization headers");
            }

            if (!isAscii(headerValue)
                    || headerValue.length() > this.maxHeaderValueChars) {
                throw invalidRequest("Authorization header is too large");
            }
        }

        String token = this.delegate.resolve(request);
        if (token != null && token.length() > this.maxTokenChars) {
            throw invalidToken("Bearer token is too large");
        }
        return token;
    }

    private static boolean isAscii(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) > 0x7f) {
                return false;
            }
        }
        return true;
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_REQUEST, description, null));
    }

    private static OAuth2AuthenticationException invalidToken(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN, description, null));
    }
}
~~~

Resolver trên minh họa các bước:

1. Đọc Authorization header trước khi gọi resolver mặc định.
2. Từ chối nhiều Authorization header thay vì chọn tùy tiện một giá trị.
3. Từ chối header value quá dài hoặc chứa ký tự ngoài ASCII.
4. Để DefaultBearerTokenResolver kiểm tra Bearer scheme/format.
5. Từ chối token vượt cap riêng trước khi decoder/introspector xử lý.

Các cap trong constructor phải lấy từ cấu hình, không hardcode nhiều giá trị rải rác. String.length() phù hợp để kiểm token Bearer ASCII sau khi đã kiểm tra ASCII; giới hạn byte ở proxy/connector vẫn là lớp quyết định cho wire-size.

### 5.2. Gắn resolver vào SecurityFilterChain

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    LimitedBearerTokenResolver resolver =
        new LimitedBearerTokenResolver(
            8 * 1024,
            6 * 1024);

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .bearerTokenResolver(resolver)
            .jwt(Customizer.withDefaults()))
        .build();
}
~~~

Các số ở đây là ví dụ. Cấu hình endpoint/resource server thực tế phải tiếp tục áp dụng authority cần thiết; authenticated() chỉ minh họa vị trí gắn resolver. Resolver không xác minh chữ ký, issuer, audience hoặc expiry; nó chỉ giới hạn và trích xuất credential trước khi decoder chạy.

### 5.3. Vì sao kiểm tra trước decoder?

Nếu chờ tới JwtDecoder mới kiểm kích thước, token đã được chuyển qua các bước nhận header, tạo chuỗi và có thể bắt đầu parse. Giới hạn tại resolver giúp từ chối token lớn trước chi phí decode/crypto/JWKS. Connector limit vẫn cần thiết vì resolver chỉ chạy sau khi request headers được HTTP server chấp nhận.

## 6. Giới hạn Bearer token trong WebFlux

Với WebFlux, dùng ServerAuthenticationConverter để bọc converter mặc định. Ý tưởng giống Servlet: kiểm tra raw Authorization header trước, sau đó mới delegate để tạo Bearer authentication token.

~~~java
import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class LimitedServerBearerTokenConverter
        implements ServerAuthenticationConverter {

    private final ServerAuthenticationConverter delegate =
        new ServerBearerTokenAuthenticationConverter();

    private final int maxHeaderValueChars;
    private final int maxTokenChars;

    LimitedServerBearerTokenConverter(
            int maxHeaderValueChars,
            int maxTokenChars) {
        this.maxHeaderValueChars = maxHeaderValueChars;
        this.maxTokenChars = maxTokenChars;
    }

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> values =
            exchange.getRequest().getHeaders().get(HttpHeaders.AUTHORIZATION);

        if (values != null && values.size() > 1) {
            return Mono.error(invalidRequest("Multiple Authorization headers"));
        }

        if (values != null && !values.isEmpty()) {
            String headerValue = values.get(0);
            if (!isAscii(headerValue)
                    || headerValue.length() > this.maxHeaderValueChars) {
                return Mono.error(
                    invalidRequest("Authorization header is too large"));
            }
        }

        return this.delegate.convert(exchange)
            .flatMap(authentication -> {
                if (authentication instanceof BearerTokenAuthenticationToken bearer
                        && bearer.getToken().length() > this.maxTokenChars) {
                    return Mono.error(
                        invalidToken("Bearer token is too large"));
                }
                return Mono.just(authentication);
            });
    }

    private static boolean isAscii(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (value.charAt(i) > 0x7f) {
                return false;
            }
        }
        return true;
    }

    private static OAuth2AuthenticationException invalidRequest(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_REQUEST, description, null));
    }

    private static OAuth2AuthenticationException invalidToken(
            String description) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN, description, null));
    }
}
~~~

Gắn converter vào reactive Resource Server DSL theo version Spring Security của dự án:

~~~java
ServerAuthenticationConverter converter =
    new LimitedServerBearerTokenConverter(8 * 1024, 6 * 1024);

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenConverter(converter)
    .jwt(Customizer.withDefaults()));
~~~

Tên package/API của converter và DSL có thể thay đổi giữa các version. Kiểm tra Javadoc tương ứng trước khi dùng. Nếu ứng dụng không cần token-specific cap ở resolver, vẫn phải có request-header limit ở connector và proxy. Không đưa blocking parsing hoặc block() vào reactive converter.

## 7. Giới hạn claim và chi phí tạo authorities

Giới hạn token bytes giúp khống chế lượng dữ liệu decoder phải parse, nhưng một token nhỏ vẫn có thể chứa nhiều phần tử claim hoặc dữ liệu lồng nhau. Sau khi decode, Resource Server nên có policy rõ cho các claim được chuyển thành authorities.

### 7.1. Tránh nhồi group/permission vào access token

Một claim groups với hàng nghìn phần tử có thể làm tăng:

- Kích thước token.
- Thời gian parse JSON.
- Số đối tượng Java được tạo.
- Số lượng GrantedAuthority.
- Chi phí kiểm tra authorization và logging/debugging.

Nếu API chỉ cần 2-3 scope, không nên phát hành cả danh sách group của người dùng. Có thể phát scope theo resource, dùng claim quyền đã rút gọn hoặc tra cứu membership/permission qua service nội bộ có cache và policy riêng.

### 7.2. Validator giới hạn claim trước khi tạo Authentication

Một custom OAuth2TokenValidator có thể giới hạn số phần tử trong claim mà ứng dụng dự định ánh xạ:

~~~java
private static final int MAX_GROUPS = 100;
private static final int MAX_SCOPE_CHARS = 2 * 1024;

OAuth2TokenValidator<Jwt> claimBudgetValidator = jwt -> {
    Object groupsClaim = jwt.getClaims().get("groups");
    if (groupsClaim instanceof Collection<?> groups
            && groups.size() > MAX_GROUPS) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Too many group values",
                null));
    }

    Object scopeClaim = jwt.getClaims().get("scope");
    if (scopeClaim instanceof String scope
            && scope.length() > MAX_SCOPE_CHARS) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Scope claim is too large",
                null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

Validator này chạy sau khi JWT đã được parse và signature verification theo decoder. Nó giới hạn claim theo policy trước khi Authentication được cấp; nó không thay thế token-size cap ở Bearer resolver. Với các claim có cấu trúc phức tạp, xác định schema và giới hạn rõ số phần tử, độ sâu hoặc độ dài mà ứng dụng thực sự sử dụng.

### 7.3. Không tạo authority từ mọi claim

Chỉ map claims đã được issuer contract định nghĩa và Resource Server cần. Không tự động chuyển mọi string/boolean trong JWT thành role. Ví dụ admin=true chỉ có ý nghĩa quyền nếu issuer contract, audience và mapping policy xác định rõ. Một token lớn với hàng nghìn giá trị không nên tạo hàng nghìn authorities.

### 7.4. Opaque token cũng cần response budget

Với opaque token, token resolver có thể giới hạn chuỗi trước introspection. Nhưng response từ AS cũng cần được kiểm soát: số attributes, kích thước claims, số scope/group và body size. Nếu dùng custom introspector, không tạo authorities vô hạn từ response. Cấu hình HTTP client/response handling theo khả năng của implementation; không giả định giới hạn request header tự giới hạn response body.

## 8. Không mở rộng giới hạn để che lỗi thiết kế token

Khi token vượt ngưỡng, điều tra nguồn gốc trước:

1. Claim nào chiếm nhiều bytes nhất?
2. Có group/permission bị lặp không?
3. API có thực sự cần claim đó trong mỗi request không?
4. Có thể phát hành scope/resource-specific access token nhỏ hơn không?
5. Có thể dùng reference/identifier và tra cứu dữ liệu cần thiết ở service nội bộ không?
6. Có client nào gửi thêm cookie hoặc header không cần thiết không?
7. Có proxy đang nhân bản hoặc ghép nhiều Authorization header không?

Đừng khắc phục bằng cách tăng header limit trên tất cả môi trường mà không đo. Một token phình to có thể là dấu hiệu authorization model hoặc issuer mapping cần thay đổi.

## 9. Chỉ chấp nhận Bearer token qua header

Spring Security DefaultBearerTokenResolver mặc định đọc Bearer token từ Authorization header. Không bật query parameter hoặc form body token trừ khi có yêu cầu tương thích đặc biệt và đã đánh giá rủi ro.

Không khuyến khích:

~~~http
GET /api/orders?access_token=eyJ...
~~~

Token trong URL dễ xuất hiện trong:

- Browser history.
- Reverse proxy/access logs.
- Analytics và tracing.
- Referrer headers.
- Cache keys hoặc monitoring systems.

Nếu bật thêm nhiều cách truyền token, request có thể mang nhiều credential khác nhau và tạo ambiguity. Giữ một phương thức truyền token rõ ràng; từ chối request có nhiều Authorization header hoặc nhiều token sources.
## 10. HTTP status khi đầu vào vượt giới hạn

Status code phụ thuộc lớp phát hiện lỗi:

| Lớp từ chối | Status thường gặp | Ý nghĩa |
|---|---:|---|
Gateway/HTTP server header limit | 431 hoặc 400 | Request header field/list quá lớn; một số connector trả 400 |
Request target quá dài | 414 | URI quá dài, khác với Authorization header |
Request body quá lớn | 413 | Content quá lớn, không phải header |
Bearer token sai format/không hợp lệ | 401 | Credential không xác thực được |
Token hợp lệ nhưng thiếu authority | 403 | Authentication thành công, authorization bị từ chối |
Custom application policy từ chối token vượt cap | Theo error contract, thường 400 hoặc 401 | Resolver đã nhận request nhưng token không đạt policy |

HTTP 431 được định nghĩa cho request header fields quá lớn. Không yêu cầu connector nào cũng phải trả 431; một số implementation trả 400. Client không nên retry nguyên request với cùng header quá lớn. Tăng limit chỉ có ý nghĩa nếu token thực sự cần kích thước đó và toàn bộ proxy/server đều cho phép.

## 11. Kiểm thử giới hạn token trong Servlet

### 11.1. Unit test resolver ở ranh giới

Với cap token là MAX_TOKEN_CHARS, nên kiểm:

| Độ dài token | Kết quả |
|---|---|
MAX_TOKEN_CHARS - 1 | Resolver có thể trả token |
MAX_TOKEN_CHARS | Resolver chấp nhận nếu format hợp lệ |
MAX_TOKEN_CHARS + 1 | Resolver từ chối trước decoder |
Non-ASCII | Resolver từ chối |
Hai Authorization headers | Resolver từ chối |
Không có Authorization | Resolver trả null |
Header không dùng Bearer scheme | Không tạo Bearer token |

Unit test resolver không chứng minh HTTP connector limit. Nó chỉ kiểm tra token-specific guard.

### 11.2. Kiểm tra decoder không được gọi

Trong test với resolver cap, dùng spy/mock decoder:

~~~java
@Test
void oversizedBearerTokenIsRejectedBeforeJwtDecoder() throws Exception {
    String oversized = "a".repeat(MAX_TOKEN_CHARS + 1);

    mockMvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + oversized))
        .andExpect(status().isUnauthorized());

    verify(jwtDecoder, never()).decode(anyString());
}
~~~

Status cụ thể phụ thuộc cách OAuth2AuthenticationException được entry point ánh xạ trong cấu hình. Assertion quan trọng là resolver từ chối và decoder không được gọi. MockMvc phù hợp cho test này vì mục tiêu là guard ở Security filter; nó không kiểm giới hạn connector.

### 11.3. Test duplicate Authorization headers

~~~java
@Test
void rejectsMultipleAuthorizationHeaders() throws Exception {
    mockMvc.perform(get("/api/orders")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer first-token",
                "Bearer second-token"))
        .andExpect(status().is4xxClientError());

    verify(jwtDecoder, never()).decode(anyString());
}
~~~

HTTP client, proxy hoặc servlet container có thể chuẩn hóa/ghép duplicate headers khác nhau. Test resolver cần kiểm trực tiếp behavior của request abstraction; thêm một test qua real connector/proxy để xác minh behavior trên wire.

## 12. Kiểm thử giới hạn header của HTTP server thật

MockMvc không mở socket qua embedded server connector. Để kiểm connector:

1. Chạy ứng dụng với @SpringBootTest(webEnvironment = RANDOM_PORT).
2. Gửi request HTTP thật với Authorization header vừa dưới, bằng và vượt limit.
3. Ghi nhận status từ connector đang dùng.
4. Xác nhận request vượt ngưỡng không tới controller.
5. Lặp lại qua gateway/ingress trong test deployment nếu gateway có limit riêng.

Ví dụ test bằng TestRestTemplate trong Spring Boot Servlet:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestHeaderLimitIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void connectorRejectsOversizedAuthorizationHeader() {
        String token = "a".repeat(20 * 1024);
        HttpHeaders headers = new HttpHeaders();
        headers.set(
            HttpHeaders.AUTHORIZATION,
            "Bearer " + token);

        ResponseEntity<String> response =
            new TestRestTemplate().exchange(
                "http://localhost:" + port + "/api/orders",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode().is4xxClientError()).isTrue();
    }
}
~~~

Kích thước trong ví dụ phải lớn hơn connector cap của test configuration. Status có thể là 400 hoặc 431 tùy embedded server. Đảm bảo test không vô tình bị từ chối ở custom resolver trước khi kiểm tra connector; muốn test connector, đặt Authorization value vượt tổng header limit và quan sát server response. Để test token-specific cap, giữ header dưới connector limit và vượt riêng token cap.

Với WebFlux, dùng @SpringBootTest(webEnvironment = RANDOM_PORT) và một HTTP client kết nối tới port thật; WebTestClient.bindToApplicationContext(...) không kiểm tra giới hạn socket/connector theo cùng cách. Với proxy/ingress, cần test ở deployment environment có proxy thực.

## 13. Kiểm thử chi phí xử lý và giới hạn claims

Ngoài size, kiểm số lượng phần tử và thời gian:

- Token nhỏ, ít claims: xác minh bình thường.
- Token gần cap: xác minh trong latency budget.
- Token vượt cap: resolver từ chối, decoder/introspector không chạy.
- Token trong cap nhưng có quá nhiều groups: validator từ chối trước khi authorities được tạo.
- Token hợp lệ nhưng scope không đủ: 403.
- Token malformed: 401, không có fallback parse payload.

Không đặt một benchmark cố định làm test pass/fail trên mọi CI machine. Dùng functional assertions để chứng minh bước đắt không chạy khi input vượt cap; dùng load/performance test riêng để đo p95/p99, CPU, allocation và throughput theo cấu hình hạ tầng.

### 13.1. Xác nhận thứ tự xử lý

~~~text
oversized Authorization
  -> resolver rejects
  -> decoder calls = 0
  -> controller calls = 0

valid-size Bearer token
  -> resolver returns token
  -> decoder called
  -> validation result decides Authentication

valid token with excessive group claim
  -> decoder verifies signature
  -> claim-budget validator rejects
  -> authentication not created
  -> controller calls = 0
~~~

Đối với opaque token, thay decoder bằng introspector. Token vượt cap phải bị chặn trước network call; test có thể xác minh MockWebServer không nhận request introspection.

## 14. Các lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
Chỉ giới hạn body size | Authorization header vẫn có thể quá lớn | Đặt request-header cap riêng |
Chỉ giới hạn ở Spring resolver | HTTP server đã phải nhận/parse header trước đó | Giới hạn tại proxy và connector |
Chỉ giới hạn tổng headers | Một token có thể chiếm gần hết budget | Thêm Authorization/token cap |
Đặt cap chỉ ở gateway | Đường truy cập trực tiếp backend có thể yếu hơn | Đặt cap tại embedded server nữa |
Tăng header limit rất lớn | Mở rộng memory/DoS budget | Đo token, giảm claims và đặt cap vừa đủ |
Kiểm size sau khi decode JWT | Parser đã chịu chi phí đầu vào | Kiểm token length trước decoder |
Gộp duplicate Authorization headers | Credential ambiguity và khác biệt giữa proxy/server | Từ chối duplicate headers |
Cho phép token trong query string | Token rò rỉ vào logs/history/referrer | Dùng Authorization header |
Nhồi toàn bộ groups vào JWT | Token và authorities phình to | Phát scope tối thiểu hoặc tra cứu quyền |
Map mọi claim thành authority | Tăng quyền và tăng chi phí | Chỉ map claim theo issuer contract |
Log raw Authorization header | Lộ bearer credential | Chỉ log kích thước và request ID |
Cho rằng HTTP/2 compression giải quyết header size | Header sau giải nén vẫn có thể rất lớn | Đặt decoded header limits |
Dùng MockMvc để kiểm connector 431 | MockMvc không đi qua socket connector | Test RANDOM_PORT và gateway thật |
Giả định mọi server trả 431 | Connector có thể trả 400 | Assert contract phù hợp server/version |
Chỉ test token lớn mà không test decoder call | Không chứng minh guard chạy trước crypto/network | Spy decoder/introspector và assert không được gọi |

## 15. Checklist triển khai an toàn

### Edge và HTTP server

- [ ] Gateway/load balancer có giới hạn tổng request headers.
- [ ] Embedded HTTP connector có giới hạn request headers.
- [ ] Giới hạn được kiểm tra trên đúng connector/version.
- [ ] Backend không thể bị truy cập trực tiếp với giới hạn yếu hơn ngoài dự kiến.
- [ ] Đã xác định status thực tế khi header quá lớn (400/431).

### Bearer token

- [ ] Chỉ chấp nhận Authorization Bearer header theo policy.
- [ ] Có giới hạn riêng cho Authorization header value.
- [ ] Có giới hạn token sau khi tách Bearer scheme.
- [ ] Từ chối ký tự không hợp lệ và duplicate Authorization headers.
- [ ] Token quá lớn bị từ chối trước decoder/introspector.
- [ ] Không nhận token qua query string trừ trường hợp ngoại lệ đã đánh giá.

### Claims và processing cost

- [ ] Issuer phát hành access token chỉ chứa claims cần thiết.
- [ ] Có budget cho scope, groups và permissions.
- [ ] Custom converter không tạo authorities không giới hạn.
- [ ] JWT algorithm/key source được giới hạn theo trust policy.
- [ ] Introspection response và custom attributes được kiểm soát.
- [ ] Không log token, secret hoặc raw Authorization header.

### Tests

- [ ] Test token ở dưới, đúng bằng và vượt cap.
- [ ] Test duplicate header và non-ASCII input.
- [ ] Test decoder/introspector không được gọi khi token quá lớn.
- [ ] Test claim count vượt ngưỡng bị từ chối.
- [ ] Test connector bằng HTTP server RANDOM_PORT.
- [ ] Test gateway/ingress limit ở deployment pipeline.
- [ ] Test token hợp lệ, token invalid và token thiếu scope riêng biệt.

## 16. Kết luận

~~~text
REQUEST HEADERS
  gateway / proxy limit
      |
      v
  HTTP connector limit
      |
      v
AUTHORIZATION HEADER
  duplicate / ASCII / header-value cap
      |
      v
BEARER TOKEN
  token-length cap
      |
      v
TOKEN VALIDATION
  JWT signature + claims
  or opaque introspection
      |
      v
CLAIM / AUTHORITY BUDGET
      |
      v
AUTHORIZATION + CONTROLLER
~~~

Giới hạn kích thước token và header là một phần của bảo vệ Resource Server trước input không đáng tin. Giới hạn ở proxy/connector bảo vệ tài nguyên trước khi Spring Security chạy; giới hạn riêng ở Bearer resolver ngăn token lớn đi vào decoder hoặc introspector; claim budget kiểm soát chi phí tạo principal và authorities. Các lớp phải có ngưỡng hữu hạn, phù hợp với token do issuer phát hành và được kiểm thử trên đúng HTTP connector/proxy.

Khi request vượt ngưỡng, từ chối sớm và không gọi bước xác minh đắt tiền. Khi token nằm trong giới hạn, vẫn phải xác minh đầy đủ chữ ký hoặc introspection, issuer, audience, thời gian và quyền. Không tăng limit vô hạn, không chấp nhận duplicate credential và không log raw token để xử lý lỗi kích thước.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token trong Authorization header và error semantics.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP field limits và status semantics.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): HTTP 431 Request Header Fields Too Large.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 field sections và header processing.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và compact serialization.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation và algorithm/key handling.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token claims/profile.
- [Spring Boot Reference — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): server request-header configuration; property availability depends on Boot version.
- [Spring Security API — BearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenResolver.html): Servlet bearer-token resolution contract.
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): default Authorization-header resolver.
- [Spring Security API — ServerBearerTokenAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html): reactive bearer-token conversion.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, validation and authentication conversion.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque-token authentication.
