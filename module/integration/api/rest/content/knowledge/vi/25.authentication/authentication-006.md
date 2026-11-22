# Kiểm tra chữ ký, thuật toán, issuer, audience và thời hạn JWT

## 1. JWT hợp lệ về cú pháp chưa chắc được phép truy cập API

Một ứng dụng bán hàng có **Orders API** nhận access token do hệ thống định danh phát hành. Client gọi **GET /orders/{id}** với header **Authorization: Bearer ...**. API đọc được JSON payload bên trong JWT:

~~~json
{
  "iss": "https://auth.example.test/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1794981600,
  "nbf": 1794981600,
  "exp": 1794982500,
  "scope": "orders.read",
  "tenant_id": "shop-7"
}
~~~

Các giá trị là **dữ liệu minh họa**, không phải token đã ký. Việc nhìn thấy **sub, scope, tenant_id** không đủ để kết luận request đã được xác thực. Kẻ tấn công có thể tự tạo chuỗi JWT có cùng payload, thay audience của token cấp cho API khác, gửi token quá hạn hoặc cố ép server dùng một thuật toán không mong đợi.

Muốn tin JWT, **resource server** phải xác thực một chuỗi điều kiện: **chữ ký và thuật toán được cho phép; khóa thuộc issuer đã tin cậy; issuer đúng; audience chỉ ra API hiện tại; thời hạn còn hiệu lực**. Sau đó server mới kiểm tra **scope và quyền đối với resource cụ thể**. Chỉ kiểm chữ ký mà bỏ qua audience hoặc issuer vẫn có thể tạo lỗ hổng **token substitution**.

Bài thuộc module **INTEGRATION_API_REST**: kết nối Bearer authentication, HTTP 401/403, Spring Security, phân quyền resource và kiểm thử. **Không tự viết JWT verifier**.

### Kết quả học tập

Bạn có thể:

1. Giải thích JWT/JWS, các trường **alg, kid, iss, aud, exp, nbf, iat** và giới hạn của chúng.
2. Thiết kế **allowlist thuật toán**, lựa chọn khóa đúng issuer và bảo vệ endpoint JWKS.
3. Phân biệt **signature verification, claim validation, authentication và authorization**.
4. Cấu hình **NimbusJwtDecoder / Spring Security Resource Server** với issuer, audience và thời gian.
5. Trả HTTP **401/403** phù hợp và không rò token, khóa hoặc thông tin người dùng.
6. Kiểm thử token ký sai, sai audience/issuer, hết hạn, chưa có hiệu lực, sai quyền và key rotation.

## 2. JWT có gì bên trong và những gì không được tin?

JWT dạng compact JWS thường có ba đoạn Base64url, nối bằng dấu chấm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ header trước khi encode:

~~~json
{"typ":"JWT","alg":"RS256","kid":"orders-key-2026-11"}
~~~

- **header** chứa thông tin thuật toán và khóa được gợi ý để verify.
- **payload** chứa claims. Với JWS thông thường, chúng **không được mã hóa**; ai có token đều có thể decode và xem nội dung.
- **signature** bảo vệ tính toàn vẹn của header/payload với khóa được tin cậy **sau khi** hệ thống kiểm tra chữ ký theo thuật toán được phép.

JWT cũng có dạng JWE mã hóa, nhưng **không mặc định mọi JWT đều được mã hóa**. Đối với một REST API chấp nhận access token dạng JWS, không bao giờ coi việc giải mã Base64url thành JSON là xác thực. **Đừng đưa mật khẩu, thông tin thẻ, bí mật nội bộ hoặc PII không cần thiết vào claims**.

### 2.1. Header do người gửi kiểm soát trước khi verify

Đối thủ có thể sửa header thành:

~~~json
{"alg":"none","kid":"some-key"}
~~~

hoặc cố chuyển **RS256** thành **HS256**. Nếu server tùy tiện tin giá trị **alg** của token để quyết định thuật toán hoặc diễn giải cùng key material không đúng loại, rủi ro **algorithm/key confusion** xuất hiện.

**Quy tắc:** Cấu hình **thuật toán chấp nhận** ở resource server, không để token tự lựa chọn ngoài allowlist. Một hệ thống chỉ được thiết kế cho **RS256** phải từ chối **none, HS256, ES256** và các biến thể khác cho đến khi chúng được cho phép có chủ đích. **HS256** tự thân không “bị cấm” trong mọi hệ thống, nhưng đòi shared secret chất lượng cao, cơ chế phân phối/giữ bí mật khác với RSA public-key verification; không tráo hai mô hình.

### 2.2. kid là chỉ dẫn chọn khóa, không phải chứng cứ tin cậy

**kid** giúp tìm khóa phù hợp trong một tập khóa đã được hệ thống định cấu hình hoặc tải từ **JWKS** đáng tin. Nó không phải URL, không phải quyền thay đổi issuer, cũng không tự xác nhận chữ ký. Đừng nối **kid** vào đường dẫn filesystem, câu SQL hoặc URL theo giá trị tùy ý.

Một token có **jku, x5u** hoặc header khác gợi ý tải khóa từ mạng vẫn là **input chưa được tin**. Không tự chạy HTTP tới URL nằm trong JWT để lấy khóa rồi verify; đó là rủi ro **SSRF và attacker-controlled key**. Endpoint JWKS phải xuất phát từ **issuer discovery đã được tin cậy hoặc cấu hình cố định**, có TLS và chính sách mạng phù hợp.

### 2.3. Chữ ký đúng chưa chứng minh token dành cho API này

Giả sử cùng một identity provider ký cả token cho **orders-api** lẫn **billing-api**. Nếu Orders API chỉ verify chữ ký bằng public key của provider mà bỏ qua **aud**, nó có thể nhận nhầm một token cấp cho Billing API. Tương tự, nhiều tenant/realm có thể dùng các issuer khác nhau; dùng nhầm key hoặc chấp nhận issuer ngoài allowlist khiến ranh giới tin cậy bị phá.

Chữ ký hợp lệ trả lời: “payload được ký bằng khóa tương ứng và chưa bị sửa”. Nó **không tự trả lời**: “issuer có được tin cho API này?”, “token còn hạn?”, “token có quyền đọc đơn này?”.

## 3. Những điều kiện JWT phải thỏa trước khi tạo Authentication

| Điều kiện | Kiểm tra bắt buộc theo hợp đồng ví dụ | Rủi ro nếu bỏ qua |
|---|---|---|
| **alg và chữ ký** | Chỉ RS256; chữ ký khớp public key tin cậy | Token giả, thay payload, algorithm confusion |
| **issuer (iss)** | Khớp **chính xác** issuer cấu hình | Nhận token từ hệ thống/realm không được phép |
| **audience (aud)** | Chứa identifier **orders-api** được cấu hình | Dùng token dành cho API khác |
| **expiration (exp)** | Bắt buộc, thời điểm hiện tại chưa vượt exp (theo clock skew được duyệt) | Token quá hạn vẫn dùng được |
| **not before (nbf)** | Nếu có, chưa được sử dụng trước thời điểm nbf | Token chưa có hiệu lực được chấp nhận |
| **issued at (iat)** | Nếu có, hợp lý theo clock/skew; chính sách có thể giới hạn tuổi token | Token có thời gian bất thường hoặc quá cũ |
| **token profile/type** | Access token đúng profile mà resource server hỗ trợ | Nhận nhầm ID token hoặc token loại khác |
| **scope/roles/permissions** | Đủ quyền cho endpoint và dữ liệu đích | Người dùng hợp lệ truy cập vượt quyền |

### 3.1. iss và aud: so khớp có chủ đích

**iss** thường là URI issuer, ví dụ **https://auth.example.test/realms/shop**; API cần so với **giá trị cấu hình**, không chấp nhận mọi URI có cùng hostname hoặc tiền tố. Khác biệt ở realm/path/trailing slash có thể có ý nghĩa theo contract. **Không đoán issuer từ một claim chưa xác thực rồi tự tải JWKS từ đó**.

**aud** có thể là một string hoặc một danh sách string theo RFC 7519; Spring Security thường đưa ra danh sách audience qua **Jwt.getAudience()**. Kiểm **đối sánh phần tử chính xác**, không dùng contains substring để so **orders-api** với **orders-api-dev** hoặc **not-orders-api**. Token có audience đúng nhưng **scope không đủ** vẫn bị từ chối bởi authorization.

### 3.2. exp, nbf, iat không có cùng ý nghĩa

- **exp:** token hết hạn ở/qua thời điểm này. Trong JWT gốc, NumericDate là số giây tính từ epoch, **không phải milliseconds**. API nên **yêu cầu exp** cho access token theo chính sách.
- **nbf:** thời điểm sớm nhất token có hiệu lực. Token đến từ tương lai hơn mức skew phải bị từ chối.
- **iat:** thời điểm phát hành; **không thay exp**, và một iat cũ không tự khiến token hết hạn nếu API chưa có chính sách tuổi tối đa.

Clock giữa identity provider và API có thể lệch nhẹ. Validator có thể cho phép **leeway khoảng vài chục giây** theo chính sách; không mở quá lớn để “chữa” lỗi đồng hồ vì sẽ kéo dài thời gian chấp nhận token hết hạn/chưa có hiệu lực. Cần đồng bộ thời gian trên hệ thống và kiểm thử **đúng biên**.

### 3.3. access token không phải ID token

Trong OpenID Connect, **ID token** chủ yếu là bằng chứng đăng nhập dành cho **OIDC client**; **OAuth2 access token** dùng để gọi resource API. Một ID token có chữ ký hợp lệ của issuer chưa được phép dùng như access token tới Orders API. Resource server cần kiểm **audience, loại/profile và các chính sách access token**; nếu dùng **RFC 9068 JWT Access Token Profile**, có thể kiểm header **typ: at+jwt** hoặc giá trị tương đương theo profile.

**Không ép typ: at+jwt** lên mọi hệ thống nếu authorization server đang sử dụng một profile khác: phải xác định hợp đồng token thật, tránh vừa kiểm quá lỏng vừa từ chối toàn bộ token hợp lệ ngoài ý muốn. Khi chọn profile **at+jwt**, cần cấu hình cả **token type validation** của decoder theo phiên bản Spring Security đang dùng, không chỉ kiểm aud/scope. Ví dụ Spring bên dưới minh họa loại token có header **typ: JWT** theo cấu hình decoder mặc định. **Opaque token** không phải JWT; phải dùng introspection khi contract cấp loại đó.

## 4. Chuỗi kiểm tra JWT và HTTP authentication

~~~mermaid
flowchart TD
    A[HTTPS request + Authorization Bearer] --> B[Extract token]
    B --> C[Decode cấu trúc trong giới hạn]
    C --> D[Fixed issuer + alg allowlist + trusted JWKS]
    D --> E{JWS signature hợp lệ?}
    E -->|Không| X[401 invalid_token]
    E -->|Có| F{iss, aud, exp, nbf, profile hợp lệ?}
    F -->|Không| X
    F -->|Có| G[Authenticated principal + authorities]
    G --> H{Scope và resource permission?}
    H -->|Không| Y[403 / hoặc 404 che giấu]
    H -->|Có| I[Controller/Service xử lý]
~~~

**Đây là luồng logic**, không khẳng định tất cả framework kiểm theo đúng thứ tự vật lý. Authentication, authorization và application business checks có thể được triển khai ở các filter/layer khác nhau.

### 4.1. Ví dụ HTTP Bearer

~~~http
GET /orders/ord-101 HTTP/1.1
Host: api.example.test
Authorization: Bearer <signed-access-token>
Accept: application/json
~~~

Khi token bị sửa chữ ký, quá hạn, sai issuer/audience:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Khi token hợp lệ nhưng thiếu **orders.read**:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
Cache-Control: no-store
~~~

Theo **RFC 6750**, **WWW-Authenticate** mang Bearer challenge/error khi phù hợp. Nếu không có token, challenge có thể chỉ là **Bearer** mà không có error chi tiết. Không bắt buộc mọi 401/403 có cùng JSON body, và không công khai lý do kỹ thuật nhạy cảm như key ID nội bộ, token thô hoặc stack trace. Nếu phân quyền ở mức resource phải **che giấu sự tồn tại**, API có thể trả **404** theo chính sách nhất quán.

**Không nhầm authentication và authorization:** token được ký đúng và audience hợp lệ có thể xác thực principal, nhưng **orders.read** cũng không cho phép đọc **đơn của tenant khác**. Quyền theo resource/owner/tenant cần được kiểm tại service hoặc policy chuyên trách, kể cả khi filter đã yêu cầu scope.

## 5. Spring Security Resource Server: cấu hình decoder kiểm đúng cả JWT

Ví dụ dùng **Java 17+, Spring Boot 3, Spring Security 6** với dependencies **spring-boot-starter-security** và **spring-boot-starter-oauth2-resource-server** (kèm JWT/Jose support tương ứng). Orders API chỉ tin issuer cố định và **RS256**, yêu cầu audience **orders-api** và claim **exp**. Các URL/giá trị là giả; production phải nạp từ cấu hình bảo vệ, không lấy từ request.

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class ApiSecurityConfig {
    private static final String ISSUER =
        "https://auth.example.test/realms/shop";
    private static final String AUDIENCE = "orders-api";

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        http
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/actuator/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(ISSUER)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> requiredAudience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                audiences -> audiences != null &&
                    audiences.contains(AUDIENCE));

        OAuth2TokenValidator<Jwt> requiredExpiration =
            new JwtClaimValidator<>(
                JwtClaimNames.EXP, Objects::nonNull);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, requiredAudience, requiredExpiration));
        return decoder;
    }
}
~~~

**Những gì đoạn code bảo vệ:**

1. **NimbusJwtDecoder** chọn và xác minh chữ ký JWS với khóa lấy từ **issuer metadata/JWKS tin cậy**, chỉ chấp nhận **RS256** theo cấu hình. Nếu khóa không tìm thấy hoặc chữ ký sai thì không tạo principal xác thực.
2. **JwtValidators.createDefaultWithIssuer** kiểm issuer và các quy tắc thời gian mặc định của Spring Security, đặc biệt **exp/nbf khi hiện diện**. Validator riêng bắt buộc **exp** ngay cả khi token gửi thiếu claim đó.
3. **audience** kiểm phần tử chính xác **orders-api**. Một token hợp lệ nhưng chỉ có **billing-api** sẽ bị từ chối.
4. **SecurityFilterChain** yêu cầu **orders.read/orders.write** theo HTTP method. Theo mặc định, Spring Security ánh xạ **scope/scp** thành authorities có prefix **SCOPE_**; hãy kiểm đúng cách Authorization Server phát scope.
5. **@EnableMethodSecurity** cho phép thêm kiểm tra authorization ở service bằng **@PreAuthorize** khi cần, nhưng không thay thế kiểm tenant/owner trong nghiệp vụ.

**Điểm cấu hình cần lưu ý:** **withIssuerLocation** dùng metadata discovery của issuer được cấu hình để xác định JWK Set URI; môi trường chạy cần kết nối được endpoint đó theo TLS/egress policy. Nếu không có discovery hoặc muốn tách startup khỏi metadata discovery, có thể cấu hình **JWKS URI đã được quản trị tin cậy** và vẫn phải thiết lập validator issuer/audience/time riêng. **Không chọn URI JWKS theo iss hoặc jku chưa xác thực trong mỗi request**.

**Về CSRF:** ví dụ dùng Bearer trong header với session stateless; nếu triển khai một API thật sự không dùng cookie/session để xác thực, có thể cấu hình vô hiệu CSRF cho đúng security chain sau khi review. **STATELESS không tự thay thế phân tích CSRF** khi hệ thống còn hỗ trợ cookie hoặc browser session ở endpoint khác. Không tắt CSRF cho toàn ứng dụng chỉ vì thêm JWT ở một nhóm API.

### 5.1. Cấu hình thời gian chặt hơn theo hợp đồng token

Mặc định validator có thể cho phép **clock skew** hữu hạn. Nếu sản phẩm quy định khác, cấu hình **JwtTimestampValidator** với duration được duyệt và kiểm thử giá trị biên; không tăng skew tùy tiện. Nếu muốn cấm **iat nằm quá xa tương lai**, cấm token có tuổi phát hành quá dài hoặc giới hạn **exp - iat**, cần viết validator riêng có error code rõ, tính theo Instant và tránh làm hỏng token hợp lệ do sai đơn vị giây/millisecond.

Ví dụ quy tắc nghiệp vụ có thể là: **exp bắt buộc, iat bắt buộc, exp > iat, thời gian sống tối đa 15 phút**. Đó là chính sách access token cụ thể, **không phải mặc định của mọi JWT theo RFC 7519**. Chỉ áp dụng khi Authorization Server thực sự cam kết phát token theo cấu trúc này.

### 5.2. Token ở request là Bearer, không phải password

~~~http
GET /orders/ord-101 HTTP/1.1
Authorization: Bearer <valid-jwt-access-token>
Accept: application/json
~~~

Không nhận JWT qua query như **?access_token=...** hoặc log raw Authorization header: URL có thể đi vào browser history, proxy và analytics. API cần bắt buộc **HTTPS** ở biên public; xác minh TLS cả đường tới issuer/JWKS, không dùng HTTP không mã hóa trong production.

## 6. Từ token đã xác thực đến phân quyền theo từng resource

Khi decode thành công, Spring Security tạo **JwtAuthenticationToken** trong SecurityContext. Controller có thể nhận JWT đã xác thực bằng **@AuthenticationPrincipal**, nhưng **chỉ được xem các claims là dữ liệu được issuer phát cho token này**, không tự coi mọi claim là quyền truy cập mọi object.

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

record OrderView(String id, String state, long totalAmount) {}

@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        String subject = jwt.getSubject();
        String tenant = jwt.getClaimAsString("tenant_id");
        OrderView order =
            orders.getVisibleTo(id, subject, tenant);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(order);
    }
}
~~~

**OrderService** là abstraction giả định. Nó phải kiểm tra **order thuộc tenant nào, subject hiện có membership/role gì, quyền đọc còn hiệu lực không** và chỉ trả những field được phép. Một tenant_id có trong access token không thay thế quy tắc domain nếu membership có thể bị thu hồi trước khi token hết hạn. Với API có nhiều nguồn tenant, cần xác định issuer, subject, tenant và service policy có cùng mô hình tin cậy.

### 6.1. Scope và object-level authorization là hai lớp khác nhau

Một token có **scope: orders.read** có thể truy cập API đọc đơn, nhưng chỉ những order mà principal được phép xem. Trong REST:

- **401**: không có access token hợp lệ / chữ ký, issuer, audience hoặc hạn dùng không đạt.
- **403**: token hợp lệ nhưng thiếu scope hoặc không có quyền với resource.
- **404**: có thể dùng để **che giấu sự tồn tại** theo chính sách, kể cả khi biết ID; phải nhất quán.

**Không trả 403 khi token chưa xác thực** chỉ vì auth header chứa chuỗi trông giống JWT. Ngược lại, API không nên trả **401** chỉ vì token hợp lệ thiếu một scope cần thiết; đó là lỗi authorization, thường là **403**.

### 6.2. Nguy cơ lấy sai token trong hệ thống nhiều dịch vụ

Orders API gọi Billing API không nên tự động chuyển tiếp token frontend dành cho Orders nếu token đó có audience **orders-api**. Billing API phải kiểm **aud=billing-api** và token được cấp đúng scope; giải pháp phù hợp có thể là **OAuth2 token exchange**, service credential hoặc một luồng ủy quyền đã được thiết kế. Nếu mọi service chỉ verify chữ ký mà không kiểm audience, cả hệ thống dễ bị tấn công **cross-service token replay**.

## 7. JWKS, xoay khóa và nhiều issuer

**JWKS** chứa các public keys để resource server verify chữ ký; private signing key phải ở Authorization Server/KMS, không nằm trong Orders API. Đối với token có **kid**, chỉ tìm key **trong JWKS thuộc issuer được cấu hình tin cậy**. Chọn algorithm/key type theo allowlist, kiểm TLS và giới hạn network egress. Không truy cập một **jku/x5u/iss URL** tùy ý xuất hiện trong JWT chưa xác thực.

**Rotation thông thường:**

~~~text
T0  JWKS có K1, issuer ký bằng K1
T1  Công bố public key K2
T2  Issuer ký token mới bằng K2
T3  Duy trì K1 đủ lâu cho token cũ và cache/skew
T4  Gỡ K1 khỏi JWKS
~~~

Giới hạn **JWKS cache và refresh rate**, tránh để hàng nghìn kid ngẫu nhiên gây flood tới identity provider. Unknown kid mà không verify được phải **fail closed**, không bỏ kiểm chữ ký. Khi signing key bị lộ, cần quy trình emergency rotation/revocation riêng; không chờ lịch xoay khóa thông thường.

**Nhiều issuer:** chỉ chấp nhận issuer trong **allowlist** với cấu hình decoder/JWKS/validation riêng. Giá trị iss chưa verify có thể dùng để tìm decoder **trong một tập đã tin**, nhưng không được phép chỉ định endpoint tin cậy mới theo input. Không trộn keysets rồi bỏ qua issuer: token từ realm khác không tự có quyền trong realm hiện tại.

**Replay và revoke:** JWT Bearer bị đánh cắp có thể dùng tới khi hết hạn nếu thiếu cơ chế khác. **jti** chỉ là định danh token, không tự thu hồi; có thể cần TTL ngắn, revocation list/introspection, mTLS hoặc DPoP khi hợp đồng hỗ trợ. Đăng xuất hoặc thu hồi membership không mặc định làm mọi JWT đã phát biến mất ngay.

## 8. Ma trận kiểm thử: kiểm cả token đúng lẫn token bị giả mạo

Một bộ kiểm thử JWT chỉ có “gửi token đúng → 200” chưa đủ. Cần tạo **signed JWT test fixtures** có thể thay đổi từng điều kiện riêng, không copy token production vào repository:

| Trường hợp | Thay đổi từ token hợp lệ | Kỳ vọng |
|---|---|---|
| T01 | RS256 ký bởi issuer tin cậy, đúng aud, còn hạn, đủ scope và quyền | **200** |
| T02 | Thay một byte payload, giữ chữ ký cũ | **401**, không tạo Authentication |
| T03 | Ký bằng private key không thuộc trusted JWKS | **401** |
| T04 | Header **alg: none** hoặc HS256 trong hệ thống chỉ cho RS256 | **401** |
| T05 | **iss** là realm khác, kể cả khi token có chữ ký hợp lệ của một nguồn nào đó | **401** |
| T06 | **aud = billing-api**, thiếu **orders-api** | **401** |
| T07 | **exp** đã qua (ngoài skew) hoặc thiếu exp | **401** |
| T08 | **nbf** ở tương lai (ngoài skew) | **401** |
| T09 | Token chưa xác thực / Authorization Bearer bị thiếu, sai cú pháp | **401** |
| T10 | Token hợp lệ, thiếu **orders.read** | **403**, không đọc order |
| T11 | Token hợp lệ, có scope nhưng order của tenant khác | **403/404** theo policy |
| T12 | **kid** không có trong trusted JWKS, JWKS endpoint lỗi | **Không fail-open**; không nhận token chưa verify |
| T13 | Rotation K1 → K2; token hợp lệ của từng khóa trong giai đoạn chuyển đổi | Chấp nhận đúng cửa sổ; xử lý cache/refresh |
| T14 | ID token được gửi nhầm làm access token | **401** khi profile/audience không hợp lệ |

Với **T05**, để kiểm riêng **issuer validator**, có thể tạo JWT được ký bằng key đã được decoder cấu hình nhưng mang claim iss sai; nếu ký bằng key lạ, test chỉ chứng minh **signature** đã bị từ chối. Tương tự, để kiểm audience/expiry, **giữ signature hợp lệ** và chỉ thay claim mong muốn. Mỗi test nên chỉ rõ **điều kiện nào** thực sự bị kiểm.

### 8.1. Thời gian là dữ liệu kiểm thử, không phải sleep()

Dùng các thời điểm có kiểm soát và test **trước/đúng/sau exp hoặc nbf**, kèm cấu hình clock skew. Khi cần test một validator tùy biến, cấp **Clock** có thể điều khiển thay vì phụ thuộc thời gian máy thật hoặc gọi Thread.sleep(). Kiểm trường hợp **exp trong giây**, JSON NumericDate và nhận dạng token thiếu exp. Không tăng skew để làm test qua khi clock hạ tầng bị sai.

## 9. Test phân quyền bằng MockMvc, kiểm chữ ký bằng token ký thật

Spring Security Test **jwt()** tạo principal giả để kiểm HTTP authorization, **không verify JWS/iss/aud/exp bằng JwtDecoder**. Ví dụ trong class có MockMvc và fixture **ord-101 thuộc shop-7**:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void readScopeCanReadVisibleOrder() throws Exception {
    mockMvc.perform(get("/orders/ord-101")
            .with(jwt()
                .jwt(t -> t.subject("user-42")
                    .claim("tenant_id", "shop-7"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void writeScopeAloneCannotRead() throws Exception {
    mockMvc.perform(get("/orders/ord-101")
            .with(jwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.write"))))
        .andExpect(status().isForbidden());
}
~~~

Bổ sung imports JUnit, SimpleGrantedAuthority và fixture. Kiểm cả request **không có token → 401** và principal thuộc tenant khác → **403/404** không có body/ETag nhạy cảm.

**Signature/claims integration test:** tạo RSA keypair **test-only**, xuất public key bằng JWKS test server (như WireMock), ký JWT bằng private key test và gửi request HTTP thật qua Bearer filter/decoder. Thử riêng: (1) token đúng → 200; (2) sửa payload sau ký hoặc dùng key lạ → 401; (3) ký hợp lệ nhưng **iss/aud** sai → 401; (4) **exp quá hạn/thiếu, nbf tương lai** → 401; (5) **alg none/không allowlist, kid lạ** → từ chối; (6) token đúng nhưng thiếu scope hoặc khác tenant → 403/404. Muốn kiểm đúng từng validator, phải **giữ chữ ký hợp lệ** ở test claim sai.

Test rotation với K1/K2 và cache JWKS; xác minh status, **WWW-Authenticate**, không có business side effect và không log token. JWT object giả dùng trong unit test validator **không chứng minh chữ ký**. Không phụ thuộc identity provider production trong CI; localhost JWKS chỉ được phép ở môi trường test.

## 10. Phản mẫu và theo dõi lỗi xác thực

| Phản mẫu | Hậu quả / cách sửa |
|---|---|
| Tin payload sau Base64url decode | Chưa xác thực; dùng decoder kiểm chữ ký và claims |
| Cho token tự chọn **alg, jku, JWKS URL** | Key confusion/SSRF; cấu hình thuật toán và key source cố định |
| Chỉ verify chữ ký, bỏ qua **iss/aud/exp** | Token substitution/expired token; validate đủ |
| Nhận ID token, bỏ token profile | Sai đối tượng nhận; định nghĩa access-token contract |
| Scope đúng là cho đọc mọi ID | BOLA; kiểm quyền tenant/owner ở service |
| 401/403 dùng thay nhau | Sai semantics; 401 xác thực, 403 thiếu quyền |
| Log Authorization hoặc bỏ qua revocation | Rò Bearer/replay; redaction và TTL/revoke policy |

Giám sát **401/403 theo route template, lỗi tổng quát, JWKS refresh, clock skew và latency**; không đưa token, PII, raw subject/tenant vào metric labels. Khi lỗi tăng sau rotation, kiểm kid/cache, issuer/audience và thời gian trước khi nới lỏng chính sách.

## 11. Bài thực hành: bảo vệ Orders API

Issuer **https://auth.example.test/realms/shop** cấp RS256 JWT, audience **orders-api**, token sống tối đa 15 phút. **GET /orders/{id}** cần **orders.read**, **POST /orders** cần **orders.write**, **GET /actuator/health** công khai.

**Yêu cầu:** (1) cấu hình decoder allowlist RS256 + iss/aud/exp/nbf; (2) bảo vệ order của **shop-7** khỏi token hợp lệ của **shop-8**; (3) chọn status cho chữ ký/aud/exp sai, thiếu scope và khác tenant; (4) thiết kế ít nhất sáu test, ba test dùng **JWT ký thật**; (5) mô tả rotation K1/K2.

**Gợi ý:** kiểm chữ ký và claims trước tạo Authentication; sau đó kiểm scope và quyền resource. Token sai → **401**; thiếu quyền → **403** hoặc **404 che giấu** theo chính sách. Dùng key test để kiểm signature, không dùng jwt() mock. Công bố K2 trước khi issuer dùng ký, giữ K1 đủ lâu khi bình thường; key compromise cần thu hồi nhanh.

## 12. Checklist và tài liệu tham khảo

- [ ] Chỉ nhận **alg được allowlist**, verify JWS bằng public key thuộc issuer được tin; không tin URL/key do token gợi ý.
- [ ] Kiểm **issuer chính xác**, **audience đúng resource server**, exp bắt buộc, nbf và clock skew hợp lý.
- [ ] Có chính sách cho **iat, token type/profile, thời hạn tối đa** nếu Authorization Server cam kết.
- [ ] Không nhận OIDC ID token hoặc token của API khác thay access token dành cho Orders.
- [ ] Cấu hình Spring **JwtDecoder + validators + SecurityFilterChain** đúng scope/HTTP method.
- [ ] Sau xác thực phải kiểm **tenant, owner và quyền trên từng resource**; 401 khác 403.
- [ ] JWKS cache/rotation/fail-closed, private key chỉ ở issuer/KMS, không tự tải key từ jku hoặc iss bất kỳ.
- [ ] HTTP Bearer dùng HTTPS, không đưa token vào query/log; Problem Details và WWW-Authenticate an toàn.
- [ ] Test token ký **thật** cho signature, issuer, aud, exp/nbf/alg; test MockMvc riêng cho authorization.
- [ ] Theo dõi revocation/replay risk, đồng bộ clock và quan sát lỗi sau key rotation.

Nguồn tham khảo: [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519); [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515); [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517); [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725); [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750); [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068); [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

**Ghi nhớ:** JWT **chỉ đáng tin sau khi verify chữ ký bằng thuật toán/khóa được cho phép và validate issuer, audience, thời hạn, token type theo hợp đồng**. Sau bước đó, scope và authorization theo từng resource mới quyết định request có được phép hay không. **JWT đã ký không tự đồng nghĩa đủ quyền hoặc không thể bị replay.**
