# SpEL và dữ liệu người dùng

Một ứng dụng Invoice API có phương thức đọc hóa đơn:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:read') and " +
    "@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto getInvoice(@P("invoiceId") String invoiceId) {
    return invoiceService.load(invoiceId);
}
~~~

Trong biểu thức trên, **SpEL (Spring Expression Language)** là một **chính sách do lập trình viên viết, cố định trong mã nguồn**. Giá trị `invoiceId` đến từ URL do người gọi chọn, vì thế **không được tin chỉ vì nó đã xuất hiện trong biểu thức `@PreAuthorize`**. Chính sách cần kiểm: token OAuth 2.0 là access token hợp lệ, có scope `invoice:read`, và subject/tenant đã xác minh **thực sự được đọc hóa đơn được yêu cầu**.

Vấn đề xuất hiện khi lập trình viên nhầm lẫn giữa **dữ liệu người dùng được truyền làm *giá trị*** với **dữ liệu người dùng bị ghép thành *mã SpEL cần thực thi***. Ví dụ, lấy một chuỗi policy từ request để chạy `SpelExpressionParser.parseExpression(...)` với quyền truy cập bean và type trong ứng dụng là một **ranh giới tin cậy nguy hiểm**; CSRF, JWT signature hay scope không biến chuỗi của attacker thành mã chính sách đáng tin.

Bài **“SpEL và dữ liệu người dùng”** thuộc chương **Method security** của module **Security Token Security Fundamentals**. Nội dung tập trung vào **Spring Security 6 / Java 17**, cách SpEL hoạt động trong `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`, cách bind tham số, đọc principal/authorities từ JWT hoặc opaque token đã xác minh, phòng biểu thức injection, bảo vệ quyền trên từng object/tenant, những hạn chế proxy/AOP và kiểm thử authorization âm tính.

**Nguyên tắc:** **SpEL của method security phải là logic tin cậy; dữ liệu từ user chỉ được đưa vào làm tham số để kiểm quyền, không trở thành nguồn biểu thức hay một authority do user tự cấp.** Kiểm token ở **Resource Server** và kiểm business authorization ở **method/data boundary** bổ sung nhau, không thay thế nhau.

## 1. Mô hình tin cậy từ access token đến quyết định của method

~~~mermaid
flowchart TD
    A["Client gửi Authorization: Bearer ..."] --> B{"Resource Server xác minh token?"}
    B -- "Sai chữ ký, inactive, expired, wrong aud" --> X["401 invalid_token"]
    B -- "Token hợp lệ" --> C["Authentication: verified principal + authorities"]
    C --> D["Method security đánh giá @PreAuthorize"]
    E["invoiceId từ path/body: user-controlled value"] --> D
    D --> F{"Scope và @invoiceGuard.canRead?"}
    F -- "Không" --> Y["403/404 theo API policy; không side effect"]
    F -- "Có" --> G["Service/repository thực thi query giới hạn tenant/owner"]
    G --> H["Chỉ trả dữ liệu người gọi được phép xem"]
~~~

| Đầu vào | Độ tin cậy | Cách xử lý |
|---|---|---|
| Bearer access token từ header | **Chưa tin** khi vừa nhận | Xác minh JWS/JWT hoặc opaque introspection trước khi tạo `Authentication` |
| `scope`/`scp` trong **token đã xác minh** | AS cấp theo grant; vẫn phải kiểm issuer/audience/type | Map thành `SCOPE_*` và so với quyền route/method |
| `authentication`/`principal` | Tin **trong phạm vi pipeline cấu hình đúng** | Đọc identity có nguồn gốc xác thực; vẫn kiểm actor/tenant |
| `invoiceId` từ path | **User-controlled** | Chuẩn hóa/validate ID và tra quyền trên chính object đó |
| `tenantId` từ request header/body | **User-controlled** | Chỉ là selector; so với tenant memberships/claims đáng tin |
| `amount`, `beneficiary` | **User-controlled** | Business policy và transaction authorization, không chỉ role |
| SpEL literal của annotation | **Trusted application code** | Review/test như chính sách bảo mật |
| Policy string từ DB/config/remote UI | **Phụ thuộc quyền chỉnh sửa và nguồn gốc** | Không tự đánh giá bằng privileged SpEL; phải có trust model, validation và sandbox được thiết kế riêng |

**Đường đi đúng:**

~~~text
Untrusted HTTP request
     |
     +--- access token  --> verified OAuth Authentication
     |                        |
     |                        +--- issuer, audience, exp, scope...
     |
     +--- invoiceId    --> method argument (untrusted value)
                              |
                              v
Trusted, static @PreAuthorize expression
                              |
                              v
Trusted policy bean checks validated actor + object ownership
                              |
                              v
Database query constrained to tenant + accessible resource
~~~

Không tạo `GrantedAuthority("SCOPE_invoice:admin")` từ header `X-Scope` hoặc body `{"role":"admin"}`. Kẻ tấn công điều khiển request; chỉ token đã được AS tin cậy cấp và RS xác minh mới có thể tạo các scope authorities theo security contract.

## 2. SpEL là gì, và Spring Security dùng nó ở đâu?

**Spring Expression Language (SpEL)** cho phép mô tả logic điều kiện bằng biểu thức: toán tử so sánh, Boolean, đọc thuộc tính, gọi method và truy cập Spring beans trong **evaluation context** thích hợp.

Trong method security, Spring có các điểm kiểm phổ biến:

~~~java
@PreAuthorize("hasAuthority('SCOPE_invoice:read')")
public InvoiceDto readInvoice(String invoiceId) { /* ... */ }

@PostAuthorize("returnObject != null and returnObject.ownerId == authentication.name")
public InvoiceDto readAndCheckResult(String invoiceId) { /* ... */ }

@PreFilter(value = "filterObject != null", filterTarget = "invoiceIds")
public void processIds(java.util.List<String> invoiceIds) { /* ... */ }

@PostFilter("filterObject != null")
public java.util.List<InvoiceDto> getVisibleInvoices() { /* ... */ }
~~~

**Các đoạn code trên chỉ minh họa cú pháp và thời điểm kiểm**, không phải thiết kế phân quyền đầy đủ: `@PostAuthorize` cần tránh null/nested property pitfalls, `@PreFilter`/`@PostFilter` có thể lọc trên bộ sưu tập đã tải vào memory và không thay query-level data isolation.

### Thời điểm kiểm

| Annotation | Thời điểm | Dữ liệu SpEL thường dùng | Rủi ro cần nhớ |
|---|---|---|---|
| **`@PreAuthorize`** | Trước method body | `authentication`, `principal`, arguments `#id` | Phải kiểm object và scope **trước side effect** |
| **`@PostAuthorize`** | Sau method trả kết quả | `returnObject` và authentication | Method có thể đã **đọc/ghi hoặc thực hiện side effect** trước khi deny |
| **`@PreFilter`** | Trước method, lọc đối số collection hỗ trợ | `filterObject` | Có thể mutation/collection incompatibility và không bảo đảm quyền ở nơi khác |
| **`@PostFilter`** | Sau method, lọc collection trả về | `filterObject` | Dữ liệu không được phép đã được load; pagination/performance/leak risk |

### Các biến/tên quan trọng

- `authentication`: đối tượng Spring Security `Authentication` hiện hành.
- `principal`: principal trong authentication context; kiểu cụ thể phụ thuộc JWT, opaque, session hoặc custom adapter.
- `#invoiceId`: tham số method **được bind theo tên** `invoiceId`.
- `returnObject`: kết quả method (thường dùng trong post authorization).
- `filterObject`: phần tử hiện tại của collection được lọc.
- `@invoiceGuard`: tham chiếu **Spring bean tin cậy** tên `invoiceGuard`, không phải annotation được attacker chọn.

**Không giả định mọi SpEL expression có toàn bộ biến ở mọi context**: method security, web authorization, Thymeleaf và data-binding SpEL có evaluation contexts khác nhau. Ở đây ta bàn **method security SpEL** của Spring Security 6.

## 3. Bật method security đúng cách

Trong Spring Security 6, annotation bảo vệ method chỉ được thực thi khi application kích hoạt method security tương ứng, thường bằng `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau đó, Spring method security infrastructure sử dụng AOP interceptors để đánh giá các annotations trên những method call đi qua **cơ chế interception đang áp dụng**.

### Dấu hiệu cấu hình sai

~~~java
// Có annotation nhưng chưa bật Method Security:
@PreAuthorize("hasAuthority('SCOPE_invoice:write')")
public void updateInvoice(String id) {
    repository.update(id); // Có thể bị gọi không được guard!
}
~~~

Nếu chưa có `@EnableMethodSecurity`/cấu hình tương đương, annotation **không tự trở thành enforcement**. Cần test một caller thiếu quyền và xác minh method **không được thực thi**.

### Method security không thay HTTP security

~~~text
HTTP SecurityFilterChain:
  Check authentication, trusted JWT/introspection, route permissions.

Method Security:
  Check method-level authority + actor/resource/business conditions.

Data access:
  Scope database read/write to tenant/owner and resource constraints.
~~~

Một API có thể dùng cả ba. Nếu chỉ kiểm UI/router mà service method được gọi từ batch worker, messaging consumer hay một controller khác, quyền method/domain vẫn rất quan trọng.

## 4. Đưa method argument vào SpEL: `#invoiceId` là giá trị, không phải mã

Phương thức:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:read') and " +
    "@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto getInvoice(@P("invoiceId") String invoiceId) {
    return invoiceRepository.get(invoiceId);
}
~~~

Lập trình viên đã viết **một biểu thức static**. Khi Spring đánh giá nó, `#invoiceId` được resolve thành **giá trị argument**. Nếu attacker truyền một chuỗi giống SpEL, nó vẫn là **chuỗi dữ liệu** truyền vào `canRead`, không tự chạy:

~~~text
Request:
  GET /api/invoices/<some-untrusted-id>

Method argument:
  invoiceId = "<some-untrusted-id>"

Expression:
  @invoiceGuard.canRead(authentication, #invoiceId)

Evaluation:
  trusted Java policy method called with a String argument
  (not parsing the String as a second SpEL program).
~~~

**Điểm cần bảo đảm là policy bean không tự gọi `parseExpression(invoiceId)` hoặc ghép ID thành query chưa parameterize.** Đưa input vào SpEL dưới dạng `#variable` đúng nhưng **việc sử dụng input phía sau** vẫn phải an toàn.

### Tham số theo tên

SpEL cần biết `invoiceId` là tham số nào. Các cách phổ biến:

~~~java
import org.springframework.security.core.parameters.P;

@PreAuthorize("@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto find(@P("invoiceId") String invoiceId) {
    return invoiceRepository.get(invoiceId);
}
~~~

Hoặc compile với Java `-parameters` để Spring có metadata tên tham số:

~~~text
javac -parameters ...

public InvoiceDto find(String invoiceId)
                      // #invoiceId theo parameter name metadata
~~~

Một số security/DI annotations và ngôn ngữ như Kotlin có cơ chế discovery riêng. **Đừng viết SpEL dùng `#invoiceId` rồi giả định Java bytecode luôn giữ tên tham số**: nếu không resolve được, kết quả có thể là `null` hoặc expression evaluation failure, gây 403/500 hay nhầm quyền nếu policy xử lý null sai.

### Nên dùng `@P` lúc nào?

- Library/module được build không chắc có `-parameters`.
- Code đi qua interface/proxy có naming không đồng nhất.
- Test thấy `#id` không resolve trong method security context.
- Muốn bảo đảm tên tham số public contract của authorization expression không đổi khi refactor Java parameter names.

Với example dùng `@P("invoiceId")`, cần test chính annotation đó được Spring Security version nhận diện đúng.

## 5. Dữ liệu người dùng không được trở thành source expression

**Đây là ranh giới an toàn quan trọng nhất của bài.** Có sự khác biệt lớn:

~~~java
// ĐÚNG HƯỚNG: expression là chuỗi hằng do developer review.
@PreAuthorize("@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto read(String invoiceId) {
    return service.read(invoiceId);
}
~~~

với việc đánh giá một biểu thức do caller/chủ thể không được tin soạn:

~~~java
// NGUY HIỂM: coi input HTTP như SpEL program.
// Không làm trong API production.
var parser = new org.springframework.expression.spel.standard.SpelExpressionParser();
var expression = parser.parseExpression(request.getParameter("policy"));
Object result = expression.getValue(privilegedEvaluationContext);
~~~

Ở ví dụ thứ hai, attacker có thể điều khiển **cú pháp biểu thức**. Tùy loại `EvaluationContext`, khả năng method invocation, type references, bean resolver và quyền của Java process, điều này có thể dẫn tới **bypass authorization, truy cập đối tượng nội bộ, thực thi hành vi không mong muốn, thậm chí code execution**. Không cần trình bày payload khai thác để hiểu rằng một **expression engine đầy đủ** không phải parser dữ liệu.

### Những anti-pattern cần loại bỏ

| Anti-pattern | Vì sao nguy hiểm? | Cách thay |
|---|---|---|
| `parseExpression(request.getParameter("rule"))` | Caller định nghĩa mã chính sách | Dùng enum allowlist hoặc policy fixed trong application |
| Ghép `invoiceId` vào một template SpEL rồi parse | Dữ liệu có thể làm thay cú pháp | Dùng `#invoiceId` làm variable |
| Lấy SpEL từ bảng DB do users được chỉnh | “Data” trở thành privileged executable policy | Chỉ dùng policy DSL giới hạn qua reviewed authorization service |
| Cho custom expression trực tiếp gọi mọi bean | Mở cửa tới operations không dùng để authorization | Định nghĩa policy bean interfaces hẹp và test |
| Dùng SpEL tạo SQL/JPQL bằng nối chuỗi | Có thể tạo injection ở tầng query | Parameterized query/typed repository methods |
| Dùng user-provided role/scope trong `@PreAuthorize` | Caller tự cấp authority | Chỉ đọc authorities từ trusted `Authentication` |
| Dùng `#requestBody.isAdmin` như một bằng chứng quyền | Boolean do attacker đặt | Kiểm subject/scope/ACL từ nguồn đáng tin |
| Convert bất kỳ policy string thành `hasAuthority(...)` | Policy drift và injection nguy cơ | Compile-time constants và typed policy service |

### Nếu phải có chính sách động?

Không phải mọi yêu cầu “quy tắc có thể cấu hình” đều cấm, nhưng phải **thay đổi mô hình**:

1. Chỉ cho **trusted administrator/policy deployment** sửa quy tắc, có review/audit/versioning.
2. Nếu user cần filter dữ liệu, cung cấp **typed query parameters** như `status`, `dateFrom`, `category`; không nhận arbitrary SpEL.
3. Nếu cần DSL riêng, giới hạn **toán tử, thuộc tính, depth, kích cỡ, evaluator capabilities** và test không có đường gọi Java arbitrary methods/types/beans.
4. Thiết kế **policy-as-code** hoặc authorization service chuyên biệt với permissions và isolation rõ; không đưa privileged ApplicationContext vào dynamic expression evaluator.
5. Không đánh giá lại một chuỗi sinh ra từ `#variable`; đây là cách biến dữ liệu thành mã.

**Dù `SimpleEvaluationContext` giới hạn một số khả năng SpEL, không mặc định coi nó là “hộp cát tuyệt đối” cho arbitrary attacker expressions**. An toàn nhất là **không thực thi biểu thức do caller kiểm soát** tại API authorization boundary.

## 6. Authentication và principal: dữ liệu nào được phép dùng trong SpEL?

Một số biểu thức thường thấy:

~~~java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("hasAuthority('SCOPE_invoice:read')")
@PreAuthorize("authentication.name == #userId")
@PreAuthorize("@invoiceGuard.canRead(authentication, #invoiceId)")
~~~

Ba điều kiện đầu **không có ý nghĩa như nhau**:

- `isAuthenticated()`: xác thực hiện được Spring coi là hợp lệ; **không chứng minh có quyền đọc hóa đơn**.
- `hasAuthority('SCOPE_invoice:read')`: token/session đã được map authority phù hợp; **không chứng minh object ownership**.
- `authentication.name == #userId`: so một principal name đã cấu hình với **request-supplied userId**; chỉ hợp lệ cho policy mà user chỉ được tự thao tác **chính mình**, và phải phân biệt issuer/user/client/tenant.
- `@invoiceGuard.canRead(...)`: policy bean có thể kiểm token identity và **object in database** ở đúng trust boundary.

### Verified token pipeline trong module

~~~text
JWT:
  BearerTokenAuthenticationFilter
  -> JwtAuthenticationProvider
  -> trusted JwtDecoder (JWS signature + iss/aud/exp/nbf/profile)
  -> JwtAuthenticationConverter (SCOPE_* authorities)
  -> JwtAuthenticationToken
  -> Method security evaluation.

Opaque:
  BearerTokenAuthenticationFilter
  -> OpaqueTokenAuthenticationProvider
  -> trusted AS introspection (active=true + metadata)
  -> mapped OAuth2AuthenticatedPrincipal/authorities
  -> Method security evaluation.
~~~

**Đừng lấy token string từ `Authorization` rồi Base64URL decode trong policy bean để “lấy subject nhanh”**. Với JWT, phải dùng `JwtDecoder` trước; với opaque, AS introspection và RS token contract quyết định metadata tin cậy.

## 7. Resource Server Spring Security 6: xác minh token trước khi xét SpEL

Method security phụ thuộc trực tiếp vào `Authentication` mà Spring đã xây dựng. Một chain xác thực sai có thể khiến biểu thức `hasAuthority(...)` chính xác về cú pháp nhưng **tin quyền đến từ token của issuer hoặc audience khác**.

### Ví dụ một JWT Resource Server cho Invoice API

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
          jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

`issuer-uri` và `jwk-set-uri` là ví dụ cho trusted issuer đã đăng ký. Cấu hình discovery/direct JWKS cụ thể tùy phiên bản Spring Boot/Security; không bao giờ lấy JWKS URI tùy ý từ `jku` hoặc `iss` trong token **chưa verified**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableMethodSecurity
class InvoiceApiMethodSecurity {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/invoices/**")
            // Giả định API chỉ chấp nhận Authorization: Bearer.
            // Nếu có browser cookie authentication, không tắt CSRF như đây.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(rs -> rs.jwt(withDefaults()));
        return http.build();
    }
}
~~~

Ứng dụng cần thêm **một catch-all chain an toàn** cho các routes ngoài `/api/invoices/**` nếu có, đúng matcher ordering và policy cho BFF/session routes. `STATELESS` không tự kiểm scope/audience; `authenticated()` chỉ yêu cầu một `Authentication` hợp lệ. Các yêu cầu cụ thể do `JwtDecoder` validators và method guard thực hiện.

### Decoder có issuer, time và audience validation tường minh

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class InvoiceJwtTrustConfiguration {
    private static final String ISSUER =
        "https://auth.example.test";
    private static final String JWKS =
        "https://auth.example.test/oauth2/jwks";

    @Bean
    JwtDecoder invoiceJwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience() != null &&
            jwt.getAudience().contains("invoice-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected access-token audience",
                    null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(ISSUER),
                new JwtTimestampValidator(Duration.ofSeconds(10)),
                audience));
        return decoder;
    }
}
~~~

**Phạm vi:** Ví dụ dùng `RS256` và `10s` skew như **policy minh họa**, không phải thông số bắt buộc. Trong production, còn phải kiểm token purpose/type (`at+jwt` cho RFC 9068 khi áp dụng), `iat`/max lifetime theo profile, sender-binding DPoP/mTLS và revoke policy. Khi tự `setJwtValidator`, phải giữ **đủ validators** cần thiết vì nó có thể thay chain mặc định.

### Opaque token cũng phải được xác minh

Nếu AS cấp **opaque reference token**, Spring có thể dùng `oauth2ResourceServer(rs -> rs.opaqueToken(...))` và `OpaqueTokenIntrospector`. Phải kiểm `active=true` (JSON Boolean), AS endpoint/TLS/RS credentials, và metadata `iss`, `aud`, `exp`, `scope` theo contract.

**Không đổi từ `JwtDecoder` sang introspection tùy dấu chấm trong token do caller gửi**; route/issuer/resource profile phải được chọn từ cấu hình trusted. Kết quả introspection `active=false` không được dùng để tạo `Authentication` có scopes.

### Guard phải tiếp tục kiểm scope của verified token

Nếu `scope=invoice:read` đã được verified, Spring thường tạo `GrantedAuthority("SCOPE_invoice:read")`. Nhưng:

- `scope=invoice:read-all` không tương đương `invoice:read`.
- `hasRole("invoice:read")` kiểm namespace `ROLE_` theo default, **không** tương đương `hasAuthority("SCOPE_invoice:read")`.
- `scope` do request body/header tự khai **không được dùng**.
- ID token có thể cũng là JWT có chữ ký, nhưng **không được nhận làm access token** tại RS.
- Scope và audience không tự là quyền trên từng invoice/tenant.

## 8. Policy bean an toàn: identity từ token, object ID từ method argument

**Một thiết kế dễ đọc và dễ kiểm thử** là giữ biểu thức SpEL ngắn, đưa logic phức tạp sang Java policy service:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:read') and " +
    "@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto getInvoice(@P("invoiceId") String invoiceId) {
    return invoiceRepository.getInvoiceForAuthorizedCaller(invoiceId);
}
~~~

Ví dụ `invoiceGuard` dùng với **JWT user-delegated route** dưới đây. Với opaque token hoặc M2M, cần identity adapter/policy khác theo contract, không cast mọi `Authentication` thành `JwtAuthenticationToken`.

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

interface InvoiceAccessRepository {
    boolean userCanRead(
        String invoiceId, String issuer,
        String tenantId, String subject);
}

@Component("invoiceGuard")
public final class InvoiceGuard {
    private static final String ISSUER =
        "https://auth.example.test";

    private final InvoiceAccessRepository accessRepository;

    public InvoiceGuard(InvoiceAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(
            Authentication authentication, String invoiceId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
            || !authentication.isAuthenticated()) {
            return false;
        }

        if (invoiceId == null || invoiceId.isBlank() ||
            invoiceId.length() > 80) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();

        // JwtAuth chỉ đến từ trusted decoder/provider.
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (!ISSUER.equals(issuer) ||
            subject == null || subject.isBlank() ||
            tenantId == null || tenantId.isBlank()) {
            return false;
        }

        // Truy vấn DB phải giới hạn theo issuer/tenant/subject.
        // Không dùng String concatenation để xây SQL.
        return accessRepository.userCanRead(
            invoiceId, issuer, tenantId, subject);
    }
}
~~~

**Những giả định của ví dụ phải được review:** token AS phát chứa `tenant_id` được RS tin theo token profile; actor là end-user, không phải client credentials; `jwt.getSubject()` có ý nghĩa user ID trong issuer đó; repository thực thi quyền thực tế; method security được bật và lời gọi đi qua proxy.

### Repository kiểm theo tất cả điều kiện

Ví dụ JPQL **tham số hóa**, khi model lưu issuer/subject/tenant rõ:

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface InvoiceReadPolicyRepository {

    @Query("""
        select case when count(i) > 0 then true else false end
        from InvoiceEntity i
        where i.id = :invoiceId
          and i.issuer = :issuer
          and i.tenantId = :tenantId
          and i.ownerSubject = :subject
          and i.deleted = false
        """)
    boolean existsOwnedInvoice(
        @Param("invoiceId") String invoiceId,
        @Param("issuer") String issuer,
        @Param("tenantId") String tenantId,
        @Param("subject") String subject);
}
~~~

`InvoiceEntity`, fields và repository interfaces là **mô hình minh họa**; sản phẩm thực có thể dùng membership/ACL thay vì chỉ owner. Query parameters là **giá trị**, không được nối thành JPQL/SQL từ `invoiceId` hoặc `tenantId`.

### Tránh lỗi TOCTOU giữa guard và truy cập dữ liệu

Nếu `canRead(...)` chạy một query rồi method body tải object bằng `findById(invoiceId)` không có tenant/owner constraints, một thay đổi quyền cạnh tranh hoặc bug mapping có thể tạo lỗ hổng **time-of-check to time-of-use**.

**Ưu tiên bảo đảm query truy xuất hoặc cập nhật dữ liệu trong method body cũng có điều kiện authorization**:

~~~text
Pre-authorization:
  canRead(verified actor, invoiceId) == true

Business read:
  SELECT invoice
  WHERE id=:invoiceId
    AND tenant_id=:trustedTenant
    AND owner/ACL condition satisfied

Business write:
  update state atomically under tenant/ACL/version constraints;
  re-check high-risk permissions at commit when required.
~~~

Với payment/admin actions, authorization thường cần transaction binding, step-up, idempotency, optimistic locking hoặc database constraints, không chỉ một pre-check ở service.

## 9. DTO, path và header: input có cấu trúc nhưng vẫn chưa được tin

Một DTO được Jackson deserialize thành Java object vẫn là **giá trị attacker chọn**:

~~~java
public record ApproveInvoiceRequest(
    String invoiceId,
    long amountMinorUnits,
    String beneficiaryAccountId,
    String tenantId,
    boolean adminApproved  // User-controlled; NEVER an authority.
) {}
~~~

Không dùng:

~~~java
// SAI: Boolean từ body không phải một quyền.
@PreAuthorize("#request.adminApproved")
public void approve(ApproveInvoiceRequest request) { /* ... */ }
~~~

Có thể attacker chỉ cần gửi `"adminApproved": true`. Spring SpEL đọc property và trả Boolean, nhưng **nguồn của Boolean là request body**, không phải một hành vi phê duyệt đáng tin.

### Biểu thức đề xuất

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:approve') and " +
    "@invoiceGuard.canApprove(authentication, #request)")
public ApprovalResult approve(
        @P("request") ApproveInvoiceRequest request) {
    return invoiceApprovalService.approve(request);
}
~~~

`canApprove` phải kiểm:

- Caller đến từ **access token** đã xác minh với đúng issuer/audience/grant/client.
- Subject/tenant membership theo **trusted identity**, không tin `request.tenantId()` như membership proof.
- Hóa đơn thuộc tenant/resource mà actor được phép; subject có quyền phê duyệt.
- Số tiền/beneficiary trong **request** khớp policy, giới hạn hạn mức và transaction trạng thái thực tế.
- Nếu hành động nhạy cảm, có **step-up/recent authentication** và transaction-specific approval khi cần.
- Retry/duplicate request được xử lý bằng idempotency/business state.

### Bean Validation khác authorization

~~~java
public record InvoiceIdInput(
    @jakarta.validation.constraints.NotBlank
    @jakarta.validation.constraints.Size(max = 80)
    String invoiceId
) {}
~~~

`@NotBlank`/`@Size` giúp kiểm input shape; **không có nghĩa invoice ID đó thuộc caller**. Một ID hoàn toàn hợp lệ về syntax vẫn có thể thuộc tenant khác.

### Không dùng path tenant làm trusted tenant

~~~text
GET /tenants/org-B/invoices/INV-99
  pathTenant = org-B         (caller-selected)
  tokenTenant = org-A       (verified but check entitlement)
  invoiceTenant = org-B

Incorrect:
  if pathTenant == invoiceTenant: allow

Correct:
  verify caller membership/entitlement in pathTenant,
  then query object under that tenant and scope.
~~~

Nếu token cho phép nhiều tenants, dùng một **trusted membership/authorization store** để kiểm tenant được chọn, không chỉ so một claim string với path. Tránh lấy `X-Tenant-ID` từ gateway nếu gateway không xóa/ghi đè header caller và có authenticated transport riêng.

## 10. SpEL với `#variable` và Bean methods: nên giữ biểu thức ngắn

Một biểu thức phức tạp:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:read') and " +
    "authentication.name == #request.userId and " +
    "#request.amount < 1000000 and " +
    "#request.tenantId == principal.claims['tenant_id']")
public void doSomething(ApproveInvoiceRequest request) { /* ... */ }
~~~

có các nguy cơ:

1. `authentication.name` có thể là **client ID hoặc sub tùy converter**, không chắc là end-user.
2. `#request.userId`, `amount`, `tenantId` đều do caller kiểm soát; so hai giá trị không đủ quyền.
3. `principal.claims` không tồn tại trong mọi principal type (JWT/opaque/session khác nhau).
4. Business logic bị nhồi vào SpEL khó test/trace và dễ tạo null/type coercion bugs.
5. Amount/time/ACL có thể thay đổi trong lúc xử lý.

**Cách tiếp cận dễ review hơn:**

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:approve') and " +
    "@invoiceGuard.canApprove(authentication, #request)")
public ApprovalResult approve(@P("request") ApproveInvoiceRequest request) {
    return approvalService.applyWithBusinessConstraints(request);
}
~~~

Với những điều kiện nhạy cảm, policy bean có thể trả **Boolean deny-by-default** hoặc một typed authorization decision có reason code nội bộ, audit và metrics. Không trả trực tiếp thông tin account/tenant tồn tại cho caller trong error message.

### Không phụ thuộc implicit coercion

~~~text
token scope = "invoice:read"
request.amount = "1000000"  (String)

SpEL expression:
  #request.amount < 2000000

Problem:
  implicit type conversion or evaluation error may depend on type/
  binding configuration, not a reviewed financial policy.
~~~

Ưu tiên typed `long`/`BigDecimal` và kiểm currency/minor units; không dùng toán học hoặc string comparison trong expression để thay domain validation.

### Kiểm null rõ ràng

~~~java
@PreAuthorize(
    "#invoiceId != null and " +
    "hasAuthority('SCOPE_invoice:read') and " +
    "@invoiceGuard.canRead(authentication, #invoiceId)")
public InvoiceDto getInvoice(@P("invoiceId") String invoiceId) {
    // ...
}
~~~

**SpEL có toán tử Boolean short-circuit**, nhưng việc một biểu thức không crash khi `#invoiceId=null` không đủ: `invoiceGuard` vẫn nên **tự deny nếu ID null/blank**, vì nó có thể được gọi ở nơi khác. Không viết policy fail open khi dữ liệu không đủ hoặc expression evaluation lỗi.

### Có nên dùng regex ngay trong SpEL?

SpEL có thể hỗ trợ kiểm mẫu, nhưng nếu input dài và regex có catastrophic backtracking, evaluation có thể trở thành CPU DoS. Với ID/token/scope, validation shape nên dùng Java code có **length limits, allowlisted formats và bounded work**; SpEL tập trung orchestration của policies.

## 11. `@PostAuthorize`: khi dữ liệu kiểm quyền chỉ có sau khi tải kết quả

Đôi khi chỉ biết owner/tenant sau khi truy vấn:

~~~java
@PostAuthorize(
    "returnObject != null and " +
    "@invoiceGuard.canRead(authentication, returnObject.id)")
public InvoiceDto getInvoice(String invoiceId) {
    return invoiceRepository.findById(invoiceId);
}
~~~

`returnObject` là **kết quả thực** của method, khác `#invoiceId` là argument. `@PostAuthorize` kiểm **sau khi method đã chạy** nhưng trước khi proxy trả kết quả cho caller khi interception đúng.

### Lợi ích

- Có thể kiểm thuộc tính của object mà chỉ biết sau khi load.
- Hữu ích cho một số **read-only** paths hoặc legacy code chưa thể query ownership trước khi load.
- Có thể kết hợp `returnObject` với `authentication` trong một policy bean thay vì so property tùy ý.

### Giới hạn quan trọng

| Tình huống | Rủi ro |
|---|---|
| Method đã ghi database | Deny sau method **không chắc rollback side effect** nếu transaction boundaries không phù hợp |
| Method gửi email/payment/webhook | Không thể “thu hồi side effect” chỉ vì `@PostAuthorize` deny |
| Method cache dữ liệu trước post-check | Cache có thể chứa dữ liệu chưa được phép |
| Method trả JPA lazy entity | Property access có thể gây lazy loading/error/N+1, tùy transaction |
| Method trả null | Expression không guard null có thể lỗi/deny không rõ |
| Method trả object chứa nested tenant | Đọc sai property hoặc dùng input không verified dễ gây object leak |

**Không dùng `@PostAuthorize` làm lớp bảo vệ duy nhất cho command có side effect**. Đối với ghi, ưu tiên **`@PreAuthorize` + domain authorization + transaction constraints**.

### Nếu dùng `@PostAuthorize` cho đọc

Một ví dụ an toàn hơn về policy structure:

~~~java
@PostAuthorize(
    "returnObject != null and " +
    "@invoiceGuard.canViewReturned(authentication, returnObject)")
public InvoiceDto findInvoice(@P("invoiceId") String invoiceId) {
    return invoiceRepository.findInvoiceProjection(invoiceId);
}
~~~

Policy bean đọc **trusted principal** và typed projection, kiểm issuer/subject/tenant/object. Query vẫn nên filter tenant/owner từ DB để tránh dữ liệu nhạy cảm bị load quá rộng vào service caches hoặc logs.

## 12. `@PreFilter` và `@PostFilter` không thay row-level authorization

Spring method security có filter annotations để **lọc collection**. Chúng có thể hữu ích trong vài trường hợp nhưng dễ bị nhầm với query-level security.

### Pre-filter trên list input

~~~java
@PreFilter(
    value = "@invoiceGuard.canRead(authentication, filterObject)",
    filterTarget = "invoiceIds")
public java.util.List<InvoiceDto> getInvoices(
        @P("invoiceIds") java.util.List<String> invoiceIds) {
    return invoiceRepository.findVisibleInvoices(invoiceIds);
}
~~~

`filterObject` tham chiếu **từng phần tử** của argument collection đang được lọc. Nếu user gửi list nhiều IDs và chỉ có quyền một số, list có thể bị lọc trước khi vào method body.

**Rủi ro:**

- Nếu business endpoint yêu cầu **all-or-nothing**, việc âm thầm loại IDs không hợp lệ có thể che lỗi hoặc gây báo cáo sai. Khi đó **deny cả request** là đúng hơn.
- Việc lọc có thể tạo **nhiều DB checks** (N+1), chi phí cao khi list dài.
- Hành vi với immutable collections, arrays, Map, Stream và proxy version có thể khác; cần test với kiểu input thực.
- Method vẫn cần query giới hạn tenant/owner khi đọc dữ liệu, không chỉ trông vào prefilter.

### Post-filter trên kết quả

~~~java
@PostFilter("@invoiceGuard.canViewReturned(authentication, filterObject)")
public java.util.List<InvoiceDto> listInvoices() {
    return invoiceRepository.loadCandidateInvoices();
}
~~~

`filterObject` tham chiếu **mỗi kết quả được trả về**. Nhưng:

- `loadCandidateInvoices()` có thể đã **đọc quá nhiều dữ liệu nhạy cảm** trong database/application memory.
- Phân trang, sorting, count và cursor có thể sai nếu lọc sau khi lấy dữ liệu.
- Áp lên result type không được hỗ trợ có thể gây error hoặc bỏ sót guard.
- N+1 authorization checks có thể làm API chậm hoặc lộ timing.
- Với `Page<Invoice>` của Spring Data, **không giả định `@PostFilter` sẽ lọc Page đúng và giữ pagination**; thường nên đưa ACL vào **repository query**.

### Query-level authorization được ưu tiên khi có thể

~~~text
Safer list query:
  SELECT invoice
  FROM invoices
  WHERE tenant_id = :trustedTenant
    AND (owner_subject = :verifiedSub
         OR EXISTS authorized_delegation(...))
  ORDER BY created_at DESC
  LIMIT :pageSize OFFSET :offset

Benefits:
  - only authorized rows enter application
  - correct pagination/count semantics
  - fewer authorization checks
  - less risk of side-channel/cache leakage
~~~

**Filter annotations là công cụ hữu ích, không phải thiết kế quyền dữ liệu mặc định cho mọi kết quả collection.**

## 13. Proxy/AOP và self-invocation: annotation có thể không chạy

Với **proxy-based method security**, Spring đặt security interceptor quanh các method call đi qua proxy. Nếu một method trong cùng class gọi method khác bằng `this`, lời gọi nội bộ thường **không đi qua proxy**, nên `@PreAuthorize` trên method đích có thể không được áp.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class InvoiceApprovalService {

    public void processBatch(java.util.List<String> invoiceIds) {
        for (String id : invoiceIds) {
            this.approveOne(id);  // Self-invocation, có thể bypass AOP.
        }
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_invoice:approve') and " +
        "@invoiceGuard.canApproveId(authentication, #invoiceId)")
    public void approveOne(@P("invoiceId") String invoiceId) {
        // Đừng tin annotation này luôn chạy qua this.approveOne(...).
        performBusinessApproval(invoiceId);
    }
}
~~~

**Đây là ví dụ anti-pattern**, với `performBusinessApproval` là placeholder nghiệp vụ. Nếu batch endpoint không có quyền tương đương, nó có thể đi vòng qua guard.

### Cách sửa kiến trúc

Tách method bảo vệ sang **một Spring bean riêng** và gọi qua bean được inject:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class SecuredInvoiceApproval {

    @PreAuthorize(
        "hasAuthority('SCOPE_invoice:approve') and " +
        "@invoiceGuard.canApproveId(authentication, #invoiceId)")
    public void approveOne(@P("invoiceId") String invoiceId) {
        // Business-layer authorization vẫn cần được thực thi
        // trong giao dịch, kể cả khi method guard đã pass.
        writeAuthorizedApproval(invoiceId);
    }
}

@Service
public class InvoiceApprovalBatch {
    private final SecuredInvoiceApproval secured;

    public InvoiceApprovalBatch(SecuredInvoiceApproval secured) {
        this.secured = secured;
    }

    public void processBatch(java.util.List<String> invoiceIds) {
        for (String id : invoiceIds) {
            secured.approveOne(id);  // Đi qua injected proxy.
        }
    }
}
~~~

Các method `writeAuthorizedApproval` và support beans là placeholders. Trong production, bảo đảm **batch actor có authentication context đúng**, mỗi operation kiểm quyền phù hợp và database writes được constraint.

### Những trường hợp dễ bỏ qua

| Trường hợp | Điều cần kiểm |
|---|---|
| Gọi `this.securedMethod()` trong cùng class | Proxy-based interception có thể bị bypass |
| Method `private` hoặc không thể intercept bởi proxy mode | Annotation có thể không được áp |
| Method `final`, class `final` với class-based proxy | Có thể không tạo được interception theo loại proxy |
| Annotation đặt trên interface/superclass | Kiểm rule inheritance/override, proxy kiểu JDK/CGLIB và Spring version |
| Test chỉ gọi bean trực tiếp nhưng production gọi internal | Cần integration tests đúng call path |
| Dùng AspectJ weaving thay proxy | Semantics khác; phải cấu hình và test mode thực tế |
| Method bảo vệ ở constructor/initializer | Có thể chạy trước khi proxy/filters sẵn sàng |

Không cần đoán annotation “có vẻ đúng”: hãy viết **test thiếu quyền** cho **mọi entry path** (controller, batch, scheduler, message consumer) và assert DB/external side effects bằng 0.

## 14. Thread, async, scheduler và reactive SecurityContext

`SecurityContextHolder` thường lưu `SecurityContext` theo strategy phù hợp luồng thực thi. Với **Servlet MVC**, cơ chế mặc định thường liên quan request thread; nếu work chuyển sang thread khác, không được giả định `Authentication` tự xuất hiện.

### Async boundary

~~~java
@PreAuthorize("hasAuthority('SCOPE_invoice:export')")
public void scheduleExport(String invoiceId) {
    exportExecutor.submit(() -> {
        // Không tự tin SecurityContext từ HTTP request
        // sẽ có mặt trong thread async này.
        exportFile(invoiceId);
    });
}
~~~

Method guard trước khi submit xác thực request ban đầu, nhưng công việc chạy sau có thể phải:

- Kiểm lại **issuer, subject/client, tenant, resource, quyền export** vào thời điểm thực thi nếu policy yêu cầu.
- Mang theo một **trusted, minimal actor context** đã được xác thực, không truyền raw Bearer token vào message queue/logs.
- Hoặc dùng cơ chế propagation `DelegatingSecurityContext...` phù hợp nếu cần, với lifecycle/cancellation và không kéo dài authentication quá `exp`.
- Khi scheduler/service account thực hiện thao tác, định nghĩa **workload identity** rõ, không giả user ID từ message body.
- Giới hạn TTL của job authorization và xử lý revoke/account disable trước khi commit.

**Không dùng `MODE_INHERITABLETHREADLOCAL` hoặc global shared SecurityContext như workaround chung**: thread pools có thể tái sử dụng threads, gây lẫn identity giữa requests nếu context không được quản lý đúng.

### Reactive khác Servlet

Với **Spring WebFlux**, SecurityContext thường gắn với **Reactor Context**, không giống thread-local strategy của Servlet. Reactive method security có các yêu cầu riêng và có thể dùng `@EnableReactiveMethodSecurity` với return types/reactive publishers được hỗ trợ.

**Đừng copy một ví dụ `SecurityContextHolder.getContext()` từ Servlet vào reactive pipeline rồi coi là authority source đáng tin**. Tài liệu và integration tests phải khớp chính xác execution model.

### Background job không có token user

Nếu job lấy access token qua `client_credentials`:

~~~text
Actor = client/workload identity
Scope = batch:export
No delegated end-user subject by default.
~~~

Không tự tạo `Authentication(name="user:an")` khi job đang chạy để vượt guard user-only. Nếu nghiệp vụ yêu cầu delegated processing, cần một **signed/authorized work request** hoặc grant model có TTL, audience và revocation phù hợp.

## 15. Quyền tại thời điểm kiểm và thời điểm ghi: TOCTOU, transaction và side effects

Một phương thức:

~~~java
@PreAuthorize("@invoiceGuard.canApproveId(authentication, #invoiceId)")
public void approveInvoice(@P("invoiceId") String invoiceId) {
    paymentGateway.sendApproval(invoiceId);
    repository.markApproved(invoiceId);
}
~~~

có vấn đề tiềm tàng ngay cả khi `@PreAuthorize` chạy:

1. Quyền có thể được rút **sau khi kiểm** nhưng trước khi side effect.
2. Invoice status/amount/beneficiary có thể thay đổi trong lúc xử lý.
3. External API đã nhận yêu cầu nhưng DB transaction thất bại; rollback database không rollback external call.
4. Caller có thể retry và thực hiện action hai lần nếu không có idempotency.
5. Nếu `@PreAuthorize` chỉ kiểm scope mà không check owner/tenant, token hợp lệ vẫn có thể phê duyệt tài nguyên không thuộc caller.

### Bảo vệ theo transaction boundary

~~~text
PRE-CONDITIONS (trusted):
  token valid + correct issuer/aud/type
  required SCOPE_invoice:approve
  actor matches tenant/approval policy

ATOMIC DATABASE WRITE:
  UPDATE invoice
  SET state = APPROVED, version = version + 1
  WHERE id = :invoiceId
    AND tenant_id = :trustedTenant
    AND status = PENDING
    AND version = :expectedVersion
    AND actor has approval entitlement

EXTERNAL SIDE EFFECT:
  Prefer outbox/event state machine + idempotency key,
  not uncontrolled call before transaction commit.
~~~

### JPA query tham số hóa cho write authorization

~~~java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface InvoiceApprovalRepository {
    @Modifying
    @Query("""
        update InvoiceEntity i
        set i.status = 'APPROVED',
            i.version = i.version + 1
        where i.id = :invoiceId
          and i.tenantId = :tenant
          and i.status = 'PENDING'
          and i.version = :expectedVersion
        """)
    int approvePendingInvoice(
        @Param("invoiceId") String invoiceId,
        @Param("tenant") String trustedTenant,
        @Param("expectedVersion") long expectedVersion);
}
~~~

Query này minh họa **state/version/tenant constraints** nhưng **chưa tự chứng minh actor có entitlement**. Phải kiểm actor theo policy/ACL trong transaction hoặc thêm predicate/transaction mechanism phù hợp. Thành công khi **affected rows = 1**, ngược lại xử lý conflict/deny. Tránh nối raw `invoiceId`/`tenant` vào JPQL.

### `@Transactional` và `@PreAuthorize` có tương tác thứ tự

Trong Spring, nhiều advisors/interceptors có order cụ thể. Không giả định mặc định `@PreAuthorize` luôn nằm trong hoặc ngoài database transaction theo ý muốn. Kiểm order/transaction settings đã cấu hình; side effects và rollback phải được test.

**Quan trọng nhất:** Nếu một `@PostAuthorize` từ chối sau khi method gọi external payment provider, **việc deny không chắc đảo ngược được giao dịch**. Authorization cho hành động có tác dụng phải diễn ra **trước** side effect, và data mutation phải có ràng buộc bất biến.

## 16. Ngữ nghĩa lỗi: SpEL fail-closed và phân biệt `401`/`403`

Một request có thể thất bại ở nhiều tầng:

| Tình huống | Lớp phát hiện | Cách xử lý phù hợp |
|---|---|---|
| Không có access token | Resource Server authentication | `401 Unauthorized`, Bearer challenge |
| JWT chữ ký sai/issuer sai/expired | `JwtDecoder` | `401 invalid_token` |
| Opaque introspection `active=false` | `OpaqueTokenIntrospector` | `401 invalid_token` |
| Bearer token đúng nhưng thiếu `SCOPE_invoice:read` | Method/route authorization | `403 insufficient_scope` khi phù hợp |
| Token có scope nhưng không phải owner | `invoiceGuard`/service policy | `403` hoặc `404` theo privacy policy |
| `#invoiceId` không bind/SpEL lỗi null/method không tồn tại | Method security evaluation | **Không cho thực thi**, alert cấu hình; mã HTTP tùy exception mapping |
| AS introspection timeout/503 | Token validation infrastructure | Fail closed, thường trả lỗi dịch vụ phù hợp, không tự tạo principal |
| Không truy cập được policy DB | Business authorization | Fail closed, không lấy lỗi DB làm “owner=true” |
| Rate limit / dependency overload | Infrastructure | Retry/backoff theo policy, không bypass guard |

### Không fail open khi expression lỗi

~~~java
// Không làm:
boolean allowed;
try {
    allowed = evaluateSecuritySpel();
} catch (Exception e) {
    allowed = true;  // NGUY HIỂM
}
~~~

Nếu method security evaluator gặp lỗi parse, type mismatch, bean lookup hoặc permission service timeout, kết quả **không được là mặc định cho phép**. Cấu hình error handling phải tách **lỗi quyền** với **lỗi vận hành**, và không để message nội bộ (bean names, query, token claims) lộ ra client.

### `hasAuthority` trả false không phải parser injection

`hasAuthority("SCOPE_invoice:write")` trả false với token chỉ có `SCOPE_invoice:read` là **quyết định đúng**, không phải lỗi “SpEL nhận sai giá trị”. Không mở `permitAll()` để giảm 403 trước khi kiểm:

1. Token đã được AS cấp scope write chưa?
2. JWT/opaque converter đọc đúng `scope`/`scp` và prefix `SCOPE_` chưa?
3. Audience và token type đúng chưa?
4. Route/method guard có yêu cầu quyền cao hơn theo thiết kế không?
5. Actor có quyền domain trên object không?

### Error response không phải oracle

Không nên trả response như:

~~~text
Invoice INV-99 exists and belongs to organization payroll-prod.
Your JWT token had scope invoice:read but lacks ROLE_GLOBAL_ADMIN.
SpEL bean invoiceGuard failed to load internal SQL table ...
~~~

Thông tin như vậy có thể tiết lộ data existence, tenant identities và kiến trúc nội bộ. Caller cần mã lỗi phù hợp; chi tiết nhạy cảm phải nằm trong audit log đã phân quyền và khử token.

## 17. Performance và observability: tránh gọi policy bean hàng nghìn lần vô kiểm soát

Đánh giá SpEL đơn giản thường không phải nút thắt chính; rủi ro nằm ở **policy method gọi DB/remote authorization service** trong mỗi lần đánh giá:

~~~text
@PreAuthorize("@invoiceGuard.canRead(authentication, #invoiceId)")
     |
     +-- SELECT canRead from database

@PostFilter("@invoiceGuard.canRead(authentication, filterObject.id)")
     |
     +-- 1 DB query PER RESULT ITEM (N+1 risk)
~~~

### Chiến lược hiệu năng an toàn

| Kỹ thuật | Lợi ích | Rào chắn bảo mật |
|---|---|---|
| **Query-level tenant/owner filter** | DB trả đúng dữ liệu, tránh N+1 | Predicate phải dùng trusted actor/tenant |
| **Batch ACL check** | Giảm số DB round trips | Không cho phép dùng quyết định của object A cho object B |
| **Cache policy** | Giảm latency | Key theo issuer/actor/tenant/object/action/version, TTL và invalidation phù hợp |
| **Index tenant/owner/status** | Truy vấn quyền nhanh | Không thay việc kiểm authorization |
| **Cap list/filter input size** | Giảm DoS khi users gửi hàng nghìn IDs | Giới hạn ở ingress/service; không silently skip authorization |
| **Circuit breaker policy service** | Giữ dependency ổn định | Khi không có quyết định đáng tin thì **deny/fail closed** |
| **Early route scope check** | Loại request thiếu scope trước DB lookup | Method/data object guard vẫn phải kiểm |
| **Transactional authorization** | Giảm race trước write | Atomic state/tenant/ACL constraints, external idempotency |

### Metrics hữu ích

~~~text
method_authorization_decision_total{policy="invoice.read",result="deny"}
method_authorization_duration_seconds{policy="invoice.read"}
method_security_expression_error_total{policy="invoice.read"}
method_security_missing_context_total{entry="async-export"}
object_authorization_denied_total{resource="invoice"}
scope_authority_missing_total{scope="invoice:read"}
authorization_policy_db_latency_seconds{policy="invoice.read"}
method_guard_bypass_test_fail_total{path="batch-approval"}
~~~

Đây là **tên metric minh họa**, không mặc định tồn tại trong Spring. Dùng labels có cardinality hữu hạn; **không gắn raw token, `jti`, invoiceId, subject, email, tenantId tùy ý hoặc chuỗi SpEL từ request** vào metric labels.

### Logging

Audit có thể ghi **decision code, route, policy version, correlation ID, trusted issuer alias** và actor pseudonymous identifier đã được phép. Không log raw `Authorization`, refresh token, client secret, full JWT payload hoặc nội dung query chứa PII.

Nếu cần điều tra token theft/replay, giữ **security audit riêng**, phân quyền, retention và redaction. Việc log “để debug converter” có thể khiến chính log trở thành nơi attacker đánh cắp Bearer token.

## 18. Ma trận kiểm thử SpEL và dữ liệu người dùng

Thiết lập minh họa:

~~~text
Authorization Server: https://auth.example.test
Invoice Resource Server: aud=invoice-api
Expected user-delegated JWT: iss trusted, RS256, not expired
GET /api/invoices/{id}: requires SCOPE_invoice:read
POST /api/invoices/{id}/approve: requires SCOPE_invoice:approve

Trusted actor:
  issuer=https://auth.example.test
  sub=user:an
  tenant_id=org-A
  scope=invoice:read invoice:approve

Objects:
  INV-42: org-A, owner=user:an, status=PENDING
  INV-99: org-B, owner=user:binh, status=PENDING

Method security:
  @EnableMethodSecurity active
  @PreAuthorize(expression is developer-controlled)
  @invoiceGuard checks trusted actor and DB constraints
~~~

| Ca kiểm thử | Input / điều kiện | Kết quả kỳ vọng |
|---|---|---|
| **JWT hợp lệ + đúng object** | `sub=An`, `SCOPE_invoice:read`, ID `INV-42` | Cho phép đọc nếu mọi policy khác đạt |
| **JWT hợp lệ + sai object** | `sub=An`, ID `INV-99` thuộc Bình | Deny, không lộ dữ liệu tenant khác |
| **Chỉ scope read gọi approve** | JWT thiếu `SCOPE_invoice:approve` | 403 trước side effect |
| **Scope substring** | `invoice:read-all` nhưng guard đòi `invoice:read` | Không coi là tương đương |
| **Scope sai namespace** | Có `ROLE_invoice:read` nhưng guard đòi `SCOPE_invoice:read` | Deny, kiểm mapping chứ không `permitAll` |
| **JWT signature sai** | Attacker sửa `scope=invoice:approve` | 401 trước khi method guard chạy |
| **JWT `alg=none`** | Không có chữ ký đáng tin | Reject |
| **JWT issuer sai** | Token từ issuer attacker | Reject trước mapping authorities |
| **JWT audience sai** | Token `aud=payroll-api` | Reject trước method |
| **JWT expired** | `now>=exp`, skew policy tương ứng | Reject |
| **JWT `nbf` tương lai** | Chưa đến not-before | Reject |
| **ID token thay access token** | OP ID token cho RP `invoice-web` | Reject token purpose/audience |
| **Refresh token gửi Invoice RS** | Token không phải access-token class | Reject |
| **Opaque introspection inactive** | `active=false` | Không tạo Authentication có scope |
| **Opaque introspection 401** | RS credential sai | Fail closed, alert; không tạo authority |
| **Opaque introspection timeout** | Không có response authoritative | Fail closed, không cho phép vì AS down |
| **Opaque wrong audience** | `active=true` nhưng `aud=payroll-api` | Reject |
| **Không có `@EnableMethodSecurity`** | Annotation tồn tại nhưng interceptor không chạy | Integration test FAIL, không coi annotation có hiệu lực |
| **Proxy self-invocation** | `this.approveOne()` | Test phát hiện path bypass; sửa kiến trúc |
| **Private protected method** | Annotation đặt ở method không intercepted | Test fail hoặc cấu hình không cho phép |
| **Method final trong proxy mode không hỗ trợ** | Method bị gọi ngoài interceptor | Test fail; sửa proxy/design |
| **Batch entry path** | Job gọi service không đi qua controller | Vẫn phải kiểm workload/actor authorization |
| **Async context absent** | `@Async`/executor không có SecurityContext phù hợp | Fail closed, không giả principal admin |
| **Scheduler không có user identity** | Job chạy dưới service account | Workload policy, không gán user giả |
| **`#invoiceId` bind đúng** | Có `@P("invoiceId")` | Policy nhận đúng giá trị argument |
| **`#invoiceId` không bind** | Thiếu metadata, expression nhận null/lỗi | Deny, regression test bắt lỗi |
| **`invoiceId=null`** | API/method nhận null | Guard deny, không query wildcard |
| **`invoiceId=""`** | ID rỗng | Deny |
| **ID quá dài** | User gửi chuỗi hàng MB | Input length validation, hạn resource |
| **ID khác tenant** | Path `/org-B/...`, token org-A | Deny trừ entitlement verified |
| **ID trông như SpEL** | User đưa string chứa toán tử/dấu nháy | Vẫn là argument value; không được parse thành expression |
| **Role từ body** | `{"role":"ADMIN"}` | Không sinh `ROLE_ADMIN` |
| **Scope từ header** | `X-Scope: invoice:approve` | Không sinh `SCOPE_invoice:approve` |
| **Tenant từ header** | `X-Tenant-ID: org-B` | Không tin như membership proof |
| **Bool phê duyệt từ DTO** | `adminApproved=true` | Không coi như privileged approval |
| **Price/amount kiểu String** | `"1000000"` thay long/BigDecimal | Validate typed schema; không implicit auth coercion |
| **Malicious nested DTO** | Input object với nhiều fields lạ | Reject/ignore theo binding policy, không cấp quyền |
| **User-provided SpEL rule** | `policy` trong request gửi vào `parseExpression` | Không evaluate bằng privileged context |
| **User-edited DB policy** | Rule string trong DB do tenant admin tự đổi | Không dùng unrestricted SpEL; cần safe DSL/admin trust review |
| **SpEL expression parse error** | Bean/method reference sai | Fail closed, alert configuration |
| **Expression result null** | Guard trả null/không có Boolean hợp lệ | Không coi là allow |
| **Bean method throw** | Policy DB lỗi | Fail closed, không thực thi side effect |
| **Bean name collision** | App có bean `invoiceGuard` sai/overridden | Startup/integration test xác minh đúng bean/policy |
| **Principal name là client ID** | `authentication.name=invoice-web` | Không coi là user:an cho owner ACL |
| **Multi-issuer cùng sub** | AS-A sub=123, AS-B sub=123 | Tách identity theo issuer/tenant |
| **Client credentials dùng user route** | Service có scope read nhưng không user-sub | Deny theo user-delegated policy |
| **Delegated user route đúng grant** | User sub/tenant verified | Có thể kiểm tiếp object ACL |
| **`@PostAuthorize` null return** | Method trả null | Fail closed/explicit not-found handling |
| **`@PostAuthorize` sau write** | Method đã thay DB trước deny | Security design FAIL; dùng pre-authorization/atomic constraints |
| **`@PostFilter` nhiều records** | Query tải toàn bộ org rồi lọc | Test hiệu năng & privacy FAIL; query-level tenant filter |
| **`@PreFilter` silent drop** | Request approve 10 IDs nhưng 3 bị lọc | Nếu all-or-nothing requirement thì deny cả request |
| **Immutable collection** | Input `List.of(...)` qua prefilter | Test hành vi framework, tránh unsupported mutation |
| **Cross-tenant list** | Query 100 records cả org-A/B | Chỉ authorized records được loaded/returned theo policy |
| **Time-of-check/use race** | Ownership thay giữa guard và query | Atomic/constrained DB operation chặn |
| **Stale JWT scope** | Admin vừa gỡ approve, JWT cũ còn exp | Revoke/dynamic policy theo security SLO |
| **Stale authorization cache** | Policy cache còn allow sau ACL change | Invalidate/TTL/decision policy đúng |
| **DPoP proof thiếu** | Sender-bound token nhưng không có proof | Reject trước method |
| **mTLS cert mismatch** | Token bound cert A, request cert B | Reject |
| **Bearer token replay** | Attacker có token còn hạn | Threat test chỉ ra cần sender binding/revoke/TTL |
| **Cookie JWT CSRF** | Cross-site unsafe POST với auth cookie | CSRF guard ở cookie boundary chặn |
| **Method 403 nhưng DB đã ghi** | Controller/service ghi trước guard hoặc async side effect | Test FAIL: require zero side effects |
| **Method 403 nhưng webhook đã gửi** | External effect chạy trước check | Test FAIL: transaction/outbox redesign |
| **Error message tiết lộ owner** | Deny trả người sở hữu thật của invoice | Security privacy test FAIL |
| **Raw token trong log** | Log toàn `Authentication`/`Authorization` | Redaction test FAIL |
| **`@WithMockUser` thay JWT test thật** | Fake ROLE_ADMIN → pass method | Không chứng minh JWT issuer/audience/signature verification |
| **MockMvc `jwt()` thành công** | Spring Security Test gắn authentication giả | Chỉ chứng minh authorization mapping ở test, không crypto end-to-end |

### Kiểm thử đúng các tầng

~~~text
Unit:
  InvoiceGuard.canRead(...) with verified actor fixtures
  + null/tenant/owner/ID schema cases.

Method security:
  @EnableMethodSecurity, real proxied Spring bean,
  missing scope -> deny BEFORE method body side effect.

Web:
  MockMvc jwt() helper for authority rules,
  with explicit warning that decoder is bypassed.

JWT integration:
  signed test JWS, trusted test JWKS,
  expected iss/aud/exp/type and correct method guard.

Opaque integration:
  test AS introspection endpoint, active=true/false,
  RS credentials, schema, audience, expiry and outage.

Data:
  DB rows across tenants and owners;
  wrong-tenant requests cause zero unauthorized reads/writes.

Async / batch:
  actor context and revocation/expiry policy,
  no internal-call bypass, no unaudited service-admin fallback.
~~~

**Điểm quan trọng:** Một **unit test SpEL** có thể kiểm biểu thức parse và Boolean logic, nhưng **không chứng minh JWT cryptography hoặc HTTP security đã bật đúng**. Ngược lại, một test token signature không chứng minh owner/tenant policy của `invoiceGuard`.

## 19. Kiểm thử Java/Spring Security có thể tái sử dụng

### Với Spring Security Test: test method authorization

Một test framework có thể dùng `@WithMockUser` để tạo mock security context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.test.context.support.WithMockUser;

// Ví dụ trong Spring Boot integration test với Spring bean proxied:
@Test
@WithMockUser(
    username = "user:an",
    authorities = {"SCOPE_invoice:read"})
void methodScopeIsPresent() {
    // Test có thể kiểm simple hasAuthority expression.
    // Nếu InvoiceGuard yêu cầu JwtAuthenticationToken cụ thể,
    // mock Authentication này KHÔNG đủ cho canRead().
}
~~~

**Phân biệt:**

- `@WithMockUser(authorities="SCOPE_invoice:read")` tạo authorities giả để test method guard, nhưng không có **JWT signature/AS trust**.
- `@WithMockUser(roles="ADMIN")` thường tạo `ROLE_ADMIN`, không phải `SCOPE_invoice:read`.
- Nếu guard cần `JwtAuthenticationToken`, dùng **đúng authentication type/test helper** hoặc fixture JWT đã verified theo test pipeline; không sửa production guard để cho mọi mock principal qua.

### MockMvc với JWT authorities

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Một phần test method, mockMvc đã được inject.
mockMvc.perform(
    get("/api/invoices/INV-42")
        .with(jwt().jwt(jwt -> jwt
            .subject("user:an")
            .claim("tenant_id", "org-A")
            .claim("iss", "https://auth.example.test")
            .claim("aud", java.util.List.of("invoice-api")))
            .authorities(
                new org.springframework.security.core.authority.SimpleGrantedAuthority(
                    "SCOPE_invoice:read"))))
    .andExpect(status().isOk());
~~~

Kết quả `200` đòi fixture `INV-42` thực sự thuộc user/tenant và mock repository/DB phù hợp. **`jwt()` của Spring Security Test tạo test Authentication, không xác minh JWT signature qua `JwtDecoder`**. Vì vậy, phải có integration test khác dùng **JWS do test AS ký** và JWKS tin cậy để kiểm security trust chain.

### Test chống self-invocation với side-effect spy

~~~java
// Pseudocode test assertions:
given authenticated caller WITHOUT SCOPE_invoice:approve
when invoke public batch entrypoint that leads to approveOne(...)
then:
  access is denied by an enforced policy
  invoiceRepository.approve(...) called zero times
  paymentGateway.send(...) called zero times
~~~

Test phải thực sự gọi **bean/path giống production** chứ không chỉ dùng reflection gọi method có annotation một cách cô lập. Nếu test phát hiện bypass, sửa kiến trúc `this.approveOne()` hoặc di chuyển bảo vệ vào domain service nơi không thể gọi vòng.

### Test không thực thi biểu thức từ user

~~~text
Given:
  request invoiceId = a string with quotes, parentheses,
  expression-like characters, and unusual Unicode.

When:
  @PreAuthorize("@invoiceGuard.canRead(authentication, #invoiceId)")

Then:
  InvoiceGuard receives the SAME string as data,
  validates length/format, and returns false if invalid.
  No SpelExpressionParser evaluates that string as code.
~~~

Không cần chạy payload nguy hiểm trong lesson. Mục tiêu test là bảo đảm **dữ liệu chỉ là dữ liệu**, chính sách không bao giờ parse hoặc compile một chuỗi attacker-controlled thành SpEL.

## 20. Tình huống thực hành: Invoice approval và dữ liệu từ request

Một hệ thống có:

~~~text
AS issuer: https://auth.example.test
Invoice RS audience: invoice-api

User An:
  iss=https://auth.example.test
  sub=user:an
  tenant_id=org-A
  scope=invoice:read invoice:approve

User Bình:
  iss=https://auth.example.test
  sub=user:binh
  tenant_id=org-B
  scope=invoice:read

Invoice INV-42:
  tenant=org-A
  owner=user:an
  status=PENDING
  amount=1,200,000 VND

Invoice INV-99:
  tenant=org-B
  owner=user:binh
  status=PENDING

API:
  POST /api/invoices/{invoiceId}/approve
  BODY: { "tenantId": "...", "adminApproved": true, ... }
~~~

**Yêu cầu:** Chỉ những actor có scope `invoice:approve`, quyền trên tenant/object, và policy phê duyệt tương ứng mới được chuyển trạng thái invoice. Caller được quyền **chọn invoiceId và nhập body**, nhưng **không được tự khai quyền**.

### Thiết kế không an toàn

~~~java
@PreAuthorize("#request.adminApproved")
public void approve(ApproveInvoiceRequest request) {
    repository.markApproved(request.invoiceId());
}
~~~

Attacker chỉ cần tự khai `adminApproved=true`. Mọi thứ trong `#request` là user-controlled; một trường tên “adminApproved” không trở thành quyền đáng tin chỉ vì SpEL đọc nó.

### Thiết kế có phân tách lớp

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoice:approve') and " +
    "@invoiceGuard.canApprove(authentication, #invoiceId, #request)")
public ApprovalResult approve(
        @P("invoiceId") String invoiceId,
        @P("request") ApproveInvoiceRequest request) {

    // Service/DB vẫn phải thực hiện transaction-safe
    // tenant, state, amount, beneficiary và idempotency constraints.
    return approvalService.approveUnderPolicy(invoiceId, request);
}
~~~

`canApprove` phải dùng **trusted actor** và **resource state**. `request.tenantId()` có thể dùng như selected tenant **sau khi kiểm actor có membership/entitlement**; không thể dùng trực tiếp làm proof. `request.adminApproved` bị bỏ qua như authority.

### 15 câu hỏi vận dụng

**Câu 1. `#invoiceId` đến từ URL có bị coi là mã SpEL tự thực thi không?**

**Không**, khi được bind dưới dạng argument variable của **một biểu thức SpEL static**. Nó là giá trị truyền cho guard. Rủi ro phát sinh nếu developer **ghép/parse lại chuỗi đó thành expression hoặc SQL**.

**Câu 2. Vì sao `@PreAuthorize("#request.adminApproved")` nguy hiểm?**

Boolean đó do caller có thể gửi. SpEL kiểm một **dữ liệu chưa tin** thay vì kiểm sự phê duyệt từ trusted authorization system.

**Câu 3. Token có `scope=invoice:approve` và `aud=payroll-api` thì annotation scope check có đủ?**

**Không.** Resource Server phải từ chối token sai audience **trước** khi map authority và gọi method.

**Câu 4. Với token của Bình, có thể thay `tenantId=org-A` trong body để phê duyệt INV-42 không?**

**Không.** Tenant selector trong body không chứng minh Bình là member hoặc có delegation trong org-A. Guard/service phải kiểm issuer/subject/membership/object policy.

**Câu 5. Tại sao `hasAuthority("SCOPE_invoice:approve")` không đủ cho INV-99 của tenant B?**

Nó chỉ chứng minh token được AS cấp quyền thao tác “approve” thuộc contract; không tự chứng minh actor có quyền **trên INV-99**.

**Câu 6. Nếu `@EnableMethodSecurity` bị bỏ, annotation còn tác dụng không?**

Không nên giả định còn có interceptor tương ứng. Cần bật đúng cơ chế và integration test thiếu scope để chứng minh method không chạy.

**Câu 7. Nếu `processBatch()` gọi `this.approveOne()`, `@PreAuthorize` có chạy không?**

**Có thể không** ở proxy-based mode vì self-invocation bypass proxy. Tách bean/call qua proxy đúng và giữ guard ở domain boundary.

**Câu 8. Nếu `@PostAuthorize` từ chối sau khi method đã gọi payment provider, side effect có tự rollback không?**

**Không bảo đảm.** External side effect không tự undo. Với command/financial operations, bảo vệ trước khi thực thi và dùng transactional/outbox/idempotency policies.

**Câu 9. `@PostFilter` có phù hợp để lọc Page chứa hàng nghìn invoice mọi tenant không?**

**Không phải mặc định tốt.** Dữ liệu có thể đã bị tải vào memory, pagination/count sai, N+1 ACL checks và privacy risk. Nên lọc tenant/owner ngay trong DB query.

**Câu 10. Khi Spring báo `#invoiceId` là null dù HTTP path có ID, phải làm gì?**

Kiểm parameter name binding `@P("invoiceId")`/`-parameters`, proxy/interface metadata và tests; **không** làm policy fail open khi ID null.

**Câu 11. Nếu access token do AS cấp đã bị đánh cắp, `@PreAuthorize` có chặn attacker không?**

Chưa chắc. Attacker có **Bearer token** còn hợp lệ có thể mang cùng scopes. Cần TTL, revoke, DPoP/mTLS sender binding và API/domain abuse controls theo threat model.

**Câu 12. Nếu một rule SpEL lấy từ ô cấu hình user có thể chỉnh được, cần làm sao?**

Không thực thi nó trong privileged `EvaluationContext`. Dùng policy cố định hoặc một DSL hạn chế và kiểm soát nguồn cấu hình, phân quyền, audit, validation và sandbox.

**Câu 13. `authentication.name` có luôn là end-user subject không?**

**Không.** Converter có thể dùng `sub`/`client_id` hoặc principal tùy JWT/opaque/session. Với multi-issuer, subject thường cần gắn issuer/tenant.

**Câu 14. Nếu policy DB tạm ngừng hoạt động, có cho phép approve để giữ availability không?**

**Không.** Không có quyết định quyền đáng tin thì phải deny/fail closed, đồng thời báo lỗi vận hành phù hợp.

**Câu 15. Khi nào có thể cân nhắc `@PostAuthorize`?**

Khi cần kiểm thuộc tính **kết quả read-only** sau khi load, không có side effect trước lúc deny, và đã kiểm performance/DB privacy. Với write operations, ưu tiên pre-authorization và atomic domain constraints.

## 21. Checklist production: SpEL và dữ liệu người dùng

### A. Nguồn tin cậy của SpEL và đầu vào

1. **Biểu thức là code tin cậy:** `@PreAuthorize`/`@PostAuthorize` là logic do developer/security team review, không nhận SpEL program từ request?
2. **Untrusted input chỉ là value:** Path/query/body/headers được bind qua `#parameter` hoặc typed methods, không ghép thành chuỗi SpEL cần parse?
3. **Không dùng privileged `parseExpression` cho input attacker:** Không trao `BeanResolver`/`TypeLocator`/method invocation không kiểm soát cho user-authored expressions?
4. **Policy động có trust model:** Nếu policy từ DB/config, quyền sửa, versioning, review, giới hạn DSL và evaluator capabilities được kiểm?
5. **Không lấy role/scope từ body:** `request.isAdmin`, `request.role`, `X-Scope` không được biến thành `GrantedAuthority`?
6. **Method argument binding đúng:** `@P("invoiceId")` hoặc `-parameters` được test; missing `#param` không thành wildcard/allow?
7. **Validate input shape:** null/blank/length/format, type coercion và regex complexity được kiểm bằng Java/Bean Validation?
8. **Không parse dữ liệu lần hai:** Policy bean không nhận ID/JSON/filter string rồi tự parse nó thành SpEL, SQL hay JPQL nối chuỗi?
9. **Fail closed khi SpEL lỗi:** Null, bean lookup/type mismatch, timeout hoặc evaluation exception không cho phép thao tác?
10. **Không dùng SpEL thay domain logic:** Các điều kiện phức tạp được chuyển sang typed policy bean với input/output đã review?

### B. Token security và principal

11. **JWT/opaque token đã xác minh:** AS issuer/JWKS hoặc introspection endpoint được tin cậy, không Base64 decode rồi tự cấp authority?
12. **Issuer exact:** `iss` thuộc allowlist, không auto-fetch token-supplied issuer/JWKS?
13. **Audience/resource binding:** `aud` chứa đúng RS; scope đúng tên không cứu token sai audience?
14. **Token type:** OAuth access token không bị nhầm với OIDC ID token hay refresh token?
15. **Lifetime:** `exp`/`nbf`/`iat` và clock skew phù hợp, không dùng token đã expired?
16. **Scope mapping chuẩn:** `scope`/`scp` được map thành `SCOPE_*` theo contract, không so substring hay nhầm `ROLE_*`?
17. **Grant/user/workload semantics:** `client_credentials` không tự tạo end-user; `authentication.name` không bị coi là user trong mọi token profile?
18. **Multi-issuer identity:** Subject có ràng buộc issuer/tenant để tránh AS-A `sub=123` bị nhầm AS-B `sub=123`?
19. **Sender-binding và replay:** DPoP/mTLS proof được kiểm khi profile yêu cầu, không cho token sender-constrained chạy như Bearer thuần?
20. **Revocation/state:** JWT offline không tự cập nhật scope vừa bị gỡ; TTL/denylist/introspection/dynamic ACL đáp ứng SLO?

### C. Method security, AOP và business authorization

21. **`@EnableMethodSecurity` active:** App startup/integration tests xác nhận annotations thực sự được enforce?
22. **Method được intercept:** Không đặt guard duy nhất ở private/final/self-invoked method không qua proxy?
23. **Gọi qua trusted bean:** Internal batch/scheduler/controller đều đi qua appropriate security/domain guard?
24. **Không gọi logic quyền ngoài trust boundary:** Guard chạy trước side effects; caller chưa xác thực không được gọi privileged service?
25. **Scope AND object policy:** `hasAuthority('SCOPE_invoice:read')` đi cùng quyền trên invoice ID/owner/tenant?
26. **Object ID là selector:** Path ID được so với database ownership/ACL, không tự là bằng chứng quyền?
27. **Tenant header/body là selector:** Membership/entitlement phải từ trusted identity/authorization store?
28. **Repository query parameterized:** Không có SQL/JPQL injection; query hạn chế issuer/tenant/owner/permission trong cùng data operation?
29. **Transaction-safe write:** Kiểm version/state/owner/tenant ở write boundary, xử lý TOCTOU và concurrency?
30. **Không dùng `@PostAuthorize` sau side effect:** Với payment/email/webhook, deny sau method không đủ để rollback?
31. **Filters không làm rò dữ liệu:** `@PreFilter`/`@PostFilter` có N+1/pagination/immutable collection/size policy, ưu tiên query-level ACL?
32. **Async context an toàn:** SecurityContext không bị mất/nhầm giữa threads, scheduler có workload identity và expiry/revocation policy?
33. **Reactive execution model đúng:** WebFlux/Reactor không sao chép thread-local assumptions từ Servlet?
34. **Method+HTTP guard phối hợp:** API private được bảo vệ ở `SecurityFilterChain`/method/domain layers, default deny và matcher order rõ?
35. **CSRF đúng credential transport:** BFF/session-cookie routes có CSRF protection, không tắt global vì có JWT ở downstream?

### D. Kiểm thử, vận hành và giám sát

36. **Unit policy tests:** Null/blank/sai tenant/sai subject/sai scope và input trông như biểu thức vẫn chỉ là dữ liệu?
37. **Method proxy integration tests:** Kiểm cả self-invocation, batch entrypoint, private/final limitations và `@EnableMethodSecurity`?
38. **Crypto integration tests:** Signed JWT test AS/JWKS kiểm issuer/audience/type/expiry, không chỉ `@WithMockUser` hoặc `jwt()`?
39. **Opaque integration tests:** `active=false`, AS auth failure, thiếu claims, timeout và cache/revoke semantics được thử?
40. **No-side-effect assertions:** Denied requests không ghi DB, không gửi webhook/payment và không tạo async job?
41. **Identity/tenant privacy:** Không tiết lộ owner/tenant của record bị từ chối; 403/404 policy rõ?
42. **Metrics không lộ credentials:** Không log raw token, `jti`, CSRF/refresh token, client secret hoặc toàn bộ SpEL evaluation context?
43. **Performance bounded:** Guard DB/remote calls có timeouts, batching, limits; không N+1 khi filter list rất lớn?
44. **Authorization cache đúng lifecycle:** Keys theo verified issuer/subject/tenant/object/action/policy version, TTL và invalidation sau ACL change?
45. **Incident runbook:** Có cách xử lý token theft, revoke propagation, authorization policy outage, route bypass, proxy self-invocation và owner/tenant leak?

**Tóm lại:** Spring Security SpEL là **ngôn ngữ diễn đạt chính sách**; dữ liệu người dùng chỉ được dùng dưới dạng **giá trị cần kiểm tra**, không được biến thành mã SpEL chạy trong privileged context. `@PreAuthorize` cần cả **scope đáng tin từ access token đã xác minh** và **quyền trên đối tượng cụ thể**; `@PostAuthorize`/`@PostFilter` chỉ nên dùng sau khi hiểu rõ side effect, latency và data leakage. Proxy/AOP, async context, transaction boundary và row-level data access là những nơi một biểu thức nhìn đúng vẫn có thể **không bảo vệ được API** nếu kiến trúc không được kiểm thử.

## 22. Thuật ngữ, chuẩn và tài liệu tham khảo

### Bảng thuật ngữ

| Thuật ngữ | Ý nghĩa trong bài |
|---|---|
| **SpEL** | Spring Expression Language, ngôn ngữ đánh giá các biểu thức policy |
| **Method security** | Kiểm authentication/authorization tại các Java method calls được intercept |
| **`@PreAuthorize`** | Đánh giá điều kiện trước khi thực thi method |
| **`@PostAuthorize`** | Đánh giá điều kiện dùng `returnObject` sau khi method trả kết quả |
| **`@PreFilter`/`@PostFilter`** | Lọc phần tử method arguments/results theo expression |
| **`#invoiceId`** | Method argument variable, có thể chứa dữ liệu attacker kiểm soát |
| **`@invoiceGuard`** | Spring bean được tham chiếu bởi expression để gọi typed policy |
| **`Authentication`/`principal`** | Kết quả authentication trong SecurityContext |
| **`GrantedAuthority`** | Quyền cụ thể như `SCOPE_invoice:read` được Spring gắn vào Authentication |
| **BOLA/IDOR** | Truy cập trái phép object do thiếu kiểm owner/tenant/resource |
| **TOCTOU** | Time-of-check to time-of-use: quyền hoặc trạng thái thay đổi giữa kiểm và thực thi |
| **Fail closed** | Khi không có quyết định quyền đáng tin, không thực thi thao tác |
| **AOP/proxy interception** | Cơ chế chặn method call để áp security annotation |

### Chuẩn và nguồn kỹ thuật

- **Spring Security Reference — Method Security:** `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, proxy/AOP, method expressions và parameter names.
- **Spring Security Reference — Authorization Architecture:** `Authentication`, `GrantedAuthority`, `AuthorizationManager` và cách Spring đưa quyết định quyền vào request/method.
- **Spring Security Reference — OAuth 2.0 Resource Server JWT:** `JwtDecoder`, `NimbusJwtDecoder`, `JwtAuthenticationConverter`, scope/authority mapping và issuer/audience validators.
- **Spring Security Reference — OAuth 2.0 Resource Server Opaque Token:** `OpaqueTokenIntrospector`, `active` và authorities từ introspection.
- **Spring Framework Reference — Spring Expression Language (SpEL):** expression parsing/evaluation, variables, method/property access, `StandardEvaluationContext` và `SimpleEvaluationContext`.
- **Spring Security Reference — Testing Method Security / Testing Servlet Security:** `@WithMockUser`, `MockMvc`, `jwt()`, method-security integration tests và giới hạn của mocks.
- **Spring Framework Reference — AOP/Proxying Mechanisms:** proxy boundaries, self-invocation, proxy modes và method interception.
- **Spring Framework Reference — Transaction Management:** transaction boundaries, advisor order, rollback và data consistency.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** AS/Client/RS roles, access tokens, `scope` và grant semantics.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer credential, `401 invalid_token`, `403 insufficient_scope` và token theft/replay.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token type, issuer, audience, scope và validation requirements.
- **RFC 7519 — JSON Web Token (JWT):** `iss`/`sub`/`aud`/`exp`/`nbf`/`iat` và NumericDate.
- **RFC 7515 — JSON Web Signature (JWS)** và **RFC 7517 — JSON Web Key (JWK):** trusted signing-key verification, JOSE header và JWKS.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, scopes/claims, endpoint authorization và cache considerations.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revoke token/grant và propagation tới RS.
- **RFC 8725 — JSON Web Token Best Current Practices:** token purpose/algorithm confusion, issuer/audience isolation và JWT security.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay, audience restriction và refresh security.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** ràng buộc access token đúng Resource Server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained token, `cnf.jkt`, proof `jti`/`iat`/`ath`/`htm`/`htu`.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** `cnf.x5t#S256` và ràng buộc chứng chỉ.
- **OpenID Connect Core 1.0:** ID token dành cho Relying Party và authentication event; không thay OAuth access token ở RS.
- **OWASP Authorization Cheat Sheet:** deny by default, least privilege, authorization tests, object-level permission và service boundary.
- **OWASP API Security Top 10:** Broken Object Level Authorization, Broken Function Level Authorization, missing access controls và sensitive operations.
- **OWASP Injection Prevention Cheat Sheet:** parameterized data access, không biến untrusted input thành executable expression/query.
- **OWASP OAuth 2.0 Cheat Sheet:** issuer/audience/scope trust, bearer token handling, revocation và sender constraint.
